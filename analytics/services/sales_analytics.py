from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from orders.models import Order, OrderItem
from stock.models import Inventory


ZERO = Decimal('0.00')
MONEY_FIELDS = ('item_subtotal', 'discounts', 'delivery_fees', 'order_revenue')
SALES_DEFINITIONS = {
    'included_orders': 'order_status=DELIVERED and payment_status=PAID',
    'date_basis': 'Order creation date; fulfillment timestamps are not stored.',
    'order_revenue': (
        'Order.total_amount after order discounts and including delivery fees.'
    ),
    'item_subtotal': (
        'OrderItem.total_price; order-level discounts are not allocated to items.'
    ),
    'refunds': 'Not adjusted; grocery refund records are not available.',
}
_TRUNCATIONS = {
    'day': TruncDay,
    'week': TruncWeek,
    'month': TruncMonth,
}


def _date_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min),
        tz,
    )
    return start, end


def _period_date(value: datetime, tz) -> date:
    if timezone.is_aware(value):
        value = timezone.localtime(value, tz)
    return value.date()


def _money_string(value: Decimal) -> str:
    return format(value, '.2f')


def _period_starts(start_date: date, end_date: date, group_by: str):
    if group_by == 'week':
        current = start_date - timedelta(days=start_date.weekday())
        increment = lambda value: value + timedelta(days=7)
    elif group_by == 'month':
        current = start_date.replace(day=1)

        def increment(value):
            if value.month == 12:
                return value.replace(year=value.year + 1, month=1)
            return value.replace(month=value.month + 1)
    else:
        current = start_date
        increment = lambda value: value + timedelta(days=1)

    while current <= end_date:
        yield current
        current = increment(current)


def _fulfilled_order_filter(start: datetime, end: datetime):
    return Order.objects.filter(
        order_status='DELIVERED',
        payment_status='PAID',
        created_at__gte=start,
        created_at__lt=end,
    )


def get_sales_summary(start_date: date, end_date: date, group_by: str = 'day') -> dict:
    start, end = _date_bounds(start_date, end_date)
    tz = timezone.get_current_timezone()
    truncation = _TRUNCATIONS[group_by]

    order_periods = (
        _fulfilled_order_filter(start, end)
        .annotate(period=truncation('created_at', tzinfo=tz))
        .values('period')
        .annotate(
            order_count=Count('id'),
            order_revenue=Sum('total_amount'),
            discounts=Sum('discount_amount'),
            delivery_fees=Sum('delivery_fee'),
        )
    )
    item_periods = (
        OrderItem.objects
        .filter(
            order__order_status='DELIVERED',
            order__payment_status='PAID',
            order__created_at__gte=start,
            order__created_at__lt=end,
        )
        .annotate(period=truncation('order__created_at', tzinfo=tz))
        .values('period')
        .annotate(
            units_sold=Sum('quantity'),
            item_subtotal=Sum('total_price'),
        )
    )

    by_period = {}
    for row in order_periods:
        period = _period_date(row['period'], tz)
        by_period[period] = {
            'order_count': row['order_count'],
            'order_revenue': row['order_revenue'] or ZERO,
            'discounts': row['discounts'] or ZERO,
            'delivery_fees': row['delivery_fees'] or ZERO,
            'units_sold': 0,
            'item_subtotal': ZERO,
        }

    for row in item_periods:
        period = _period_date(row['period'], tz)
        metrics = by_period.setdefault(
            period,
            {
                'order_count': 0,
                'order_revenue': ZERO,
                'discounts': ZERO,
                'delivery_fees': ZERO,
                'units_sold': 0,
                'item_subtotal': ZERO,
            },
        )
        metrics['units_sold'] = row['units_sold'] or 0
        metrics['item_subtotal'] = row['item_subtotal'] or ZERO

    periods = []
    totals = {
        'order_count': 0,
        'units_sold': 0,
        'item_subtotal': ZERO,
        'discounts': ZERO,
        'delivery_fees': ZERO,
        'order_revenue': ZERO,
    }
    for period in _period_starts(start_date, end_date, group_by):
        metrics = by_period.get(
            period,
            {
                'order_count': 0,
                'order_revenue': ZERO,
                'discounts': ZERO,
                'delivery_fees': ZERO,
                'units_sold': 0,
                'item_subtotal': ZERO,
            },
        )
        periods.append({
            'period': period.isoformat(),
            **{
                key: _money_string(metrics[key]) if key in MONEY_FIELDS else metrics[key]
                for key in metrics
            },
        })
        totals['order_count'] += metrics['order_count']
        totals['units_sold'] += metrics['units_sold']
        for key in MONEY_FIELDS:
            totals[key] += metrics[key]
    totals.update({key: _money_string(totals[key]) for key in MONEY_FIELDS})

    return {
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'group_by': group_by,
        'definitions': SALES_DEFINITIONS,
        'totals': totals,
        'periods': periods,
    }


def get_top_products(
    start_date: date,
    end_date: date,
    limit: int = 10,
    sort_by: str = 'revenue',
) -> list[dict]:
    start, end = _date_bounds(start_date, end_date)
    products = (
        OrderItem.objects
        .filter(
            order__order_status='DELIVERED',
            order__payment_status='PAID',
            order__created_at__gte=start,
            order__created_at__lt=end,
        )
        .values('product_id', 'product__name')
        .annotate(
            units_sold=Sum('quantity'),
            item_subtotal=Sum('total_price'),
        )
    )
    if sort_by == 'quantity':
        products = products.order_by('-units_sold', '-item_subtotal', 'product_id')
    else:
        products = products.order_by('-item_subtotal', '-units_sold', 'product_id')

    return [
        {
            'product_id': row['product_id'],
            'product_name': row['product__name'],
            'units_sold': row['units_sold'],
            'item_subtotal': _money_string(row['item_subtotal'] or ZERO),
        }
        for row in products[:limit]
    ]


def get_inventory_overview() -> dict:
    summary = (
        Inventory.objects
        .annotate(available_stock=F('total_stock') - F('reserved_stock'))
        .aggregate(
            total_products=Count('id'),
            total_units=Sum('total_stock'),
            available_units=Sum('available_stock'),
            low_stock_count=Count(
                'id',
                filter=Q(available_stock__lte=F('low_stock_threshold')),
            ),
        )
    )
    return {
        key: summary[key] or 0
        for key in (
            'total_products',
            'total_units',
            'available_units',
            'low_stock_count',
        )
    }
