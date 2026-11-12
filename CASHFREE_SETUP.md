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

Apply database migrations before deploying. The client return URL is supplied
by the existing client application; payment confirmation must call the
authenticated backend verification endpoint or arrive through the signed
webhook. The webhook endpoint is `POST /api/payments/cashfree/webhook/`.
