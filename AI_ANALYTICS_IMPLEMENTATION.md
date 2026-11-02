# AI Analytics Backend and Angular Integration

This guide describes the implemented Django analytics APIs, how their numbers are calculated, and how to add them to the Angular admin dashboard.

> This repository contains the Django backend, not the Angular application. Adapt the frontend examples to the Angular app's existing routing, environment, component, and authentication patterns.

## What is implemented

Analytics routes are mounted at `/api/analytics/`. Every endpoint requires an authenticated Django staff user (`is_staff=True`). Use the application's existing JWT interceptor to attach the access token as a Bearer authorization header.

| Endpoint | Description |
|---|---|
| `GET /api/analytics/overview/` | Date-filtered sales totals and current inventory totals |
| `GET /api/analytics/sales-summary/` | Sales grouped by day, week, or month |
| `GET /api/analytics/top-products/` | Product rankings by item subtotal or units sold |
| `GET /api/analytics/inventory-insights/` | Paginated current inventory and low-stock information |
| `GET /api/analytics/demand-signals/` | Up to 100 recent search and add-to-cart events |
| `GET /api/analytics/demand-forecast/` | Transparent 28-day average estimates with sufficiency status |
| `POST /api/analytics/assistant/ask/` | Optional Ollama explanation based on approved aggregate analytics |

Product searches record a normalized query and result count. Cart additions record product and quantity. These signals do not contain customer identity, addresses, or payment details. Email addresses and phone-like values are removed from search phrases. If recording a signal fails, the user-facing search/cart action continues and the failure is logged.

## How AI calculations work

The report APIs can ask **Ollama with `llama3.2:3b`** to calculate report values from sanitized order/item or inventory records. The exact Django calculations remain in the existing response fields; the additional `ollama_calculation.result` contains the model's independent calculation and `matches_backend` shows whether it agrees. Model-generated numbers may be wrong, so the exact backend fields remain the reliable values.

- Set `AI_REPORTS_ENABLED=True` to add Ollama calculations to overview, sales summary, top products, and inventory insights. It is disabled by default.
- The assistant endpoint continues to require `AI_ASSISTANT_ENABLED=True`; when enabled it returns both the plain-language answer and an Ollama calculation.
- Ollama receives only the fields needed for these reports. Order/customer identifiers, emails, addresses, payment credentials, delivery details, and free-text assistant questions are not included in calculation records.
- A calculation is limited to 1,000 order, item, and inventory records. Larger reports return HTTP 413 rather than silently truncating data. An Ollama timeout returns 504; provider or invalid-output failures return 502.
- Local `llama3.2:3b` testing matched the sample sales totals and top-product ranking, but produced incorrect inventory sums. Use `matches_backend` to spot differences; the exact backend fields remain authoritative.
- Ollama is reachable over the private Docker Compose network in the optional `ai` profile and is not published on a public host port.

Example request:

```http
POST /api/analytics/assistant/ask/
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "question": "Explain sales and delivery fees this month",
  "start_date": "2026-10-01",
  "end_date": "2026-10-31"
}
```

Supported intent keywords include stock/inventory, top or best-selling products, sales/revenue, and the general overview. Unrecognized questions select overview. The dates are optional and follow the same range rules as the reports.

## Metric definitions and caveats

- **Included grocery sales:** Orders where `order_status=DELIVERED` and `payment_status=PAID`. Paid COD orders are included.
- **Date basis:** `Order.created_at`; the grocery order model does not store a delivery/fulfillment timestamp. Dates use the project timezone, Asia/Kolkata, and `start_date`/`end_date` are inclusive.
- **Date defaults and limits:** The last 30 local calendar days, including today. A requested range cannot exceed 366 days or end in the future.
- **`order_revenue`:** `Order.total_amount` after order discounts and including delivery fees. Do not add delivery fees or subtract discounts again.
- **`item_subtotal`:** Sum of `OrderItem.total_price`. Order-level discounts are not allocated to individual products.
- **Refunds:** Grocery refunds are not recorded in a refund ledger, so reports cannot adjust for them.
- **Inventory:** Current values, not a historical snapshot for the requested sales dates. `total_units` and `available_units` sum quantities across products that may use different units, so these are numeric totals rather than comparable physical quantities.
- **Low stock:** `available_stock <= low_stock_threshold`, where `available_stock = total_stock - reserved_stock`.
- **Money:** Monetary values are strings with two decimal places.
- **Forecasts:** An estimate is returned only after at least 14 days with fulfilled sales during the last 28 complete days. Otherwise the status is `insufficient_data`. Forecasts are not validated production predictions. Historical stock availability is missing, so zero sales may also mean a stockout; there are no prediction intervals.

## Endpoint parameters and response shapes

### Overview

```text
GET /api/analytics/overview/?start_date=2026-10-04&end_date=2026-11-02
```

Returns `sales_definitions`, exact `sales` totals, current `inventory` totals, and—when enabled—`ollama_calculation`. Its `result` contains model-calculated sales and inventory totals.

### Sales summary

```text
GET /api/analytics/sales-summary/?start_date=2026-10-04&end_date=2026-11-02&group_by=day
```

`group_by` is `day`, `week`, or `month`. The response contains totals, period rows, and definitions. Weekly periods start Monday; monthly periods start on day one. A boundary period can start before the requested date.

When AI reports are enabled, `ollama_calculation.result.totals` is the model's separate calculation from the underlying order/item records.

### Top products

```text
GET /api/analytics/top-products/?start_date=2026-10-04&end_date=2026-11-02&limit=10&sort_by=revenue
```

`limit` is 1–100. `sort_by` is `revenue` or `quantity`. Each result includes `product_id`, `product_name`, `units_sold`, and `item_subtotal`.

When AI reports are enabled, `ollama_calculation.result.results` contains the model's ranking/calculations from delivered, paid order items.

### Inventory insights

```text
GET /api/analytics/inventory-insights/?limit=50&offset=0
```

Returns DRF limit-offset pagination: `count`, `next`, `previous`, `results`, and `low_stock_count`. Page size is 1–100. The complete result set is ordered by available stock ascending, then product name. `low_stock_count` is across all inventory, not just the current page.

When AI reports are enabled, `ollama_calculation.result.inventory` is calculated from all inventory rows, not just the current page.

### Demand forecast

```text
GET /api/analytics/demand-forecast/?horizon_days=7&limit=50&offset=0
GET /api/analytics/demand-forecast/?product_id=42&horizon_days=14
```

`horizon_days` is 1–30 (default 7). The paginated response provides model, history, evaluation metadata, caveats, and per-product estimates/status.

### Demand signals

```text
GET /api/analytics/demand-signals/
```

Returns an array with up to 100 recent events. Search events include normalized query/result count; cart events include product/quantity.

## Angular integration steps

1. **Configure the API base URL.** Use the Angular app's environment configuration; don't hard-code a deployment host in a component.
2. **Reuse authentication.** Keep using the existing JWT interceptor and protect the analytics route with the admin/staff guard. Do not add a separate token store.
3. **Create typed API models.** Keep money as strings in transport types.
4. **Create an injectable API service.** Use `HttpClient` and `HttpParams`; keep network calls out of chart components.
5. **Add an admin analytics route/page.** Start with a date picker, overview cards, sales chart, top-product table, and inventory list.
6. **Show definitions and caveats.** Label order revenue as the order total including delivery fee; don't double-add fees or subtract discounts. Make the current-vs-historical inventory distinction clear.
7. **Add the assistant form optionally.** Display the answer alongside the returned aggregate `data`; show disabled/unavailable/time-out states without disabling the rest of the dashboard.
8. **Test integration.** Verify admin and non-admin access, token expiry, date validation, empty periods, pagination, loading/errors, and chart totals against the raw API payload.

Example interfaces:

```ts
export interface AnalyticsOverview {
  start_date: string;
  end_date: string;
  sales_definitions: Record<string, string>;
  sales: {
    order_count: number;
    units_sold: number;
    item_subtotal: string;
    discounts: string;
    delivery_fees: string;
    order_revenue: string;
  };
  inventory: {
    total_products: number;
    total_units: number;
    available_units: number;
    low_stock_count: number;
  };
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AnalyticsAssistantRequest {
  question: string;
  start_date?: string;
  end_date?: string;
}

export interface AnalyticsAssistantResponse {
  answer: string;
  intent: 'overview' | 'sales' | 'top_products' | 'inventory';
  start_date: string;
  end_date: string;
  model: string;
  data: Record<string, unknown>;
}
```

Example API service methods:

```ts
getOverview(startDate: string, endDate: string) {
  const params = new HttpParams()
    .set('start_date', startDate)
    .set('end_date', endDate);

  return this.http.get<AnalyticsOverview>(
    `${this.apiBaseUrl}/api/analytics/overview/`,
    { params },
  );
}

askAnalytics(request: AnalyticsAssistantRequest) {
  return this.http.post<AnalyticsAssistantResponse>(
    `${this.apiBaseUrl}/api/analytics/assistant/ask/`,
    request,
  );
}
```

Import `HttpClient` and `HttpParams` from `@angular/common/http` and use the Angular app's existing API-base configuration and DI pattern.

## Enable Ollama locally on Mac

On this development machine, Ollama is installed and running, `llama3.2:3b` has been downloaded, and real requests through the Django provider were tested against sample reports. The model matched sample sales totals and product ranking, but not inventory sums. This verifies local inference only; it does not install or configure Ollama on the production server.

On another Mac, install Ollama and download the selected model:

```bash
brew install ollama
brew services start ollama
ollama pull llama3.2:3b
```

Set these variables in the local, untracked environment file read by Django:

```dotenv
AI_ASSISTANT_ENABLED=True
AI_REPORTS_ENABLED=True
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:3b
```

Keep port 11434 bound to localhost/private interfaces. Never expose it publicly or commit environment files.

## Enable Ollama in Docker deployment

The default Docker Compose profile does not start Ollama or download a model. The opt-in `ai` profile adds an Ollama service, persistent model storage, and a one-shot model-pull job. The model service has no published host port.

Set these values in the server's existing `.env`:

```dotenv
AI_ASSISTANT_ENABLED=True
AI_REPORTS_ENABLED=True
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2:3b
```

The deployment command/pipeline must start the AI profile:

```bash
docker compose --profile ai up -d --build
docker compose logs ollama-model
```

Wait for the model-pull job to complete before testing assistant requests. The downloaded model is kept in the `ollama_data` Docker volume. A Git push alone does not install Ollama or pull a model: the server's deployment process must run the profile. Check production RAM, disk, CPU capacity, and load before enabling local inference. No remote installation, model download, or server deployment is performed by this code change.

## Migrations and validation

Migrations required by the analytics database and sales-query index:

- `analytics/migrations/0001_initial.py`
- `orders/migrations/0015_order_orders_sales_status_date_idx.py`

Inspect the target environment's migration state and follow the deployment backup/release process before applying. Do not assume migrations run merely because code is pushed.

Backend validation previously passed:

```text
python3 manage.py test analytics.tests cart.tests orders.tests
Ran 32 tests — OK
python3 manage.py check
System check identified no issues
python3 manage.py makemigrations --check --dry-run
No changes detected
git diff --check
Passed
```
