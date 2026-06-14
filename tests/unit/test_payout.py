"""Payout capability specs (S79 Slice 2) — TrueMoney wallet transfer.

RED-first oracle for the `PayoutProvider` contract on TrueMoney:
- `TrueMoneySDKAdapter.create_wallet_transfer` issues an HMAC-signed
  POST (the adapter's existing signing convention) carrying the msisdn,
  THB amount and the caller's reference id.
- `TrueMoneyPlugin.create_payout` maps adapter responses to
  `PayoutResult`, refuses non-THB, and maps every failure to the typed
  `PayoutError`.
"""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from vbwd.plugins.payment_provider import PayoutError, PayoutProvider, PayoutResult
from vbwd.sdk.interface import SDKResponse


REFERENCE_ID = "withdraw-req-789"
RECEIVER_MSISDN = "+66912345678"


class TestCreateWalletTransfer:
    def test_posts_signed_transfer_shape(self, adapter, mocker):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {"transfer_id": "TMN-TR-1", "status": "PROCESSING"}
        mock_post = mocker.patch(
            "plugins.truemoney.truemoney.sdk_adapter.requests.post",
            return_value=fake,
        )

        response = adapter.create_wallet_transfer(
            amount=Decimal("123.45"),
            msisdn=RECEIVER_MSISDN,
            reference_id=REFERENCE_ID,
        )

        assert response.success is True
        assert response.data["transfer_id"] == "TMN-TR-1"

        call = mock_post.call_args
        assert call.args[0].endswith("/transfers")
        # Signed per the adapter's convention: canonical JSON body +
        # X-Signature HMAC header.
        headers = call.kwargs["headers"]
        assert headers["X-Merchant-Id"] == "TMN-TEST-001"
        assert headers["X-Signature"] == adapter._hmac(call.kwargs["data"].encode())
        body = call.kwargs["data"]
        assert '"msisdn":"+66912345678"' in body
        assert '"amount":"123.45"' in body
        assert '"currency":"THB"' in body
        assert f'"reference_id":"{REFERENCE_ID}"' in body

    def test_provider_error_maps_to_failed_sdk_response(self, adapter, mocker):
        fake = MagicMock()
        fake.status_code = 400
        fake.json.return_value = {"message": "wallet_not_found"}
        mocker.patch(
            "plugins.truemoney.truemoney.sdk_adapter.requests.post",
            return_value=fake,
        )

        response = adapter.create_wallet_transfer(
            amount=Decimal("1.00"),
            msisdn=RECEIVER_MSISDN,
            reference_id=REFERENCE_ID,
        )

        assert response.success is False
        assert "wallet_not_found" in response.error

    def test_network_error_maps_to_failed_sdk_response(self, adapter, mocker):
        import requests

        mocker.patch(
            "plugins.truemoney.truemoney.sdk_adapter.requests.post",
            side_effect=requests.ConnectionError("down"),
        )

        response = adapter.create_wallet_transfer(
            amount=Decimal("1.00"),
            msisdn=RECEIVER_MSISDN,
            reference_id=REFERENCE_ID,
        )

        assert response.success is False
        assert "network" in response.error


class TestGetTransferStatus:
    def test_gets_signed_status_lookup(self, adapter, mocker):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {"transfer_id": "TMN-TR-1", "status": "SUCCESS"}
        mock_get = mocker.patch(
            "plugins.truemoney.truemoney.sdk_adapter.requests.get",
            return_value=fake,
        )

        response = adapter.get_transfer_status("TMN-TR-1")

        assert response.success is True
        assert response.data["status"] == "SUCCESS"
        assert mock_get.call_args.args[0].endswith("/transfers/TMN-TR-1")


class TestTrueMoneyPluginPayout:
    def _plugin_with_adapter(self, adapter_mock):
        from plugins.truemoney import TrueMoneyPlugin

        plugin = TrueMoneyPlugin()
        plugin._get_adapter = lambda: adapter_mock
        return plugin

    def test_plugin_is_a_payout_provider(self):
        from plugins.truemoney import TrueMoneyPlugin

        assert issubclass(TrueMoneyPlugin, PayoutProvider)

    def test_destination_schema(self):
        from plugins.truemoney import TrueMoneyPlugin

        assert TrueMoneyPlugin().get_payout_destination_schema() == [
            {
                "name": "msisdn",
                "type": "tel",
                "label_key": "withdraw.destination.truemoney_msisdn",
            }
        ]

    def test_create_payout_returns_processing_result(self):
        adapter_mock = MagicMock()
        adapter_mock.create_wallet_transfer.return_value = SDKResponse(
            success=True, data={"transfer_id": "TMN-TR-1", "status": "PROCESSING"}
        )
        plugin = self._plugin_with_adapter(adapter_mock)

        result = plugin.create_payout(
            amount=Decimal("123.45"),
            currency="THB",
            destination={"msisdn": RECEIVER_MSISDN},
            reference_id=REFERENCE_ID,
        )

        assert isinstance(result, PayoutResult)
        assert result.provider_payout_id == "TMN-TR-1"
        assert result.status == "processing"
        adapter_mock.create_wallet_transfer.assert_called_once_with(
            amount=Decimal("123.45"),
            msisdn=RECEIVER_MSISDN,
            reference_id=REFERENCE_ID,
        )

    def test_create_payout_non_thb_raises_payout_error(self):
        adapter_mock = MagicMock()
        plugin = self._plugin_with_adapter(adapter_mock)

        with pytest.raises(PayoutError):
            plugin.create_payout(
                amount=Decimal("12.34"),
                currency="EUR",
                destination={"msisdn": RECEIVER_MSISDN},
                reference_id=REFERENCE_ID,
            )
        adapter_mock.create_wallet_transfer.assert_not_called()

    def test_create_payout_without_msisdn_raises_payout_error(self):
        plugin = self._plugin_with_adapter(MagicMock())

        with pytest.raises(PayoutError):
            plugin.create_payout(
                amount=Decimal("12.34"),
                currency="THB",
                destination={},
                reference_id=REFERENCE_ID,
            )

    def test_create_payout_provider_failure_raises_payout_error(self):
        adapter_mock = MagicMock()
        adapter_mock.create_wallet_transfer.return_value = SDKResponse(
            success=False, error="wallet_not_found"
        )
        plugin = self._plugin_with_adapter(adapter_mock)

        with pytest.raises(PayoutError):
            plugin.create_payout(
                amount=Decimal("12.34"),
                currency="THB",
                destination={"msisdn": RECEIVER_MSISDN},
                reference_id=REFERENCE_ID,
            )

    @pytest.mark.parametrize(
        "provider_status,expected",
        [
            ("SUCCESS", "completed"),
            ("PENDING", "processing"),
            ("PROCESSING", "processing"),
            ("FAILED", "failed"),
            ("CANCELLED", "failed"),
        ],
    )
    def test_get_payout_status_maps_provider_status(self, provider_status, expected):
        adapter_mock = MagicMock()
        adapter_mock.get_transfer_status.return_value = SDKResponse(
            success=True, data={"status": provider_status}
        )
        plugin = self._plugin_with_adapter(adapter_mock)

        assert plugin.get_payout_status("TMN-TR-1") == expected

    def test_get_payout_status_failure_raises_payout_error(self):
        adapter_mock = MagicMock()
        adapter_mock.get_transfer_status.return_value = SDKResponse(
            success=False, error="not_found"
        )
        plugin = self._plugin_with_adapter(adapter_mock)

        with pytest.raises(PayoutError):
            plugin.get_payout_status("TMN-missing")
