"""Unit tests for TrueMoneySDKAdapter (TDD-first per sprint checkpoints)."""
from decimal import Decimal
from unittest.mock import MagicMock


class TestQrRenderer:
    def test_renders_non_empty(self, adapter):
        qr = adapter.render_qr_payload(
            merchant_id="TMN-TEST-001",
            amount=Decimal("123.45"),
            reference="INV-1",
        )
        assert qr
        assert "123.45" in qr

    def test_crc_trailing_hex(self, adapter):
        qr = adapter.render_qr_payload(
            merchant_id="TMN-TEST-001",
            amount=Decimal("100.00"),
            reference="INV-42",
        )
        crc = qr[-4:]
        assert all(c in "0123456789ABCDEF" for c in crc)


class TestHmacVerify:
    def test_accepts_correct_signature(self, adapter):
        payload = b'{"hello":"world"}'
        sig = adapter._hmac(payload)
        assert adapter.verify_webhook(payload, sig) is True

    def test_rejects_wrong_signature(self, adapter):
        payload = b'{"hello":"world"}'
        assert adapter.verify_webhook(payload, "deadbeef") is False

    def test_rejects_empty_signature(self, adapter):
        assert adapter.verify_webhook(b"anything", "") is False


class TestCreateTransaction:
    def test_success(self, adapter, mocker):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {
            "transaction_id": "TMN-TX-1",
            "qr_payload": "00020101...",
            "deep_link": "truemoney://pay?t=TMN-TX-1",
            "expires_at": "2026-04-22T13:00:00+00:00",
        }
        mocker.patch(
            "plugins.truemoney.truemoney.sdk_adapter.requests.post",
            return_value=fake,
        )

        resp = adapter.create_transaction(
            amount=Decimal("99.00"),
            invoice_no="INV-1",
            user_id="user-1",
            metadata={"return_url": "https://shop.test/return"},
        )
        assert resp.success is True
        assert resp.data["transaction_id"] == "TMN-TX-1"

    def test_network_error(self, adapter, mocker):
        import requests

        mocker.patch(
            "plugins.truemoney.truemoney.sdk_adapter.requests.post",
            side_effect=requests.ConnectionError("down"),
        )
        resp = adapter.create_transaction(
            amount=Decimal("1"),
            invoice_no="INV-1",
            user_id="user-1",
            metadata={},
        )
        assert resp.success is False
        assert "network" in (resp.error or "")

    def test_5xx_failure(self, adapter, mocker):
        fake = MagicMock()
        fake.status_code = 503
        fake.text = "upstream down"
        mocker.patch(
            "plugins.truemoney.truemoney.sdk_adapter.requests.post",
            return_value=fake,
        )
        resp = adapter.create_transaction(
            amount=Decimal("1"),
            invoice_no="INV-1",
            user_id="user-1",
            metadata={},
        )
        assert resp.success is False
        assert "503" in (resp.error or "")

    def test_4xx_returns_provider_message(self, adapter, mocker):
        fake = MagicMock()
        fake.status_code = 400
        fake.json.return_value = {"message": "invalid_merchant"}
        mocker.patch(
            "plugins.truemoney.truemoney.sdk_adapter.requests.post",
            return_value=fake,
        )
        resp = adapter.create_transaction(
            amount=Decimal("1"),
            invoice_no="INV-1",
            user_id="user-1",
            metadata={},
        )
        assert resp.success is False
        assert "invalid_merchant" in (resp.error or "")


class TestReleaseAuthorization:
    def test_raises_unsupported(self, adapter):
        """S11 — TrueMoney doesn't support authorization holds; the adapter
        must raise UnsupportedOperationError (not return success=False)."""
        import pytest

        from vbwd.sdk.errors import UnsupportedOperationError

        with pytest.raises(UnsupportedOperationError) as excinfo:
            adapter.release_authorization("TMN-TX-1")
        assert "authorization hold" in str(excinfo.value)
