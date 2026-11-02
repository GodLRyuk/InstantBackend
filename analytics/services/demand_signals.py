import logging
import re
import unicodedata

from django.db import DatabaseError

from products.models import Product

from analytics.models import DemandSignal


logger = logging.getLogger(__name__)

_EMAIL_PATTERN = re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b')
_PHONE_PATTERN = re.compile(r'(?<!\w)\+?\d(?:[\s().-]*\d){7,}(?!\w)')


def normalize_search_query(query: str) -> str:
    normalized = unicodedata.normalize('NFKC', query)
    normalized = _EMAIL_PATTERN.sub(' ', normalized)
    normalized = _PHONE_PATTERN.sub(' ', normalized)
    return ' '.join(normalized.casefold().split())[:120]


def _save_signal(**fields):
    try:
        DemandSignal.objects.create(**fields)
    except DatabaseError:
        logger.exception('Could not persist an analytics demand signal.')


def record_search_signal(query: str, result_count: int) -> None:
    normalized_query = normalize_search_query(query)
    if not normalized_query:
        return

    _save_signal(
        signal_type=DemandSignal.SignalType.SEARCH,
        normalized_query=normalized_query,
        result_count=result_count,
    )


def record_add_to_cart(product: Product, quantity: int) -> None:
    if quantity <= 0:
        return

    _save_signal(
        signal_type=DemandSignal.SignalType.ADD_TO_CART,
        product=product,
        quantity=quantity,
    )
