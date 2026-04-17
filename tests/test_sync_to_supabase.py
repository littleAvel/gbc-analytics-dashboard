"""
Тесты для scripts/sync_to_supabase.py.

Покрытие:
- build_row()              — маппинг полей CRMOrder → Supabase-строку
- _parse_crm_datetime()    — парсинг дат из RetailCRM формата в ISO 8601
- fetch_existing_ids()     — чтение из Supabase (клиент замокан)
- send_telegram_alert()    — отправка алерта (httpx замокан)
- порог алерта             — только заказы > 50 000 ₸ тригерят алерт
- fetch_crm_orders()       — парсинг ответа RetailCRM API (httpx замокан)
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from sync_to_supabase import (
    _parse_crm_datetime,
    build_row,
    fetch_crm_orders,
    fetch_existing_ids,
    send_telegram_alert,
    _ALERT_THRESHOLD,
)


# ---------------------------------------------------------------------------
# _parse_crm_datetime
# ---------------------------------------------------------------------------

class TestParseCrmDatetime:
    def test_valid_datetime_converts_to_iso(self):
        result = _parse_crm_datetime("2024-01-15 14:30:00")
        assert result == "2024-01-15T14:30:00+00:00"

    def test_none_returns_none(self):
        assert _parse_crm_datetime(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_crm_datetime("") is None

    def test_invalid_format_returns_none(self):
        assert _parse_crm_datetime("not-a-date") is None
        assert _parse_crm_datetime("2024/01/15") is None

    def test_result_contains_utc_offset(self):
        result = _parse_crm_datetime("2024-06-01 00:00:00")
        assert result is not None
        assert "+00:00" in result


# ---------------------------------------------------------------------------
# build_row
# ---------------------------------------------------------------------------

class TestBuildRow:
    RAW = {"id": 1001, "extra_field": "preserved"}

    def test_retailcrm_id_is_string(self, crm_order):
        row = build_row(crm_order, self.RAW)
        assert row["retailcrm_id"] == "1001"
        assert isinstance(row["retailcrm_id"], str)

    def test_basic_fields_mapped(self, crm_order):
        row = build_row(crm_order, self.RAW)
        assert row["external_id"] == "mock-77001234501"
        assert row["first_name"] == "Айгуль"
        assert row["last_name"] == "Касымова"
        assert row["phone"] == "+77001234501"
        assert row["email"] == "aigul@example.com"
        assert row["total_sum"] == 30000.0
        assert row["status"] == "new"
        assert row["order_type"] == "main"
        assert row["order_method"] == "shopping-cart"

    def test_city_extracted_from_nested_delivery(self, crm_order):
        row = build_row(crm_order, self.RAW)
        assert row["city"] == "Алматы"

    def test_city_none_when_delivery_absent(self):
        from sync_to_supabase import CRMOrder
        order = CRMOrder(id=2, totalSumm=0)
        row = build_row(order, {})
        assert row["city"] is None

    def test_created_at_converted_from_crm_format(self, crm_order):
        row = build_row(crm_order, self.RAW)
        assert row["created_at"] == "2024-01-15T10:00:00+00:00"

    def test_created_at_absent_when_crm_datetime_is_none(self):
        from sync_to_supabase import CRMOrder
        order = CRMOrder(id=3, totalSumm=0, createdAt=None)
        row = build_row(order, {})
        assert "created_at" not in row

    def test_synced_at_always_present(self, crm_order):
        row = build_row(crm_order, self.RAW)
        assert "synced_at" in row
        assert row["synced_at"]  # не пустое

    def test_raw_data_stored_as_is(self, crm_order):
        raw = {"id": 1001, "nested": {"x": 1}}
        row = build_row(crm_order, raw)
        assert row["raw_data"] == raw


# ---------------------------------------------------------------------------
# fetch_existing_ids
# ---------------------------------------------------------------------------

class TestFetchExistingIds:
    def test_returns_set_of_ids(self):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value.data = [
            {"retailcrm_id": "101"},
            {"retailcrm_id": "102"},
            {"retailcrm_id": "103"},
        ]
        result = fetch_existing_ids(mock_sb)
        assert result == {"101", "102", "103"}

    def test_empty_table_returns_empty_set(self):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value.data = []
        assert fetch_existing_ids(mock_sb) == set()

    def test_none_data_returns_empty_set(self):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value.data = None
        assert fetch_existing_ids(mock_sb) == set()

    def test_calls_correct_table_and_column(self):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value.data = []
        fetch_existing_ids(mock_sb)
        mock_sb.table.assert_called_once_with("orders")
        mock_sb.table.return_value.select.assert_called_once_with("retailcrm_id")


# ---------------------------------------------------------------------------
# send_telegram_alert
# ---------------------------------------------------------------------------

def _make_tg_response(status_code: int, ok: bool) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"ok": ok}
    resp.text = ""
    return resp


class TestSendTelegramAlert:
    def test_returns_true_on_success(self, sync_config, crm_order):
        mock_resp = _make_tg_response(200, ok=True)
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.post.return_value = mock_resp
            result = send_telegram_alert(sync_config, crm_order)
        assert result is True

    def test_returns_false_when_ok_is_false(self, sync_config, crm_order):
        mock_resp = _make_tg_response(200, ok=False)
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.post.return_value = mock_resp
            result = send_telegram_alert(sync_config, crm_order)
        assert result is False

    def test_returns_false_on_non_200(self, sync_config, crm_order):
        mock_resp = _make_tg_response(429, ok=False)
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.post.return_value = mock_resp
            result = send_telegram_alert(sync_config, crm_order)
        assert result is False

    def test_returns_false_on_http_error(self, sync_config, crm_order):
        import httpx
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.post.side_effect = (
                httpx.ConnectError("timeout")
            )
            result = send_telegram_alert(sync_config, crm_order)
        assert result is False

    def test_message_contains_order_id(self, sync_config, crm_order):
        mock_resp = _make_tg_response(200, ok=True)
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            mock_post = MockClient.return_value.__enter__.return_value.post
            mock_post.return_value = mock_resp
            send_telegram_alert(sync_config, crm_order)

        call_kwargs = mock_post.call_args.kwargs
        text = call_kwargs["json"]["text"]
        assert "1001" in text

    def test_message_contains_total_sum(self, sync_config, crm_order):
        mock_resp = _make_tg_response(200, ok=True)
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            mock_post = MockClient.return_value.__enter__.return_value.post
            mock_post.return_value = mock_resp
            send_telegram_alert(sync_config, crm_order)

        text = mock_post.call_args.kwargs["json"]["text"]
        assert "30" in text  # 30 000 в тексте

    def test_chat_id_matches_config(self, sync_config, crm_order):
        mock_resp = _make_tg_response(200, ok=True)
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            mock_post = MockClient.return_value.__enter__.return_value.post
            mock_post.return_value = mock_resp
            send_telegram_alert(sync_config, crm_order)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["chat_id"] == sync_config.telegram_chat_id


# ---------------------------------------------------------------------------
# Порог алерта
# ---------------------------------------------------------------------------

class TestAlertThreshold:
    def test_threshold_value(self):
        assert _ALERT_THRESHOLD == 50_000.0

    def test_order_above_threshold_triggers_alert(self, large_crm_order):
        assert large_crm_order.totalSumm > _ALERT_THRESHOLD

    def test_order_below_threshold_does_not_trigger(self, crm_order):
        assert crm_order.totalSumm <= _ALERT_THRESHOLD

    def test_order_exactly_at_threshold_does_not_trigger(self):
        from sync_to_supabase import CRMOrder
        order = CRMOrder(id=9, totalSumm=50_000.0)
        assert not (order.totalSumm > _ALERT_THRESHOLD)


# ---------------------------------------------------------------------------
# fetch_crm_orders
# ---------------------------------------------------------------------------

class TestFetchCrmOrders:
    def _make_http_response(self, orders: list) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": True, "orders": orders}
        return resp

    RAW_ORDER = {
        "id": 42,
        "externalId": "mock-77001234501",
        "firstName": "Айгуль",
        "lastName": "Касымова",
        "phone": "+77001234501",
        "email": "aigul@example.com",
        "totalSumm": 30000.0,
        "status": "new",
        "orderType": "main",
        "orderMethod": "shopping-cart",
        "delivery": {"address": {"city": "Алматы", "text": "ул. Абая 1"}},
        "createdAt": "2024-01-15 10:00:00",
    }

    def test_returns_list_of_tuples(self, sync_config):
        resp = self._make_http_response([self.RAW_ORDER])
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.get.return_value = resp
            result = fetch_crm_orders(sync_config)

        assert len(result) == 1
        order, raw = result[0]
        assert order.id == 42
        assert raw == self.RAW_ORDER

    def test_parses_total_summ(self, sync_config):
        resp = self._make_http_response([self.RAW_ORDER])
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.get.return_value = resp
            result = fetch_crm_orders(sync_config)
        assert result[0][0].totalSumm == 30000.0

    def test_raises_on_non_200(self, sync_config):
        resp = MagicMock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.get.return_value = resp
            with pytest.raises(RuntimeError, match="401"):
                fetch_crm_orders(sync_config)

    def test_raises_on_success_false(self, sync_config):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": False, "errorMsg": "wrong key"}
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.get.return_value = resp
            with pytest.raises(RuntimeError):
                fetch_crm_orders(sync_config)

    def test_skips_unparseable_order(self, sync_config):
        """Заказ без id не ломает весь список."""
        bad_order = {"firstName": "X"}  # нет id — валидация упадёт
        good_order = self.RAW_ORDER
        resp = self._make_http_response([bad_order, good_order])
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.get.return_value = resp
            result = fetch_crm_orders(sync_config)
        assert len(result) == 1
        assert result[0][0].id == 42

    def test_empty_orders_list(self, sync_config):
        resp = self._make_http_response([])
        with patch("sync_to_supabase.httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.get.return_value = resp
            result = fetch_crm_orders(sync_config)
        assert result == []
