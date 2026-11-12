"""Cashfree Payments API helpers shared by all order types."""
import base64
import hashlib
import hmac
import json
import uuid

import requests
from django.conf import settings


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


def parse_webhook(raw_body):
    return json.loads(raw_body.decode('utf-8'))
