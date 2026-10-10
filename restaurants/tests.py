from datetime import time
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from .services import calculate_bill
from .utils import fmt_time, haversine_km, whole_rupees


def item(price, packaging=0):
    return SimpleNamespace(price=Decimal(price), packaging_charge=Decimal(packaging))


def restaurant(**kw):
    base = dict(
        offer_percent=30, offer_max_discount=75, offer_min_order=0, delivery_fee=Decimal('25'),
    )
    base.update(kw)
    return SimpleNamespace(**base)


class BillTests(SimpleTestCase):
    def test_matches_the_app_design(self):
        # 1 biryani (249, packaging 10) + 2 naan (40) -> total 302
        bill = calculate_bill(restaurant(), [(item('249', '10'), 1), (item('40'), 2)])
        self.assertEqual(bill.item_total, Decimal('329'))
        self.assertEqual(bill.discount, Decimal('75'))  # 30% = 99, capped at 75
        self.assertEqual(bill.packaging, Decimal('10'))
        self.assertEqual(bill.gst, Decimal('13'))
        self.assertEqual(bill.total, Decimal('302'))

    def test_no_offer(self):
        bill = calculate_bill(restaurant(offer_percent=None), [(item('100'), 2)])
        self.assertEqual(bill.discount, Decimal('0'))
        self.assertEqual(bill.gst, Decimal('10'))
        self.assertEqual(bill.total, Decimal('235'))

    def test_offer_needs_minimum_order(self):
        bill = calculate_bill(restaurant(offer_min_order=500), [(item('100'), 2)])
        self.assertEqual(bill.discount, Decimal('0'))

    def test_offer_without_cap(self):
        bill = calculate_bill(restaurant(offer_max_discount=0), [(item('1000'), 1)])
        self.assertEqual(bill.discount, Decimal('300'))


class UtilTests(SimpleTestCase):
    def test_rounding_goes_up_on_half(self):
        self.assertEqual(whole_rupees(Decimal('12.5')), Decimal('13'))
        self.assertEqual(whole_rupees(Decimal('12.4')), Decimal('12'))

    def test_time_format(self):
        self.assertEqual(fmt_time(time(23, 0)), '11:00 pm')
        self.assertEqual(fmt_time(time(9, 30)), '9:30 am')

    def test_distance(self):
        # Asansol to Durgapur is roughly 35 km
        km = haversine_km(23.6850, 86.9740, 23.5204, 87.3119)
        self.assertTrue(30 < km < 45)
