"""TrueMoney services — domain mapping + webhook handling."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from vbwd.extensions import db

from plugins.truemoney.truemoney.models import TrueMoneyTransaction


STATUS_MAP = {
    "SUCCESS": "completed",
    "PENDING": "pending",
    "PROCESSING": "processing",
    "EXPIRED": "expired",
    "CANCELLED": "cancelled",
    "FAILED": "failed",
    "REFUNDED": "refunded",
}


def map_provider_status(provider_status: str) -> str:
    return STATUS_MAP.get(provider_status.upper(), "failed")


class TrueMoneyService:
    """Ingest TrueMoney responses into TrueMoneyTransaction domain."""

    def __init__(self, session=None):
        self._session = session or db.session

    def record_transaction_created(
        self,
        invoice_no: str,
        merchant_id: str,
        transaction_id: str,
        amount: Decimal,
        qr_payload: Optional[str] = None,
        deep_link: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> TrueMoneyTransaction:
        tx = self._get_or_create(invoice_no)
        tx.merchant_id = merchant_id
        tx.transaction_id = transaction_id
        tx.amount = amount
        tx.currency = "THB"
        tx.qr_payload = qr_payload
        tx.deep_link = deep_link
        tx.expires_at = expires_at
        tx.status = "pending"
        tx.extra_data = extra_data
        self._session.add(tx)
        self._session.commit()
        return tx

    def apply_provider_update(
        self, invoice_no: str, provider_payload: Dict[str, Any]
    ) -> TrueMoneyTransaction:
        tx = self._get_or_create(invoice_no)
        provider_status = provider_payload.get("status", "")
        new_status = map_provider_status(provider_status)

        if tx.status == new_status and tx.last_provider_status == provider_status:
            return tx

        tx.last_provider_status = provider_status
        tx.status = new_status
        if provider_payload.get("transaction_id"):
            tx.transaction_id = provider_payload["transaction_id"]
        self._session.commit()
        return tx

    def _get_or_create(self, invoice_no: str) -> TrueMoneyTransaction:
        tx = (
            self._session.query(TrueMoneyTransaction)
            .filter_by(invoice_no=invoice_no)
            .one_or_none()
        )
        if tx is None:
            tx = TrueMoneyTransaction(
                invoice_no=invoice_no,
                merchant_id="",
                amount=Decimal("0"),
                currency="THB",
            )
        return tx


class TrueMoneyWebhookHandler:
    """Webhook handler — idempotent on (invoice_no, provider_status)."""

    def __init__(self, service: Optional[TrueMoneyService] = None):
        self._service = service or TrueMoneyService()

    def handle(self, payload: Dict[str, Any]) -> TrueMoneyTransaction:
        invoice_no = payload.get("invoice_no") or payload.get("invoiceNo")
        if not invoice_no:
            raise ValueError("missing invoice_no in TrueMoney webhook")
        return self._service.apply_provider_update(invoice_no, payload)
