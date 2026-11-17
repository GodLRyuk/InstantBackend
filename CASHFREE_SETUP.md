# Cashfree Payments

The backend supports Cashfree for grocery and restaurant online orders. It uses
the Cashfree Payments API `2025-01-01` version and hosted checkout sessions.

Set these environment variables in each deployment (never commit credential
values):

```text
CASHFREE_ENV=sandbox
CASHFREE_CLIENT_ID=<sandbox App ID>
CASHFREE_CLIENT_SECRET=<sandbox Secret Key>
CASHFREE_API_VERSION=2025-01-01
CASHFREE_RETURN_URL=<public client return URL>
CASHFREE_NOTIFY_URL=https://<uat-api-host>/api/payments/cashfree/webhook/
```

For production, use `CASHFREE_ENV=production`, the production App ID and Secret
Key, and production return and webhook URLs. The code selects Cashfree's
sandbox or production API endpoint from `CASHFREE_ENV`. Configure the matching
webhook URL in the corresponding Cashfree dashboard environment.

For grocery orders, `/api/orders/create/` now creates a Cashfree checkout intent,
not an app order. The backend creates the app order only after server-side
Cashfree verification succeeds, either through the authenticated
`POST /api/verify-payment/` endpoint or the signed webhook. Failed or abandoned
checkouts therefore do not create an order or consume stock.

Apply database migrations before deploying. The client return URL is supplied
by the existing client application. The webhook endpoint is
`POST /api/payments/cashfree/webhook/`.
# Restaurant marketplace (Cashfree Easy Split)

Restaurant order checkout still uses the existing Cashfree PG order flow. Marketplace settlement is an additional Easy Split flow and requires Easy Split to be enabled for the same Cashfree merchant account in both sandbox and production.

## Owner onboarding

An approved restaurant owner submits bank details and business KYC (`account_number`, `ifsc_code`, `account_holder_name`, `pan`, `business_type`, optional `gstin`) to `POST /api/restaurants/partner/vendor/`. Account number and KYC identifiers are encrypted in the database using Django's `SECRET_KEY`; they are not returned by the API. Cashfree performs beneficiary verification. Owners can read the verification state with `GET` on the same endpoint. Bank/KYC details cannot currently be changed after the Cashfree vendor is created; support must coordinate changes to prevent a local/Cashfree mismatch.

Configure commission percentages in Django admin under **Vendor commissions**. The applicable latest commission effective at order creation is snapshotted into the order split. If no commission is configured, the platform commission is zero.

## Order split processing

Paid online restaurant orders with a successfully onboarded vendor get a `PaymentSplit` ledger row. The Cashfree webhook and server-side payment verification record the payment time. Cashfree requires waiting two minutes before submitting a split-after-payment request; a staff-only process endpoint handles due rows:

```text
POST /api/restaurants/admin/payment-splits/process/
POST /api/restaurants/admin/payment-splits/sync/
POST /api/restaurants/admin/refunds/process/
```

Schedule these endpoints from a trusted backend cron using staff authentication. The first submits pending splits (safe to retry with Cashfree idempotency), the second refreshes Cashfree settlement references, and the third submits and reconciles cancellation refunds (including the vendor portion when a split was submitted). Do not expose the staff endpoints to restaurant or customer clients.

The marketplace feature depends on Cashfree Easy Split being active and on the Cashfree API credentials having Easy Split access. Without those prerequisites, vendor onboarding and split processing will fail while the existing grocery and restaurant checkout collection flows continue to work.
