"""Unit tests for TrueMoneyService + TrueMoneyWebhookHandler."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from plugins.truemoney.truemoney.services import (
    TrueMoneyService,
    TrueMoneyWebhookHandler,
    map_provider_status,
)


class TestStatusMapping:
    @pytest.mark.parametrize(
        "provider,expected",
        [
            ("SUCCESS", "completed"),
            ("success", "completed"),
            ("PENDING", "pending"),
            ("PROCESSING", "processing"),
            ("EXPIRED", "expired"),
            ("CANCELLED", "cancelled"),
            ("FAILED", "failed"),
            ("REFUNDED", "refunded"),
            ("UNKNOWN", "failed"),
            ("", "failed"),
        ],
    )
    def test_maps(self, provider, expected):
        assert map_provider_status(provider) == expected


class TestService:
    def test_record_transaction_created(self):
        session = MagicMock()
        session.query.return_value.filter_by.return_value.one_or_none.return_value = (
            None
        )
        service = TrueMoneyService(session=session)

        tx = service.record_transaction_created(
            invoice_no="INV-1",
            merchant_id="TMN-TEST",
            transaction_id="TMN-TX-1",
            amount=Decimal("99"),
            qr_payload="00020101...",
        )

        assert tx.invoice_no == "INV-1"
        assert tx.transaction_id == "TMN-TX-1"
        assert tx.status == "pending"
        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_apply_provider_update_transitions(self):
        existing = MagicMock()
        existing.status = "pending"
        existing.last_provider_status = None
        session = MagicMock()
        session.query.return_value.filter_by.return_value.one_or_none.return_value = (
            existing
        )
        service = TrueMoneyService(session=session)

        service.apply_provider_update(
            "INV-1", {"status": "SUCCESS", "transaction_id": "TMN-TX-9"}
        )

        assert existing.status == "completed"
        assert existing.last_provider_status == "SUCCESS"
        assert existing.transaction_id == "TMN-TX-9"
        session.commit.assert_called()

    def test_apply_provider_update_idempotent(self):
        existing = MagicMock()
        existing.status = "completed"
        existing.last_provider_status = "SUCCESS"
        session = MagicMock()
        session.query.return_value.filter_by.return_value.one_or_none.return_value = (
            existing
        )
        service = TrueMoneyService(session=session)

        service.apply_provider_update("INV-1", {"status": "SUCCESS"})
        session.commit.assert_not_called()


class TestWebhookHandler:
    def test_rejects_missing_invoice(self):
        handler = TrueMoneyWebhookHandler(service=MagicMock())
        with pytest.raises(ValueError, match="invoice_no"):
            handler.handle({"status": "SUCCESS"})

    def test_handles_invoiceNo_camelCase(self):
        svc = MagicMock()
        handler = TrueMoneyWebhookHandler(service=svc)
        handler.handle({"invoiceNo": "INV-1", "status": "SUCCESS"})
        svc.apply_provider_update.assert_called_once()

    def test_handles_snake_case(self):
        svc = MagicMock()
        handler = TrueMoneyWebhookHandler(service=svc)
        handler.handle({"invoice_no": "INV-1", "status": "SUCCESS"})
        svc.apply_provider_update.assert_called_once()
