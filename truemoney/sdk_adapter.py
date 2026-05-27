"""TrueMoney Wallet SDK adapter — HMAC-signed REST client."""
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import requests

from vbwd.sdk.base import BaseSDKAdapter
from vbwd.sdk.errors import UnsupportedOperationError
from vbwd.sdk.interface import SDKConfig, SDKResponse


class TrueMoneySDKAdapter(BaseSDKAdapter):
    """TrueMoney Wallet adapter.

    Liskov: every ISDKAdapter postcondition holds — SDKResponse.success
    reflects adapter success; error is populated on failure.
    """

    def __init__(
        self,
        config: SDKConfig,
        merchant_id: str,
        api_url: str,
        idempotency_service=None,
        qr_expiry_minutes: int = 15,
    ):
        super().__init__(config, idempotency_service)
        self._merchant_id = merchant_id
        self._api_url = api_url.rstrip("/")
        self._secret_key = config.api_key
        self._qr_expiry_minutes = qr_expiry_minutes

    @property
    def provider_name(self) -> str:
        return "truemoney"

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        invoice_no = metadata.get("invoice_no", "")
        user_id = metadata.get("user_id", "")
        return self.create_transaction(
            amount=amount,
            invoice_no=invoice_no,
            user_id=user_id,
            metadata=metadata,
        )

    def capture_payment(
        self,
        payment_intent_id: str,
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        return self.get_transaction_status(payment_intent_id)

    def release_authorization(self, payment_intent_id: str) -> SDKResponse:
        # S11 — Liskov: structural inability is an exception, not success=False.
        raise UnsupportedOperationError(
            "TrueMoney does not support authorization hold"
        )

    def get_payment_status(self, payment_intent_id: str) -> SDKResponse:
        return self.get_transaction_status(payment_intent_id)

    def create_transaction(
        self,
        amount: Decimal,
        invoice_no: str,
        user_id: str,
        metadata: Dict[str, Any],
    ) -> SDKResponse:
        """Issue a TrueMoney payment request.

        Returns `{ transaction_id, qr_payload, deep_link, expires_at }`.
        """
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self._qr_expiry_minutes
        )
        body = {
            "merchant_id": self._merchant_id,
            "invoice_no": invoice_no,
            "amount": str(amount),
            "currency": "THB",
            "user_reference": user_id,
            "return_url": metadata.get("return_url", ""),
            "callback_url": metadata.get("callback_url", ""),
            "expires_at": expires_at.isoformat(),
            "nonce": uuid.uuid4().hex,
            "ts": int(time.time()),
        }
        return self._signed_post("/transactions", body)

    def get_transaction_status(self, transaction_id: str) -> SDKResponse:
        return self._signed_get(f"/transactions/{transaction_id}")

    def refund_payment(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        body: Dict[str, Any] = {
            "transaction_id": payment_intent_id,
            "nonce": uuid.uuid4().hex,
            "ts": int(time.time()),
        }
        if amount is not None:
            body["amount"] = str(amount)
        return self._signed_post(f"/transactions/{payment_intent_id}/refund", body)

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        expected = self._hmac(payload)
        return hmac.compare_digest(expected, signature or "")

    def render_qr_payload(
        self, merchant_id: str, amount: Decimal, reference: str
    ) -> str:
        """Render a TrueMoney QR payload per the merchant QR spec.

        Uses the Thai EMVCo standard (NAPAS QR since 2023) with
        TrueMoney's tag-29 merchant ID + tag-54 amount + tag-62 reference.
        """
        parts = [
            _tlv("00", "01"),
            _tlv("01", "12"),
            _tlv("29", _tlv("00", "A0000006770101110") + _tlv("01", merchant_id)),
            _tlv("52", "0000"),
            _tlv("53", "764"),
            _tlv("54", f"{amount:.2f}"),
            _tlv("58", "TH"),
            _tlv("62", _tlv("01", reference)),
        ]
        payload = "".join(parts) + "6304"
        crc = _crc16_ccitt(payload.encode("ascii"))
        return payload + f"{crc:04X}"

    # ── internal helpers ───────────────────────────────────────────────

    def _signed_post(self, path: str, body: Dict[str, Any]) -> SDKResponse:
        canonical = json.dumps(body, separators=(",", ":"), sort_keys=True)
        signature = self._hmac(canonical.encode())
        try:
            resp = requests.post(
                f"{self._api_url}{path}",
                data=canonical,
                headers={
                    "Content-Type": "application/json",
                    "X-Merchant-Id": self._merchant_id,
                    "X-Signature": signature,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            return SDKResponse(success=False, error=f"network: {exc}")

        return self._parse(resp)

    def _signed_get(self, path: str) -> SDKResponse:
        canonical_query = f"GET {path} {int(time.time())}"
        signature = self._hmac(canonical_query.encode())
        try:
            resp = requests.get(
                f"{self._api_url}{path}",
                headers={
                    "X-Merchant-Id": self._merchant_id,
                    "X-Signature": signature,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            return SDKResponse(success=False, error=f"network: {exc}")

        return self._parse(resp)

    def _parse(self, resp: requests.Response) -> SDKResponse:
        if resp.status_code >= 500:
            return SDKResponse(
                success=False,
                error=f"TrueMoney {resp.status_code}: {resp.text[:200]}",
            )
        try:
            body = resp.json()
        except ValueError:
            return SDKResponse(success=False, error="invalid JSON from TrueMoney")

        if resp.status_code >= 400:
            return SDKResponse(
                success=False,
                data=body,
                error=body.get("message", f"HTTP {resp.status_code}"),
            )
        return SDKResponse(success=True, data=body)

    def _hmac(self, message: bytes) -> str:
        return hmac.new(self._secret_key.encode(), message, hashlib.sha256).hexdigest()


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """CRC16/CCITT-FALSE — Thai QR / EMVCo standard."""
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc
