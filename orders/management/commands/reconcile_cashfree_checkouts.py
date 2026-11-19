import logging
from time import sleep

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from orders.payment_fulfillment import reconcile_due_checkouts

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconcile grocery Cashfree checkouts and refunds."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Check for due work every 15 seconds.")

    def handle(self, *args, **options):
        if not options["loop"]:
            reconcile_due_checkouts()
            return

        while True:
            close_old_connections()
            try:
                reconcile_due_checkouts()
            except Exception:
                logger.exception("Cashfree checkout reconciliation pass failed")
            sleep(15)
