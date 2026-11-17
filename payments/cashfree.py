"""Cashfree Payments API helpers shared by all order types."""
import base64
import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _base_url():
    return (
        'https://api.cashfree.com/pg'
        if settings.CASHFREE_ENV == 'production'
        else 'https://sandbox.cashfree.com/pg'
    )


def _headers():
    if not settings.CASHFREE_CLIENT_ID or not settings.CASHFREE_CLIENT_SECRET:
        raise RuntimeError('Cashfree API credentials are not configured')
    return {
        'x-client-id': settings.CASHFREE_CLIENT_ID,
        'x-client-secret': settings.CASHFREE_CLIENT_SECRET,
        'x-api-version': settings.CASHFREE_API_VERSION,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }


def create_order(*, amount, currency, customer_id, customer_phone, customer_email='',
                 order_note='', return_url='', notify_url=''):
    # The opaque ID prevents collisions across grocery and restaurant sequences.
    provider_order_id = f'cf_{uuid.uuid4().hex}'
    body = {
        'order_id': provider_order_id,
        'order_amount': float(amount),
        'order_currency': currency,
        'customer_details': {
            'customer_id': str(customer_id),
            'customer_phone': str(customer_phone),
        },
    }
    if customer_email:
        body['customer_details']['customer_email'] = customer_email
    if order_note:
        body['order_note'] = order_note[:250]
    meta = {}
    if return_url:
        meta['return_url'] = return_url
    if notify_url:
        meta['notify_url'] = notify_url
    if meta:
        body['order_meta'] = meta
    response = requests.post(
        f'{_base_url()}/orders', headers=_headers(), json=body, timeout=20
    )
    if not response.ok:
        # Cashfree's response is useful for operational diagnosis; never log
        # request headers or credentials.
        logger.error(
            'Cashfree create-order failed: HTTP %s response=%s',
            response.status_code,
            response.text[:1000],
        )
        response.raise_for_status()
    return response.json()


def get_order(provider_order_id):
    response = requests.get(
        f'{_base_url()}/orders/{provider_order_id}', headers=_headers(), timeout=20
    )
    response.raise_for_status()
    return response.json()


def get_payments(provider_order_id):
    response = requests.get(
        f'{_base_url()}/orders/{provider_order_id}/payments',
        headers=_headers(), timeout=20,
    )
    response.raise_for_status()
    return response.json()


def verify_webhook(raw_body, timestamp, signature):
    if not settings.CASHFREE_CLIENT_SECRET or not timestamp or not signature:
        return False
    signed_payload = timestamp.encode() + raw_body
    expected = base64.b64encode(
        hmac.new(settings.CASHFREE_CLIENT_SECRET.encode(), signed_payload, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


def success_payment(provider_order_id):
    """Return successful payment details only after querying Cashfree server-side."""
    order = get_order(provider_order_id)
    if order.get('order_status') != 'PAID':
        return None
    payments = get_payments(provider_order_id)
    if isinstance(payments, dict):
        payments = payments.get('payments', [])
    for payment in payments:
        if payment.get('payment_status') == 'SUCCESS':
            return payment
    return None


def payment_matches(payment, *, amount, currency='INR'):
    return (
        payment is not None
        and payment.get('payment_currency') == currency
        and Decimal(str(payment.get('payment_amount', 0))) == amount
    )


def parse_webhook(raw_body):
    return json.loads(raw_body.decode('utf-8'))


def _request_idempotency_headers(key):
    return {'x-idempotency-key': str(uuid.uuid5(uuid.NAMESPACE_URL, key)), 'x-request-id': str(uuid.uuid4())}


def safe_error_details(exc, *, sensitive_values=()):
    """Return only Cashfree's non-sensitive error identifiers for API responses."""
    response = getattr(exc, 'response', None)
    if response is None:
        return {'code': 'cashfree_unavailable', 'message': 'Cashfree could not be reached.'}
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    details = {}
    for key in ('code', 'type', 'message'):
        if payload.get(key) is None:
            continue
        value = str(payload[key])[:300]
        for sensitive_value in sensitive_values:
            if sensitive_value:
                value = value.replace(str(sensitive_value), '[redacted]')
        details[key] = value
    if not details:
        details = {'code': 'cashfree_request_failed',
                   'message': f'Cashfree returned HTTP {response.status_code}.'}
    return details


def create_vendor(*, vendor_id, name, email, phone, account_number, account_holder, ifsc,
                 pan, business_type, gstin=''):
    """Create a Cashfree Easy Split vendor (requires Easy Split enabled on merchant)."""
    phone_digits = ''.join(ch for ch in str(phone) if ch.isdigit())
    if len(phone_digits) == 12 and phone_digits.startswith('91'):
        phone_digits = phone_digits[2:]
    body = {
        'vendor_id': vendor_id, 'status': 'ACTIVE', 'name': name[:100],
        'email': email, 'phone': phone_digits,
        'verify_account': True, 'dashboard_access': False, 'schedule_option': 1,
        'bank': {'account_number': str(account_number), 'account_holder': account_holder,
                 'ifsc': ifsc.upper()},
        'kyc_details': {
            'account_type': 'BUSINESS', 'business_type': business_type,
            'pan': pan.upper(), **({'gst': gstin.upper()} if gstin else {}),
        },
    }
    # Reuse the key for network retries of identical details, but generate a
    # new key if staff corrects details after a Cashfree validation failure.
    request_fingerprint = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()
    response = requests.post(
        f'{_base_url()}/easy-split/vendors',
        headers={**_headers(), **_request_idempotency_headers(f'vendor:{vendor_id}:{request_fingerprint}')},
        json=body, timeout=20,
    )
    if not response.ok:
        logger.error('Cashfree vendor creation failed: HTTP %s response=%s', response.status_code, response.text[:1000])
        response.raise_for_status()
    return response.json()


def submit_order_split(order_id, *, vendor_id, vendor_percentage):
    response = requests.post(
        f'{_base_url()}/easy-split/orders/{order_id}/split',
        headers={**_headers(), **_request_idempotency_headers(f'split:{order_id}')},
        json={'split': [{'vendor_id': vendor_id, 'percentage': float(vendor_percentage)}],
              'disable_split': True}, timeout=20,
    )
    if not response.ok:
        logger.error('Cashfree split failed: HTTP %s response=%s', response.status_code, response.text[:1000])
        response.raise_for_status()
    return response.json()


def get_order_split_details(order_id):
    response = requests.get(
        f'{_base_url()}/easy-split/orders/{order_id}', headers=_headers(), timeout=20,
    )
    response.raise_for_status()
    return response.json()


def create_refund(order_id, *, refund_id, amount, note, refund_splits=None):
    body = {'refund_id': refund_id, 'refund_amount': float(amount), 'refund_note': note[:100]}
    if refund_splits:
        body['refund_splits'] = refund_splits
    response = requests.post(
        f'{_base_url()}/orders/{order_id}/refunds',
        headers={**_headers(), **_request_idempotency_headers(f'refund:{refund_id}')},
        json=body, timeout=20,
    )
    if not response.ok:
        logger.error('Cashfree refund failed: HTTP %s response=%s', response.status_code, response.text[:1000])
        response.raise_for_status()
    return response.json()


def get_refund(order_id, refund_id):
    response = requests.get(
        f'{_base_url()}/orders/{order_id}/refunds/{refund_id}', headers=_headers(), timeout=20,
    )
    response.raise_for_status()
    return response.json()
