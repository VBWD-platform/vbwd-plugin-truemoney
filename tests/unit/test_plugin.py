"""Plugin-class tests — metadata + Liskov super().initialize + THB-only guard."""
from decimal import Decimal
from uuid import uuid4
from unittest.mock import MagicMock, patch

from vbwd.plugins.base import PluginStatus

from plugins.truemoney import TrueMoneyPlugin, DEFAULT_CONFIG


class TestTrueMoneyPlugin:
    def test_metadata(self):
        plugin = TrueMoneyPlugin()
        assert plugin.metadata.name == "truemoney"
        assert plugin.metadata.version == "26.6.1"

    def test_initialize_merges(self):
        plugin = TrueMoneyPlugin()
        plugin.initialize({"test_merchant_id": "TMN-X"})

        assert plugin.status == PluginStatus.INITIALIZED
        assert plugin._config["test_merchant_id"] == "TMN-X"
        assert plugin._config["currency"] == DEFAULT_CONFIG["currency"]

    def test_create_payment_intent_rejects_non_thb(self):
        plugin = TrueMoneyPlugin()
        plugin.initialize({})

        result = plugin.create_payment_intent(
            amount=Decimal("10"),
            currency="USD",
            subscription_id=uuid4(),
            user_id=uuid4(),
        )
        assert result.success is False
        assert "THB" in (result.error_message or "")

    def test_release_authorization_is_unsupported(self):
        plugin = TrueMoneyPlugin()
        plugin.initialize({})
        with patch.object(plugin, "_get_adapter", return_value=MagicMock()):
            result = plugin.release_authorization("TMN-TX-1")
        assert result.success is False
