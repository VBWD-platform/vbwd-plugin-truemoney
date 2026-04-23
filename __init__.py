"""TrueMoney Wallet plugin — Thailand direct-settlement QR + deep-link."""
from typing import Optional, Dict, Any, TYPE_CHECKING
from decimal import Decimal
from uuid import UUID

from vbwd.plugins.base import PluginMetadata
from vbwd.plugins.payment_provider import (
    PaymentProviderPlugin,
    PaymentResult,
    PaymentStatus,
)

if TYPE_CHECKING:
    from flask import Blueprint


DEFAULT_CONFIG = {
    "sandbox": True,
    "test_merchant_id": "",
    "test_secret_key": "",
    "test_api_url": "https://sandbox-api.truemoney.com/payment/v1",
    "live_merchant_id": "",
    "live_secret_key": "",
    "live_api_url": "https://api.truemoney.com/payment/v1",
    "qr_expiry_minutes": 15,
    "currency": "THB",
}


class TrueMoneyPlugin(PaymentProviderPlugin):
    """TrueMoney Wallet direct — THB-only, QR + deep-link.

    Class MUST live in __init__.py (not re-exported) per plugin-discovery
    rule.
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="truemoney",
            version="1.0.0",
            author="VBWD Team",
            description=(
                "TrueMoney Wallet (Thailand) — direct-settlement QR + "
                "deep-link flow, HMAC-signed API, bank-webhook "
                "reconciliation."
            ),
            dependencies=[],
        )

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        merged = {**DEFAULT_CONFIG}
        if config:
            merged.update(config)
        super().initialize(merged)

    def get_blueprint(self) -> Optional["Blueprint"]:
        from plugins.truemoney.truemoney.routes import truemoney_plugin_bp

        return truemoney_plugin_bp

    def get_url_prefix(self) -> Optional[str]:
        return "/api/v1/plugins/truemoney"

    @property
    def admin_permissions(self):
        return [
            {
                "key": "payments.configure",
                "label": "Payment provider settings",
                "group": "Payments",
            },
        ]

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def _get_adapter(self):
        from flask import current_app
        from plugins.truemoney.truemoney.sdk_adapter import TrueMoneySDKAdapter
        from vbwd.sdk.interface import SDKConfig

        config_store = current_app.config_store
        config = config_store.get_config("truemoney")
        prefix = "test_" if config.get("sandbox", True) else "live_"
        return TrueMoneySDKAdapter(
            SDKConfig(
                api_key=config.get(f"{prefix}secret_key", ""),
                sandbox=config.get("sandbox", True),
            ),
            merchant_id=config.get(f"{prefix}merchant_id", ""),
            api_url=config.get(
                f"{prefix}api_url", DEFAULT_CONFIG[f"{prefix}api_url"]
            ),
        )

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        subscription_id: UUID,
        user_id: UUID,
        metadata: Optional[Dict[str, Any]] = None,
        capture: bool = True,
    ) -> PaymentResult:
        if currency.upper() != "THB":
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error_message=f"TrueMoney supports THB only, got {currency}",
            )

        adapter = self._get_adapter()
        response = adapter.create_transaction(
            amount=amount,
            invoice_no=str(subscription_id),
            user_id=str(user_id),
            metadata=metadata or {},
        )
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        return PaymentResult(
            success=True,
            transaction_id=response.data.get("transaction_id"),
            status=PaymentStatus.PENDING,
            metadata={
                "qr_payload": response.data.get("qr_payload"),
                "deep_link": response.data.get("deep_link"),
                "expires_at": response.data.get("expires_at"),
            },
        )

    def capture_payment(
        self, payment_id: str, amount: Optional[Decimal] = None
    ) -> PaymentResult:
        adapter = self._get_adapter()
        response = adapter.get_transaction_status(payment_id)
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        status = _map_truemoney_status(response.data.get("status", ""))
        return PaymentResult(
            success=status == PaymentStatus.COMPLETED,
            transaction_id=payment_id,
            status=status,
        )

    def release_authorization(self, payment_id: str) -> PaymentResult:
        return PaymentResult(
            success=False,
            status=PaymentStatus.FAILED,
            error_message="TrueMoney does not support authorization hold",
        )

    def process_payment(
        self, payment_intent_id: str, payment_method: str
    ) -> PaymentResult:
        return self.capture_payment(payment_intent_id)

    def refund_payment(
        self, transaction_id: str, amount: Optional[Decimal] = None
    ) -> PaymentResult:
        adapter = self._get_adapter()
        response = adapter.refund_payment(
            payment_intent_id=transaction_id, amount=amount
        )
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        return PaymentResult(
            success=True,
            transaction_id=transaction_id,
            status=PaymentStatus.REFUNDED,
        )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        adapter = self._get_adapter()
        return adapter.verify_webhook(payload, signature)

    def handle_webhook(self, payload: Dict[str, Any]) -> None:
        from plugins.truemoney.truemoney.services import TrueMoneyWebhookHandler

        handler = TrueMoneyWebhookHandler()
        handler.handle(payload)


def _map_truemoney_status(status: str) -> PaymentStatus:
    """Map TrueMoney transaction status to VBWD PaymentStatus."""
    mapping = {
        "SUCCESS": PaymentStatus.COMPLETED,
        "PENDING": PaymentStatus.PENDING,
        "PROCESSING": PaymentStatus.PROCESSING,
        "EXPIRED": PaymentStatus.FAILED,
        "CANCELLED": PaymentStatus.CANCELLED,
        "FAILED": PaymentStatus.FAILED,
        "REFUNDED": PaymentStatus.REFUNDED,
    }
    return mapping.get(status.upper(), PaymentStatus.FAILED)
