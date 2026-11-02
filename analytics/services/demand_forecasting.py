from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from orders.models import OrderItem
from products.models import Product


HISTORY_DAYS = 28
MIN_SALES_DAYS = 14
EVALUATION_TRAIN_DAYS = 21
EVALUATION_HOLDOUT_DAYS = 7
MODEL_NAME = '28_day_mean'
MODEL_VERSION = '1'
ZERO = Decimal('0')
TWO_DECIMAL_PLACES = Decimal('0.01')


def _format_units(value: Decimal) -> str:
    return format(value.quantize(TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP), '.2f')


def _evaluate_baseline(daily_units: list[int]) -> dict:
    training = daily_units[:EVALUATION_TRAIN_DAYS]
    holdout = daily_units[EVALUATION_TRAIN_DAYS:]
    training_sales_days = sum(units > 0 for units in training)

    evaluation = {
        'status': 'insufficient_data',
        'method': 'time_holdout_21_days_train_7_days_test',
        'training_sales_days': training_sales_days,
        'mae_units': None,
        'wape_percent': None,
    }
    if training_sales_days < MIN_SALES_DAYS or len(holdout) != EVALUATION_HOLDOUT_DAYS:
        return evaluation

    daily_average = Decimal(sum(training)) / Decimal(EVALUATION_TRAIN_DAYS)
    absolute_errors = [abs(Decimal(actual) - daily_average) for actual in holdout]
    mae = sum(absolute_errors, ZERO) / Decimal(EVALUATION_HOLDOUT_DAYS)
    actual_total = sum(holdout)

    evaluation.update({
        'status': 'evaluated',
        'mae_units': _format_units(mae),
        'wape_percent': (
            _format_units(sum(absolute_errors, ZERO) / Decimal(actual_total) * 100)
            if actual_total
            else None
        ),
    })
    return evaluation


def build_demand_forecasts(products: list[Product], horizon_days: int) -> list[dict]:
    today = timezone.localdate()
    history_start = today - timedelta(days=HISTORY_DAYS)
    history_end = today - timedelta(days=1)
    history_dates = [
        history_start + timedelta(days=offset)
        for offset in range(HISTORY_DAYS)
    ]
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(history_start, time.min), tz)
    end = timezone.make_aware(datetime.combine(today, time.min), tz)
    product_ids = [product.id for product in products]

    daily_sales = (
        OrderItem.objects
        .filter(
            product_id__in=product_ids,
            order__order_status='DELIVERED',
            order__payment_status='PAID',
            order__created_at__gte=start,
            order__created_at__lt=end,
        )
        .annotate(sales_date=TruncDate('order__created_at', tzinfo=tz))
        .values('product_id', 'sales_date')
        .annotate(units_sold=Sum('quantity'))
    )
    units_by_product: dict[int, dict[date, int]] = {}
    for row in daily_sales:
        units_by_product.setdefault(row['product_id'], {})[row['sales_date']] = (
            row['units_sold'] or 0
        )

    forecasts = []
    for product in products:
        daily_units = [
            units_by_product.get(product.id, {}).get(sales_date, 0)
            for sales_date in history_dates
        ]
        sales_days = sum(units > 0 for units in daily_units)
        total_units = sum(daily_units)
        sufficient_data = sales_days >= MIN_SALES_DAYS
        forecast = []

        if sufficient_data:
            average_units = Decimal(total_units) / Decimal(HISTORY_DAYS)
            forecast = [
                {
                    'date': (today + timedelta(days=offset)).isoformat(),
                    'predicted_units': _format_units(average_units),
                }
                for offset in range(1, horizon_days + 1)
            ]

        forecasts.append({
            'product_id': product.id,
            'product_name': product.name,
            'status': 'baseline_estimate' if sufficient_data else 'insufficient_data',
            'history': {
                'start_date': history_start.isoformat(),
                'end_date': history_end.isoformat(),
                'calendar_days': HISTORY_DAYS,
                'sales_days': sales_days,
                'fulfilled_units': total_units,
            },
            'forecast': forecast,
            'evaluation': _evaluate_baseline(daily_units),
        })

    return forecasts
