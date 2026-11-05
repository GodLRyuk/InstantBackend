import secrets

from .models import Product


def _ean13_check_digit(body):
    weighted_sum = sum(
        int(digit) * (3 if index % 2 else 1)
        for index, digit in enumerate(body)
    )
    return str((-weighted_sum) % 10)


def generate_unique_in_store_ean13():
    for _ in range(100):
        body = f"2{secrets.randbelow(10**11):011d}"
        barcode = f"{body}{_ean13_check_digit(body)}"
        if not Product.objects.filter(barcode=barcode).exists():
            return barcode

    raise RuntimeError("Could not generate an unused in-store barcode.")
