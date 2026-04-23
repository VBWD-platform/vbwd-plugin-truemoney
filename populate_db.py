"""Idempotent demo data for the TrueMoney plugin."""
from decimal import Decimal

from vbwd.extensions import db

from plugins.truemoney.truemoney.models import TrueMoneyTransaction


def populate_db() -> None:
    existing = (
        db.session.query(TrueMoneyTransaction)
        .filter_by(invoice_no="DEMO-TMN-0001")
        .one_or_none()
    )
    if existing is not None:
        return

    db.session.add(
        TrueMoneyTransaction(
            invoice_no="DEMO-TMN-0001",
            merchant_id="TMN-DEMO",
            transaction_id="TMN-TX-DEMO-1",
            amount=Decimal("99.00"),
            currency="THB",
            qr_payload="00020101021129370016A00000067701011101080TMN-DEMO...",
            status="completed",
            last_provider_status="SUCCESS",
            extra_data={"demo": True},
        )
    )
    db.session.commit()


if __name__ == "__main__":
    populate_db()
