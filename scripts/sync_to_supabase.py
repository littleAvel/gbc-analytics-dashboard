"""
sync_to_supabase.py — забирает заказы из RetailCRM и синхронизирует в Supabase.

Запуск:
    python scripts/sync_to_supabase.py

Переменные окружения (из .env.local или .env):
    RETAILCRM_URL         — https://<subdomain>.retailcrm.ru
    RETAILCRM_API_KEY     — ключ API
    RETAILCRM_SITE        — символьный код магазина
    SUPABASE_URL          — URL проекта Supabase
    SUPABASE_SERVICE_KEY  — service_role ключ (нужен для записи в обход RLS)
    TELEGRAM_BOT_TOKEN    — токен бота
    TELEGRAM_CHAT_ID      — chat_id куда слать алерты
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from supabase import Client, create_client

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_env() -> None:
    root = Path(__file__).resolve().parent.parent
    local_env = root / ".env.local"
    base_env = root / ".env"
    if local_env.exists():
        load_dotenv(local_env, override=True)
    elif base_env.exists():
        load_dotenv(base_env, override=True)


@dataclass(frozen=True)
class Config:
    retailcrm_url: str
    retailcrm_api_key: str
    retailcrm_site: str
    supabase_url: str
    supabase_service_key: str
    telegram_bot_token: str
    telegram_chat_id: str

    @classmethod
    def from_env(cls) -> "Config":
        _load_env()
        fields = {
            "RETAILCRM_URL": "",
            "RETAILCRM_API_KEY": "",
            "RETAILCRM_SITE": "",
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_KEY": "",
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "",
        }
        for key in fields:
            fields[key] = os.environ.get(key, "").strip()

        missing = [k for k, v in fields.items() if not v]
        if missing:
            raise EnvironmentError(f"Не заданы переменные окружения: {', '.join(missing)}")

        return cls(
            retailcrm_url=fields["RETAILCRM_URL"].rstrip("/"),
            retailcrm_api_key=fields["RETAILCRM_API_KEY"],
            retailcrm_site=fields["RETAILCRM_SITE"],
            supabase_url=fields["SUPABASE_URL"],
            supabase_service_key=fields["SUPABASE_SERVICE_KEY"],
            telegram_bot_token=fields["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=fields["TELEGRAM_CHAT_ID"],
        )


# ---------------------------------------------------------------------------
# Pydantic models — ответ GET /api/v5/orders
# ---------------------------------------------------------------------------

class CRMAddress(BaseModel):
    city: str | None = None
    text: str | None = None


class CRMDelivery(BaseModel):
    address: CRMAddress | None = None


class CRMOrder(BaseModel):
    id: int                                # внутренний ID RetailCRM
    externalId: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    phone: str | None = None
    email: str | None = None
    totalSumm: float = 0.0
    status: str | None = None
    orderType: str | None = None
    orderMethod: str | None = None
    delivery: CRMDelivery | None = None
    createdAt: str | None = None          # "YYYY-MM-DD HH:MM:SS" от RetailCRM

    # raw: весь объект сохраняем как jsonb — поле заполняется вручную после парсинга
    _raw: dict[str, Any] = {}

    def city(self) -> str | None:
        if self.delivery and self.delivery.address:
            return self.delivery.address.city
        return None


# ---------------------------------------------------------------------------
# RetailCRM — получение заказов
# ---------------------------------------------------------------------------

def fetch_crm_orders(config: Config) -> list[tuple[CRMOrder, dict[str, Any]]]:
    """
    GET /api/v5/orders → list[(CRMOrder, raw_dict)].
    Возвращает кортеж чтобы raw_dict можно было сохранить в jsonb.
    При 50 заказах limit=100 покрывает всё одной страницей.
    """
    url = f"{config.retailcrm_url}/api/v5/orders"
    params: dict[str, Any] = {
        "apiKey": config.retailcrm_api_key,
        "limit": 100,
        "page": 1,
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, params=params)

    if resp.status_code != 200:
        raise RuntimeError(
            f"RetailCRM вернул {resp.status_code}: {resp.text[:300]}"
        )

    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"RetailCRM ошибка: {body}")

    raw_orders: list[dict[str, Any]] = body.get("orders", [])
    result: list[tuple[CRMOrder, dict[str, Any]]] = []

    for raw in raw_orders:
        try:
            order = CRMOrder.model_validate(raw)
            result.append((order, raw))
        except Exception as exc:
            logger.warning("Не удалось распарсить заказ id=%s: %s", raw.get("id"), exc)

    logger.info("RetailCRM: получено %d заказов", len(result))
    return result


# ---------------------------------------------------------------------------
# Supabase — вспомогательные функции
# ---------------------------------------------------------------------------

def fetch_existing_ids(sb: Client) -> set[str]:
    """
    Возвращает множество retailcrm_id уже существующих в Supabase.
    Используется для определения новых заказов (нужно для Telegram-алерта).
    """
    resp = sb.table("orders").select("retailcrm_id").execute()
    return {row["retailcrm_id"] for row in (resp.data or [])}


def _parse_crm_datetime(value: str | None) -> str | None:
    """
    "2024-01-15 14:30:00" → "2024-01-15T14:30:00+00:00" (ISO 8601).
    Supabase принимает ISO-строку для timestamptz.
    """
    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        logger.warning("Не удалось распарсить дату: %r", value)
        return None


def build_row(order: CRMOrder, raw: dict[str, Any]) -> dict[str, Any]:
    """Формирует строку для Supabase из объекта CRMOrder."""
    now_iso = datetime.now(timezone.utc).isoformat()
    row: dict[str, Any] = {
        "retailcrm_id": str(order.id),
        "external_id": order.externalId,
        "first_name": order.firstName,
        "last_name": order.lastName,
        "phone": order.phone,
        "email": order.email,
        "total_sum": order.totalSumm,
        "status": order.status,
        "order_type": order.orderType,
        "order_method": order.orderMethod,
        "city": order.city(),
        "synced_at": now_iso,
        "raw_data": raw,
    }

    created = _parse_crm_datetime(order.createdAt)
    if created:
        row["created_at"] = created

    return row


def upsert_order(sb: Client, row: dict[str, Any]) -> None:
    """Upsert по retailcrm_id. При конфликте обновляет все поля кроме id."""
    sb.table("orders").upsert(row, on_conflict="retailcrm_id").execute()


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram_alert(config: Config, order: CRMOrder) -> bool:
    """Отправляет алерт о крупном заказе. Возвращает True при успехе."""
    text = (
        f"🔔 Новый крупный заказ\n"
        f"Сумма: {order.totalSumm:,.0f} ₸\n"
        f"Клиент: {order.firstName or ''} {order.lastName or ''}\n"
        f"Статус: {order.status or '—'}\n"
        f"ID: {order.id}"
    )
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    payload = {"chat_id": config.telegram_chat_id, "text": text}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        logger.warning(
            "Telegram ответил %d: %s", resp.status_code, resp.text[:200]
        )
        return False
    except httpx.HTTPError as exc:
        logger.error("Ошибка отправки в Telegram: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Основной цикл
# ---------------------------------------------------------------------------

_ALERT_THRESHOLD = 50_000.0


def sync(config: Config) -> None:
    # 1. Получаем заказы из RetailCRM
    orders_with_raw = fetch_crm_orders(config)

    # 2. Получаем существующие ID из Supabase (для определения новых)
    sb = create_client(config.supabase_url, config.supabase_service_key)
    existing_ids = fetch_existing_ids(sb)
    logger.info("Supabase: уже есть %d заказов", len(existing_ids))

    inserted = updated = alerts_sent = errors = 0

    for order, raw in orders_with_raw:
        retailcrm_id = str(order.id)
        is_new = retailcrm_id not in existing_ids

        try:
            row = build_row(order, raw)
            upsert_order(sb, row)
        except Exception as exc:
            logger.error("retailcrm_id=%s | ошибка upsert: %s", retailcrm_id, exc)
            errors += 1
            continue

        if is_new:
            inserted += 1
            logger.info("[+] retailcrm_id=%s | вставлен | %s %s | %.0f ₸",
                        retailcrm_id, order.firstName, order.lastName, order.totalSumm)

            if order.totalSumm > _ALERT_THRESHOLD:
                sent = send_telegram_alert(config, order)
                if sent:
                    alerts_sent += 1
                    logger.info("    → Telegram-алерт отправлен")
                else:
                    logger.warning("    → Telegram-алерт НЕ отправлен")
        else:
            updated += 1
            logger.info("[~] retailcrm_id=%s | обновлён | %s %s",
                        retailcrm_id, order.firstName, order.lastName)

    total = inserted + updated + errors
    logger.info(
        "\n─────────────────────────────\n"
        "  Итог: %d заказов\n"
        "  + Вставлено:  %d\n"
        "  ~ Обновлено:  %d\n"
        "  🔔 Алертов:   %d\n"
        "  ✗ Ошибок:    %d\n"
        "─────────────────────────────",
        total, inserted, updated, alerts_sent, errors,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import time
    start = time.monotonic()

    config = Config.from_env()
    logger.info(
        "RetailCRM: %s | Supabase: %s",
        config.retailcrm_url,
        config.supabase_url,
    )

    sync(config)

    elapsed = time.monotonic() - start
    logger.info("Время выполнения: %.1f сек", elapsed)


if __name__ == "__main__":
    main()
