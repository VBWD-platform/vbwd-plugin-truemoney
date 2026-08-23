# TrueMoney Plugin (Backend)

Direct TrueMoney Wallet integration for Thai merchants.

## Purpose

Implements `PaymentProviderPlugin` for TrueMoney. Covers QR-code
scan-at-desktop and mobile deep-link flows. HMAC-SHA256 signed
requests. THB-only (enforced at the plugin layer).

## Configuration (`plugins/config.json`)

```json
{
  "truemoney": {
    "sandbox": true,
    "test_merchant_id": "TMN-TEST-001",
    "test_secret_key": "…",
    "qr_expiry_minutes": 15
  }
}
```

## API Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/plugins/truemoney/transactions` | Bearer | Issue a transaction + QR + deep-link |
| GET | `/api/v1/plugins/truemoney/transactions/:invoice/status` | Bearer | Query/refresh status |
| POST | `/api/v1/plugins/truemoney/webhooks` | HMAC signature | TrueMoney webhook receiver |
| POST | `/api/v1/plugins/truemoney/transactions/:invoice/refund` | Admin | Refund (full or partial) |

## Database

Owns `truemoney_transactions` — one row per invoice; tracks provider
transaction_id, QR payload, deep-link, expiry, status.

## Frontend bundles

- User: [`vbwd-fe-user-plugin-truemoney`](https://github.com/VBWD-platform/vbwd-fe-user-plugin-truemoney)
- Admin: [`vbwd-fe-admin-plugin-truemoney`](https://github.com/VBWD-platform/vbwd-fe-admin-plugin-truemoney)

## Testing

```bash
docker compose run --rm test python -m pytest plugins/truemoney/tests/ -v
```

## Core requirements

See `docs/dev_log/20260422/sprints/_engineering-requirements.md`.
Gated by `bin/pre-commit-check.sh --full`.

---

**Core:** [vbwd-backend](https://github.com/VBWD-platform/vbwd-backend)

## Documentation

Full platform documentation lives at **[vbwd.cc/docs](https://vbwd.cc/docs)**.

- [Plugin system](https://vbwd.cc/docs-plugin-system) — how backend plugins are registered, enabled, and configured
- [Payments](https://vbwd.cc/docs-core-payments) — documentation for this plugin's domain
- [Architecture](https://vbwd.cc/docs-architecture) — platform layering and the core-agnosticism rule
- [Getting started](https://vbwd.cc/docs-getting-started) — install a VBWD instance and enable plugins
