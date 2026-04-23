"""TrueMoney plugin API routes."""
import logging
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request

from vbwd.middleware.auth import require_auth

from plugins.truemoney.truemoney.services import (
    TrueMoneyService,
    TrueMoneyWebhookHandler,
)

logger = logging.getLogger(__name__)

truemoney_plugin_bp = Blueprint("truemoney_plugin", __name__)


def _get_plugin():
    manager = current_app.plugin_manager
    plugin = manager.get_plugin("truemoney")
    if plugin is None:
        raise RuntimeError("truemoney plugin not enabled")
    return plugin


@truemoney_plugin_bp.route("/transactions", methods=["POST"])
@require_auth
def create_transaction():
    body = request.get_json(silent=True) or {}
    required = ("invoice_no", "amount")
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": "missing fields", "fields": missing}), 400

    try:
        amount = Decimal(str(body["amount"]))
    except (ValueError, ArithmeticError):
        return jsonify({"error": "invalid amount"}), 400

    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    response = adapter.create_transaction(
        amount=amount,
        invoice_no=body["invoice_no"],
        user_id=str(getattr(request, "user_id", "")),
        metadata={
            "return_url": body.get("return_url"),
            "callback_url": body.get("callback_url"),
        },
    )
    if not response.success:
        return jsonify({"error": response.error or "TrueMoney error"}), 502

    service = TrueMoneyService()
    from datetime import datetime

    expires_at = response.data.get("expires_at")
    expires_dt = None
    if expires_at:
        try:
            expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_dt = None

    service.record_transaction_created(
        invoice_no=body["invoice_no"],
        merchant_id=adapter._merchant_id,
        transaction_id=response.data.get("transaction_id", ""),
        amount=amount,
        qr_payload=response.data.get("qr_payload"),
        deep_link=response.data.get("deep_link"),
        expires_at=expires_dt,
        extra_data=response.data,
    )

    return (
        jsonify(
            {
                "transaction_id": response.data.get("transaction_id"),
                "qr_payload": response.data.get("qr_payload"),
                "deep_link": response.data.get("deep_link"),
                "expires_at": response.data.get("expires_at"),
            }
        ),
        201,
    )


@truemoney_plugin_bp.route("/transactions/<invoice_no>/status", methods=["GET"])
@require_auth
def get_transaction_status(invoice_no: str):
    from plugins.truemoney.truemoney.models import TrueMoneyTransaction
    from vbwd.extensions import db

    tx = (
        db.session.query(TrueMoneyTransaction)
        .filter_by(invoice_no=invoice_no)
        .one_or_none()
    )
    if tx is None:
        return jsonify({"error": "not found"}), 404

    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    response = adapter.get_transaction_status(tx.transaction_id)
    if response.success:
        TrueMoneyService().apply_provider_update(invoice_no, response.data)

    return jsonify(tx.to_dict()), 200


@truemoney_plugin_bp.route("/webhooks", methods=["POST"])
def webhook():
    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    signature = request.headers.get("X-Signature", "")
    if not adapter.verify_webhook(request.get_data(), signature):
        return jsonify({"error": "invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    handler = TrueMoneyWebhookHandler()
    handler.handle(payload)
    return "", 204


@truemoney_plugin_bp.route("/transactions/<invoice_no>/refund", methods=["POST"])
@require_auth
def refund(invoice_no: str):
    body = request.get_json(silent=True) or {}
    amount = body.get("amount")
    if amount is not None:
        try:
            amount = Decimal(str(amount))
        except (ValueError, ArithmeticError):
            return jsonify({"error": "invalid amount"}), 400

    plugin = _get_plugin()
    adapter = plugin._get_adapter()

    from plugins.truemoney.truemoney.models import TrueMoneyTransaction
    from vbwd.extensions import db

    tx = (
        db.session.query(TrueMoneyTransaction)
        .filter_by(invoice_no=invoice_no)
        .one_or_none()
    )
    if tx is None or not tx.transaction_id:
        return jsonify({"error": "not found"}), 404

    response = adapter.refund_payment(
        payment_intent_id=tx.transaction_id, amount=amount
    )
    if not response.success:
        return jsonify({"error": response.error or "TrueMoney error"}), 502
    return jsonify({"transaction_id": tx.transaction_id}), 200
