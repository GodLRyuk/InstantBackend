import json
from dataclasses import dataclass
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.forms.models import model_to_dict
from rest_framework.exceptions import APIException, ValidationError

from .models import MenuItem, Restaurant, RestaurantOrder, RestaurantOrderItem
from .utils import haversine_km, whole_rupees

GST_RATE = Decimal('0.05')

S = RestaurantOrder.Status
P = RestaurantOrder.PaymentStatus
M = RestaurantOrder.PaymentMethod


# ---------------------------------------------------------------- pricing
@dataclass(frozen=True)
class Bill:
    item_total: Decimal
    discount: Decimal
    delivery_fee: Decimal
    packaging: Decimal
    gst: Decimal

    @property
    def total(self):
        return self.item_total - self.discount + self.delivery_fee + self.packaging + self.gst


def calculate_bill(restaurant, lines):
    """lines: iterable of (menu_item, quantity). Same maths as the Flutter cart."""
    lines = list(lines)
    item_total = sum((Decimal(i.price) * q for i, q in lines), Decimal('0'))
    packaging = sum((Decimal(i.packaging_charge) for i, _ in lines), Decimal('0'))  # once per dish

    discount = Decimal('0')
    pct = restaurant.offer_percent
    if pct and item_total >= Decimal(restaurant.offer_min_order):
        discount = whole_rupees(item_total * pct / 100)
        cap = Decimal(restaurant.offer_max_discount)
        if cap > 0 and discount > cap:
            discount = cap

    gst = whole_rupees((item_total - discount) * GST_RATE)
    return Bill(item_total, discount, Decimal(restaurant.delivery_fee), packaging, gst)


# ---------------------------------------------------------------- address
def resolve_address(user, address_id):
    """Loads the customer's saved address and makes a snapshot of it.

    Assumes addresses.Address has a `user` field. If yours is named differently,
    change the one filter below.
    """
    Address = apps.get_model('addresses', 'Address')
    try:
        address = Address.objects.get(pk=address_id, user=user)
    except (Address.DoesNotExist, ValueError, TypeError):
        raise ValidationError({'address_id': 'Address not found.'})

    snapshot = json.loads(json.dumps(model_to_dict(address), cls=DjangoJSONEncoder))

    def as_float(v):
        try:
            return float(v) if v not in (None, '') else None
        except (TypeError, ValueError):
            return None

    return {
        'snapshot': snapshot,
        'lat': as_float(snapshot.get('lat')),
        'lng': as_float(snapshot.get('lng')),
        'name': snapshot.get('name') or '',
        'phone': snapshot.get('phone') or '',
    }


# ---------------------------------------------------------------- quote
def build_quote(user, restaurant_id, items, address_id=None):
    """Validates a cart against the database and prices it. Never trusts client prices."""
    try:
        restaurant = Restaurant.objects.get(pk=restaurant_id, status=Restaurant.Status.APPROVED)
    except Restaurant.DoesNotExist:
        raise ValidationError({'restaurant_id': 'Restaurant not found.'})
    if not restaurant.is_open_now:
        raise ValidationError({'restaurant_id': 'This restaurant is not accepting orders right now.'})

    wanted = {}
    for row in items:
        wanted[row['menu_item_id']] = wanted.get(row['menu_item_id'], 0) + row['quantity']
    found = {
        m.id: m for m in MenuItem.objects.filter(restaurant=restaurant, pk__in=wanted.keys())
    }
    lines = []
    for item_id, qty in wanted.items():
        item = found.get(item_id)
        if item is None:
            raise ValidationError({'items': f'Dish {item_id} does not belong to this restaurant.'})
        if not item.is_available:
            raise ValidationError({'items': f'"{item.name}" is currently unavailable.'})
        if qty > 20:
            raise ValidationError({'items': f'You can order at most 20 of "{item.name}".'})
        lines.append((item, qty))

    bill = calculate_bill(restaurant, lines)
    if bill.item_total < restaurant.min_order_amount:
        raise ValidationError(
            {'items': f'Minimum order for this restaurant is Rs {restaurant.min_order_amount:.0f}.'}
        )

    address = None
    if address_id is not None:
        address = resolve_address(user, address_id)
        if address['lat'] is not None and restaurant.latitude is not None:
            km = haversine_km(address['lat'], address['lng'], restaurant.latitude, restaurant.longitude)
            if km > float(restaurant.delivery_radius_km):
                raise ValidationError(
                    {'address_id': 'This restaurant does not deliver to your location.'}
                )

    return {'restaurant': restaurant, 'lines': lines, 'bill': bill, 'address': address}


# ---------------------------------------------------------------- razorpay
def _razorpay_client():
    import razorpay  # imported here so tests and tools work without it configured

    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET))


def create_razorpay_order(order):
    data = _razorpay_client().order.create(
        {
            'amount': int(order.total_amount * 100),
            'currency': 'INR',
            'receipt': order.order_number,
            'payment_capture': 1,
        }
    )
    return data['id']


def verify_razorpay_signature(order_id, payment_id, signature):
    import razorpay

    try:
        _razorpay_client().utility.verify_payment_signature(
            {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature,
            }
        )
        return True
    except razorpay.errors.SignatureVerificationError:
        return False


class PaymentGatewayError(APIException):
    status_code = 502
    default_detail = 'Payment gateway is not reachable. Please try again.'
    default_code = 'payment_gateway_error'


# ---------------------------------------------------------------- create order
@transaction.atomic
def create_order(user, quote, payment_method, notes=''):
    restaurant, lines, bill, address = (
        quote['restaurant'], quote['lines'], quote['bill'], quote['address'],
    )
    online = payment_method == M.ONLINE
    order = RestaurantOrder.objects.create(
        customer=user,
        restaurant=restaurant,
        status=S.AWAITING_PAYMENT if online else S.PLACED,
        payment_method=payment_method,
        payment_status=P.PENDING,
        item_total=bill.item_total,
        discount=bill.discount,
        delivery_fee=bill.delivery_fee,
        packaging_charge=bill.packaging,
        gst=bill.gst,
        total_amount=bill.total,
        offer_code=restaurant.offer_code if bill.discount > 0 else '',
        customer_name=address['name'] or (user.get_full_name() or ''),
        customer_phone=address['phone'] or getattr(user, 'phone', '') or '',
        delivery_address=address['snapshot'],
        delivery_lat=address['lat'],
        delivery_lng=address['lng'],
        notes=notes,
    )
    order.order_number = f'RO{order.pk:06d}'
    order.save(update_fields=['order_number'])

    RestaurantOrderItem.objects.bulk_create(
        [
            RestaurantOrderItem(
                order=order,
                menu_item=item,
                name=item.name,
                is_veg=item.is_veg,
                unit_price=item.price,
                quantity=qty,
                line_total=item.price * qty,
                packaging_charge=item.packaging_charge,
            )
            for item, qty in lines
        ]
    )

    if online:
        try:
            order.razorpay_order_id = create_razorpay_order(order)
        except Exception as exc:  # noqa: BLE001 - any gateway problem rolls the order back
            raise PaymentGatewayError() from exc
        order.save(update_fields=['razorpay_order_id'])
    return order


# ---------------------------------------------------------------- status changes
FINAL = {S.DELIVERED, S.REJECTED, S.CANCELLED}
OWNER_TRANSITIONS = {
    S.PLACED: {S.ACCEPTED, S.REJECTED},
    S.ACCEPTED: {S.PREPARING},
    S.PREPARING: {S.READY},
}
STAFF_TRANSITIONS = {
    **OWNER_TRANSITIONS,
    S.READY: {S.OUT_FOR_DELIVERY},
    S.OUT_FOR_DELIVERY: {S.DELIVERED},
}


@transaction.atomic
def change_status(order_id, new_status, *, staff=False, reason='', allow=None, **lookup):
    """Moves an order to a new status if the transition is allowed.

    allow: override the allowed set (used for customer cancellation).
    lookup: extra filters, e.g. restaurant=..., customer=... so nobody touches other orders.
    """
    try:
        order = RestaurantOrder.objects.select_for_update().get(pk=order_id, **lookup)
    except RestaurantOrder.DoesNotExist:
        raise ValidationError({'detail': 'Order not found.'})

    if allow is None:
        table = STAFF_TRANSITIONS if staff else OWNER_TRANSITIONS
        allow = set(table.get(order.status, set()))
        if staff and order.status not in FINAL:
            allow.add(S.CANCELLED)
    if new_status not in allow:
        raise ValidationError(
            {'status': f'Cannot change an order from "{order.status}" to "{new_status}".'}
        )

    if new_status in (S.REJECTED, S.CANCELLED):
        order.rejection_reason = reason or (
            'Rejected by restaurant' if new_status == S.REJECTED else 'Cancelled'
        )
        if order.payment_method == M.ONLINE and order.payment_status == P.PAID:
            order.payment_status = P.REFUND_PENDING
    if new_status == S.DELIVERED and order.payment_method == M.COD:
        order.payment_status = P.PAID

    order.status = new_status
    order.save()
    # TODO: notify the customer / restaurant here (Channels or FCM).
    return order
