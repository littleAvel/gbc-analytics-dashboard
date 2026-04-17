"""
Общие фикстуры и настройка sys.path для тестов.
scripts/ добавляется в путь, чтобы импортировать upload_to_crm и sync_to_supabase
как обычные модули (без пакетных __init__.py).
"""

import sys
from pathlib import Path

# Добавляем scripts/ в путь импорта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

# ---------------------------------------------------------------------------
# Фикстуры для upload_to_crm
# ---------------------------------------------------------------------------

@pytest.fixture()
def crm_config():
    """Минимальный конфиг RetailCRM для upload_to_crm."""
    from upload_to_crm import Config
    return Config(url="https://demo.retailcrm.ru", api_key="test-key", site="main")


@pytest.fixture()
def mock_order():
    """Одиночный MockOrder с полным набором полей."""
    from upload_to_crm import MockOrder
    return MockOrder.model_validate({
        "firstName": "Айгуль",
        "lastName": "Касымова",
        "phone": "+77001234501",
        "email": "aigul@example.com",
        "orderType": "eshop-individual",
        "orderMethod": "shopping-cart",
        "status": "new",
        "items": [
            {"productName": "Nova Classic", "quantity": 2, "initialPrice": 15000},
            {"productName": "Nova Slim",    "quantity": 1, "initialPrice": 28000},
        ],
        "delivery": {"address": {"city": "Алматы", "text": "ул. Абая 1"}},
        "customFields": {"utm_source": "instagram"},
    })


@pytest.fixture()
def crm_payload(mock_order):
    """CRMOrderPayload, полученный трансформацией из mock_order."""
    from upload_to_crm import transform_order
    return transform_order(mock_order, "2024-01-15 10:00:00")


# ---------------------------------------------------------------------------
# Фикстуры для sync_to_supabase
# ---------------------------------------------------------------------------

@pytest.fixture()
def sync_config():
    """Минимальный конфиг для sync_to_supabase."""
    from sync_to_supabase import Config
    return Config(
        retailcrm_url="https://demo.retailcrm.ru",
        retailcrm_api_key="test-key",
        retailcrm_site="main",
        supabase_url="https://xxx.supabase.co",
        supabase_service_key="service-key",
        telegram_bot_token="123456:ABC",
        telegram_chat_id="-100123456",
    )


@pytest.fixture()
def crm_order():
    """CRMOrder из RetailCRM — типичный заказ ниже порога алерта."""
    from sync_to_supabase import CRMOrder, CRMDelivery, CRMAddress
    return CRMOrder(
        id=1001,
        externalId="mock-77001234501",
        firstName="Айгуль",
        lastName="Касымова",
        phone="+77001234501",
        email="aigul@example.com",
        totalSumm=30000.0,
        status="new",
        orderType="main",
        orderMethod="shopping-cart",
        delivery=CRMDelivery(address=CRMAddress(city="Алматы", text="ул. Абая 1")),
        createdAt="2024-01-15 10:00:00",
    )


@pytest.fixture()
def large_crm_order(crm_order):
    """CRMOrder с суммой выше порога алерта (> 50 000)."""
    return crm_order.model_copy(update={"totalSumm": 75000.0})
