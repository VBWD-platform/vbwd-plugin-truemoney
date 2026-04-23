"""TrueMoney payment transaction model."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Numeric, String

from vbwd.extensions import db


class TrueMoneyTransaction(db.Model):
    __tablename__ = "truemoney_transactions"

    id = Column(
        db.UUID,
        primary_key=True,
        server_default=db.text("gen_random_uuid()"),
    )
    invoice_no = Column(String(64), nullable=False, unique=True, index=True)
    merchant_id = Column(String(64), nullable=False)
    transaction_id = Column(String(128), nullable=True, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="THB")
    qr_payload = Column(String(512), nullable=True)
    deep_link = Column(String(512), nullable=True)
    status = Column(String(24), nullable=False, default="pending")
    last_provider_status = Column(String(24), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    extra_data = Column(db.JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "invoice_no": self.invoice_no,
            "merchant_id": self.merchant_id,
            "transaction_id": self.transaction_id,
            "amount": str(self.amount),
            "currency": self.currency,
            "qr_payload": self.qr_payload,
            "deep_link": self.deep_link,
            "status": self.status,
            "last_provider_status": self.last_provider_status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
