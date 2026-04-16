"""
upload_to_crm.py — загружает mock_orders.json в RetailCRM через API v5.

Запуск:
    python scripts/upload_to_crm.py

Переменные окружения (из .env.local или .env):
    RETAILCRM_URL       — https://<subdomain>.retailcrm.ru
    RETAILCRM_API_KEY   — ключ API из настроек RetailCRM
    RETAILCRM_SITE      — символьный код магазина (Настройки → Магазины)
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
import os
from pydantic import BaseModel, field_validator

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
    """Загружает .env.local с приоритетом над .env."""
    root = Path(__file__).resolve().parent.parent
    local_env = root / ".env.local"
    base_env = root / ".env"
    if local_env.exists():
        load_dotenv(local_env, override=True)
        logger.debug("Loaded env from .env.local")
    elif base_env.exists():
        load_dotenv(base_env, override=True)
        logger.debug("Loaded env from .env")


@dataclass(frozen=True)
class Config:
    url: str          # https://<subdomain>.retailcrm.ru
    api_key: str      # API ключ
    site: str         # символьный код магазина

    @classmethod
    def from_env(cls) -> "Config":
        _load_env()
        url = os.environ.get("RETAILCRM_URL", "").rstrip("/")
        api_key = os.environ.get("RETAILCRM_API_KEY", "")
        site = os.environ.get("RETAILCRM_SITE", "")
        missing = [k for k, v in [("RETAILCRM_URL", url), ("RETAILCRM_API_KEY", api_key), ("RETAILCRM_SITE", site)] if not v]
        if missing:
            raise EnvironmentError(f"Не заданы переменные окружения: {', '.join(missing)}")
        return cls(url=url, api_key=api_key, site=site)


# ---------------------------------------------------------------------------
# Pydantic models — входные данные (mock_orders.json)
# ---------------------------------------------------------------------------

class MockOrderItem(BaseModel):
    productName: str
    quantity: int
    initialPrice: float


class MockOrderAddress(BaseModel):
    city: str
    text: str


class MockOrderDelivery(BaseModel):
    address: MockOrderAddress


class MockOrderCustomFields(BaseModel):
    utm_source: str | None = None


class MockOrder(BaseModel):
    firstName: str
    lastName: str
    phone: str
    email: str
    orderType: str
    orderMethod: str  # читаем из JSON, но в payload не передаём
    status: str
    items: list[MockOrderItem]
    delivery: MockOrderDelivery
    customFields: MockOrderCustomFields | None = None

    @field_validator("phone")
    @classmethod
    def phone_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("phone не может быть пустым")
        return v.strip()


# ---------------------------------------------------------------------------
# Pydantic models — формат RetailCRM (для сериализации)
# ---------------------------------------------------------------------------

class CRMOrderItem(BaseModel):
    """Позиция заказа в формате RetailCRM."""
    quantity: int
    initialPrice: float
    offer: dict[str, Any]  # {"name": productName}


class CRMDeliveryAddress(BaseModel):
    city: str
    text: str


class CRMDelivery(BaseModel):
    address: CRMDeliveryAddress


_CRM_ORDER_TYPE = "main"  # единственный тип в аккаунте


class CRMOrderPayload(BaseModel):
    """Заказ в формате RetailCRM API v5."""
    externalId: str
    firstName: str
    lastName: str
    phone: str
    email: str
    orderType: str
    orderMethod: str
    status: str
    createdAt: str          # "YYYY-MM-DD HH:MM:SS"
    items: list[CRMOrderItem]
    delivery: CRMDelivery
    customFields: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Маппинги справочников RetailCRM
# ---------------------------------------------------------------------------

# Статусы RetailCRM: new, assembling, delivering, complete, cancel-other, ...
STATUS_MAP: dict[str, str] = {
    "new": "new",
    "in_progress": "assembling",
    "assembling": "assembling",
    "delivering": "delivering",
    "shipped": "delivering",
    "done": "complete",
    "completed": "complete",
    "cancelled": "cancel-other",
    "canceled": "cancel-other",
}

# Методы RetailCRM: phone, shopping-cart, one-click, landing-page,
#                   offline, app, live-chat, messenger, ...
ORDER_METHOD_MAP: dict[str, str] = {
    "shopping-cart": "shopping-cart",
    "cart": "shopping-cart",
    "online": "shopping-cart",
    "phone": "phone",
    "callback": "phone",
    "one-click": "one-click",
    "landing-page": "landing-page",
    "landing": "landing-page",
    "offline": "offline",
    "app": "app",
    "live-chat": "live-chat",
    "messenger": "messenger",
}

_DEFAULT_ORDER_METHOD = "shopping-cart"
_DEFAULT_STATUS = "new"


def _map_status(status: str) -> str:
    return STATUS_MAP.get(status, _DEFAULT_STATUS)


def _map_order_method(method: str) -> str:
    return ORDER_METHOD_MAP.get(method, _DEFAULT_ORDER_METHOD)


# ---------------------------------------------------------------------------
# Трансформация
# ---------------------------------------------------------------------------

def make_external_id(order: MockOrder) -> str:
    """Генерирует стабильный externalId из номера телефона."""
    digits = "".join(c for c in order.phone if c.isdigit())
    return f"mock-{digits}"


def transform_order(order: MockOrder, created_at: str) -> CRMOrderPayload:
    """Преобразует MockOrder → CRMOrderPayload."""
    crm_items = [
        CRMOrderItem(
            quantity=item.quantity,
            initialPrice=item.initialPrice,
            offer={"name": item.productName},
        )
        for item in order.items
    ]

    custom: dict[str, Any] = {}
    if order.customFields and order.customFields.utm_source:
        custom["utm_source"] = order.customFields.utm_source

    return CRMOrderPayload(
        externalId=make_external_id(order),
        firstName=order.firstName,
        lastName=order.lastName,
        phone=order.phone,
        email=order.email,
        orderType=_CRM_ORDER_TYPE,
        orderMethod=_map_order_method(order.orderMethod),
        status=_map_status(order.status),
        createdAt=created_at,
        items=crm_items,
        delivery=CRMDelivery(
            address=CRMDeliveryAddress(
                city=order.delivery.address.city,
                text=order.delivery.address.text,
            )
        ),
        customFields=custom if custom else None,
    )


# ---------------------------------------------------------------------------
# HTTP клиент — RetailCRM API v5
# ---------------------------------------------------------------------------

# RetailCRM возвращает 460 когда заказ с таким externalId уже существует
_DUPLICATE_STATUS = 460


def _payload_to_form(config: Config, order_dict: dict[str, Any]) -> dict[str, str]:
    """Формирует form-urlencoded тело запроса."""
    # Убираем None-поля перед сериализацией
    clean = {k: v for k, v in order_dict.items() if v is not None}
    return {
        "apiKey": config.api_key,
        "site": config.site,
        "order": json.dumps(clean, ensure_ascii=False),
    }


def create_order(
    client: httpx.Client,
    config: Config,
    payload: CRMOrderPayload,
) -> tuple[int, dict[str, Any]]:
    """POST /api/v5/orders/create. Возвращает (http_status, response_json)."""
    order_dict = payload.model_dump(exclude_none=True)
    form = _payload_to_form(config, order_dict)
    resp = client.post(f"{config.url}/api/v5/orders/create", data=form)
    return resp.status_code, resp.json()


def edit_order(
    client: httpx.Client,
    config: Config,
    payload: CRMOrderPayload,
) -> tuple[int, dict[str, Any]]:
    """POST /api/v5/orders/{externalId}/edit?by=externalId."""
    order_dict = payload.model_dump(exclude_none=True)
    form = _payload_to_form(config, order_dict)
    url = f"{config.url}/api/v5/orders/{payload.externalId}/edit"
    resp = client.post(url, params={"by": "externalId"}, data=form)
    return resp.status_code, resp.json()


def upsert_order(
    client: httpx.Client,
    config: Config,
    payload: CRMOrderPayload,
) -> tuple[str, bool]:
    """
    Создаёт или обновляет заказ (идемпотентно).
    Возвращает (action, success) где action = "created" | "updated" | "error".
    """
    try:
        status_code, body = create_order(client, config, payload)

        if status_code == 201 and body.get("success"):
            return "created", True

        # Дубликат — пробуем обновить
        if status_code == _DUPLICATE_STATUS or (
            not body.get("success") and (
                "externalId" in str(body.get("errors", ""))
                or "already exists" in str(body.get("errorMsg", ""))
            )
        ):
            status_code, body = edit_order(client, config, payload)
            if body.get("success"):
                return "updated", True
            logger.error(
                "externalId=%s | edit failed | %d | %s",
                payload.externalId, status_code, body,
            )
            return "error", False

        logger.error(
            "externalId=%s | create failed | %d | %s",
            payload.externalId, status_code, body,
        )
        return "error", False

    except httpx.HTTPError as exc:
        logger.error("externalId=%s | HTTP error: %s", payload.externalId, exc)
        return "error", False


# ---------------------------------------------------------------------------
# Загрузка данных
# ---------------------------------------------------------------------------

def load_orders(path: Path) -> list[MockOrder]:
    """Читает и валидирует mock_orders.json через Pydantic."""
    raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    orders: list[MockOrder] = []
    errors = 0
    for i, item in enumerate(raw, start=1):
        try:
            orders.append(MockOrder.model_validate(item))
        except Exception as exc:
            logger.warning("Заказ #%d невалиден, пропускаю: %s", i, exc)
            errors += 1
    logger.info("Загружено заказов: %d, невалидных: %d", len(orders), errors)
    return orders


# ---------------------------------------------------------------------------
# Основной цикл
# ---------------------------------------------------------------------------

_RATE_LIMIT_SECONDS = 0.1  # 100 мс между запросами


def upload_all(orders: list[MockOrder], config: Config) -> None:
    created = updated = errors = 0
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with httpx.Client(timeout=30.0) as client:
        for i, order in enumerate(orders, start=1):
            try:
                payload = transform_order(order, created_at)
            except Exception as exc:
                logger.error("Заказ #%d | ошибка трансформации: %s", i, exc)
                errors += 1
                continue

            action, success = upsert_order(client, config, payload)

            if success:
                icon = "+" if action == "created" else "~"
                logger.info(
                    "[%s] #%d | %s | %s %s",
                    icon, i, payload.externalId, action, payload.firstName,
                )
                if action == "created":
                    created += 1
                else:
                    updated += 1
            else:
                logger.error("[!] #%d | %s | ОШИБКА", i, payload.externalId)
                errors += 1

            if i < len(orders):
                time.sleep(_RATE_LIMIT_SECONDS)

    total = created + updated + errors
    logger.info(
        "\n─────────────────────────────\n"
        "  Итог: %d заказов\n"
        "  ✓ Создано:  %d\n"
        "  ~ Обновлено: %d\n"
        "  ✗ Ошибок:   %d\n"
        "─────────────────────────────",
        total, created, updated, errors,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    start = time.monotonic()

    config = Config.from_env()
    logger.info("RetailCRM: %s | site: %s", config.url, config.site)

    orders_path = Path(__file__).resolve().parent.parent / "mock_orders.json"
    if not orders_path.exists():
        raise FileNotFoundError(f"Файл не найден: {orders_path}")

    orders = load_orders(orders_path)
    if not orders:
        logger.warning("Нет заказов для загрузки, выход.")
        return

    upload_all(orders, config)

    elapsed = time.monotonic() - start
    logger.info("Время выполнения: %.1f сек", elapsed)


if __name__ == "__main__":
    main()
