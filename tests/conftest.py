"""Shared fixtures for TrueMoney plugin tests."""
import pytest

from vbwd.sdk.interface import SDKConfig


@pytest.fixture
def truemoney_config() -> dict:
    return {
        "test_merchant_id": "TMN-TEST-001",
        "test_secret_key": "secret-abc-123",
        "test_api_url": "https://sandbox-api.truemoney.com/payment/v1",
        "sandbox": True,
        "qr_expiry_minutes": 15,
        "currency": "THB",
    }


@pytest.fixture
def sdk_config(truemoney_config) -> SDKConfig:
    return SDKConfig(
        api_key=truemoney_config["test_secret_key"],
        sandbox=truemoney_config["sandbox"],
    )


@pytest.fixture
def adapter(sdk_config, truemoney_config):
    from plugins.truemoney.truemoney.sdk_adapter import TrueMoneySDKAdapter

    return TrueMoneySDKAdapter(
        config=sdk_config,
        merchant_id=truemoney_config["test_merchant_id"],
        api_url=truemoney_config["test_api_url"],
    )
