"""
Тесты для scripts/upload_to_crm.py.

Покрытие:
- load_orders()       — парсинг реального mock_orders.json
- transform_order()   — маппинг полей, хардкод orderType, externalId, items
- _map_status()       — известные статусы и fallback
- _map_order_method() — известные методы и fallback
- upsert_order()      — ветки created / updated / error (httpx замокан)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from upload_to_crm import (
    _map_order_method,
    _map_status,
    load_orders,
    make_external_id,
    transform_order,
    upsert_order,
)

MOCK_ORDERS_PATH = Path(__file__).resolve().parent.parent / "mock_orders.json"


# ---------------------------------------------------------------------------
# load_orders
# ---------------------------------------------------------------------------

class TestLoadOrders:
    def test_returns_all_50_orders(self):
        orders = load_orders(MOCK_ORDERS_PATH)
        assert len(orders) == 50

    def test_each_item_is_mock_order(self):
        from upload_to_crm import MockOrder
        orders = load_orders(MOCK_ORDERS_PATH)
        assert all(isinstance(o, MockOrder) for o in orders)

    def test_first_order_has_expected_fields(self):
        orders = load_orders(MOCK_ORDERS_PATH)
        first = orders[0]
        assert first.firstName
        assert first.phone.startswith("+7")
        assert len(first.items) >= 1

    def test_skips_invalid_order(self, tmp_path):
        """Невалидный заказ пропускается, валидные возвращаются."""
        data = '[{"firstName":"Ok","lastName":"X","phone":"+7","email":"x@x.com",'
        data += '"orderType":"t","orderMethod":"m","status":"new",'
        data += '"items":[{"productName":"P","quantity":1,"initialPrice":100}],'
        data += '"delivery":{"address":{"city":"A","text":"B"}}}, '
        data += '{"broken": true}]'
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(data)
        orders = load_orders(bad_file)
        assert len(orders) == 1


# ---------------------------------------------------------------------------
# transform_order
# ---------------------------------------------------------------------------

class TestTransformOrder:
    def test_order_type_hardcoded_to_main(self, mock_order):
        payload = transform_order(mock_order, "2024-01-15 10:00:00")
        assert payload.orderType == "main"

    def test_external_id_built_from_phone_digits(self, mock_order):
        payload = transform_order(mock_order, "2024-01-15 10:00:00")
        assert payload.externalId == "mock-77001234501"

    def test_basic_fields_pass_through(self, mock_order):
        payload = transform_order(mock_order, "2024-01-15 10:00:00")
        assert payload.firstName == "Айгуль"
        assert payload.lastName == "Касымова"
        assert payload.phone == "+77001234501"
        assert payload.email == "aigul@example.com"

    def test_created_at_passed_verbatim(self, mock_order):
        ts = "2024-06-01 12:30:00"
        payload = transform_order(mock_order, ts)
        assert payload.createdAt == ts

    def test_items_converted_to_crm_format(self, mock_order):
        payload = transform_order(mock_order, "2024-01-15 10:00:00")
        assert len(payload.items) == 2
        first = payload.items[0]
        assert first.offer == {"name": "Nova Classic"}
        assert first.quantity == 2
        assert first.initialPrice == 15000.0

    def test_delivery_city_and_text_preserved(self, mock_order):
        payload = transform_order(mock_order, "2024-01-15 10:00:00")
        assert payload.delivery.address.city == "Алматы"
        assert payload.delivery.address.text == "ул. Абая 1"

    def test_custom_fields_utm_source(self, mock_order):
        payload = transform_order(mock_order, "2024-01-15 10:00:00")
        assert payload.customFields == {"utm_source": "instagram"}

    def test_custom_fields_none_when_absent(self, mock_order):
        order = mock_order.model_copy(update={"customFields": None})
        payload = transform_order(order, "2024-01-15 10:00:00")
        assert payload.customFields is None

    def test_order_method_mapped(self, mock_order):
        # "shopping-cart" → "shopping-cart" (прямое совпадение)
        payload = transform_order(mock_order, "2024-01-15 10:00:00")
        assert payload.orderMethod == "shopping-cart"

    def test_status_mapped(self, mock_order):
        payload = transform_order(mock_order, "2024-01-15 10:00:00")
        assert payload.status == "new"


# ---------------------------------------------------------------------------
# make_external_id
# ---------------------------------------------------------------------------

class TestMakeExternalId:
    def test_strips_plus_and_prefix(self, mock_order):
        assert make_external_id(mock_order) == "mock-77001234501"

    def test_phone_with_spaces_and_dashes(self, mock_order):
        order = mock_order.model_copy(update={"phone": "+7 700 123-45-01"})
        assert make_external_id(order) == "mock-77001234501"


# ---------------------------------------------------------------------------
# _map_status
# ---------------------------------------------------------------------------

class TestMapStatus:
    @pytest.mark.parametrize("input_status,expected", [
        ("new",        "new"),
        ("in_progress","assembling"),
        ("assembling", "assembling"),
        ("delivering", "delivering"),
        ("shipped",    "delivering"),
        ("done",       "complete"),
        ("completed",  "complete"),
        ("cancelled",  "cancel-other"),
        ("canceled",   "cancel-other"),
    ])
    def test_known_statuses(self, input_status, expected):
        assert _map_status(input_status) == expected

    def test_unknown_status_falls_back_to_new(self):
        assert _map_status("whatever") == "new"
        assert _map_status("") == "new"
        assert _map_status("pending") == "new"


# ---------------------------------------------------------------------------
# _map_order_method
# ---------------------------------------------------------------------------

class TestMapOrderMethod:
    @pytest.mark.parametrize("input_method,expected", [
        ("shopping-cart", "shopping-cart"),
        ("cart",          "shopping-cart"),
        ("online",        "shopping-cart"),
        ("phone",         "phone"),
        ("callback",      "phone"),
        ("one-click",     "one-click"),
        ("landing-page",  "landing-page"),
        ("landing",       "landing-page"),
        ("offline",       "offline"),
        ("app",           "app"),
        ("live-chat",     "live-chat"),
        ("messenger",     "messenger"),
    ])
    def test_known_methods(self, input_method, expected):
        assert _map_order_method(input_method) == expected

    def test_unknown_method_falls_back_to_shopping_cart(self):
        assert _map_order_method("unknown-channel") == "shopping-cart"
        assert _map_order_method("") == "shopping-cart"


# ---------------------------------------------------------------------------
# upsert_order
# ---------------------------------------------------------------------------

class TestUpsertOrder:
    """
    httpx.Client передаётся снаружи в upsert_order,
    но функция вызывает create_order / edit_order — патчим их напрямую.
    """

    def test_201_returns_created(self, crm_payload, crm_config):
        with patch("upload_to_crm.create_order") as mock_create:
            mock_create.return_value = (201, {"success": True, "id": 99})
            action, success = upsert_order(MagicMock(), crm_config, crm_payload)

        assert action == "created"
        assert success is True
        mock_create.assert_called_once()

    def test_460_triggers_edit_and_returns_updated(self, crm_payload, crm_config):
        with patch("upload_to_crm.create_order") as mock_create, \
             patch("upload_to_crm.edit_order") as mock_edit:
            mock_create.return_value = (460, {"success": False})
            mock_edit.return_value = (200, {"success": True})

            action, success = upsert_order(MagicMock(), crm_config, crm_payload)

        assert action == "updated"
        assert success is True
        mock_edit.assert_called_once()

    def test_edit_failure_after_460_returns_error(self, crm_payload, crm_config):
        with patch("upload_to_crm.create_order") as mock_create, \
             patch("upload_to_crm.edit_order") as mock_edit:
            mock_create.return_value = (460, {"success": False})
            mock_edit.return_value = (400, {"success": False, "errorMsg": "bad request"})

            action, success = upsert_order(MagicMock(), crm_config, crm_payload)

        assert action == "error"
        assert success is False

    def test_unexpected_error_response_returns_error(self, crm_payload, crm_config):
        with patch("upload_to_crm.create_order") as mock_create:
            mock_create.return_value = (500, {"success": False, "errorMsg": "server error"})
            action, success = upsert_order(MagicMock(), crm_config, crm_payload)

        assert action == "error"
        assert success is False

    def test_http_exception_returns_error(self, crm_payload, crm_config):
        import httpx
        with patch("upload_to_crm.create_order") as mock_create:
            mock_create.side_effect = httpx.ConnectError("connection refused")
            action, success = upsert_order(MagicMock(), crm_config, crm_payload)

        assert action == "error"
        assert success is False

    def test_already_exists_error_message_triggers_edit(self, crm_payload, crm_config):
        """Ответ 400 с 'already exists' в errorMsg тоже должен идти в edit."""
        with patch("upload_to_crm.create_order") as mock_create, \
             patch("upload_to_crm.edit_order") as mock_edit:
            mock_create.return_value = (
                400, {"success": False, "errorMsg": "Order already exists"}
            )
            mock_edit.return_value = (200, {"success": True})

            action, success = upsert_order(MagicMock(), crm_config, crm_payload)

        assert action == "updated"
        assert success is True
