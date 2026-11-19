from django.db import connection
from django.db.models import Value
from django.db.models.functions import Left, Lower, Replace, StrIndex


def email_in_use(users, email, *, lock=False):
    if not isinstance(email, str):
        return users.filter(email=email).exists()

    local, _, domain = email.rpartition("@")
    if domain.lower() not in {"gmail.com", "googlemail.com"}:
        return users.filter(email=email).exists()

    mailbox = local.partition("+")[0].replace(".", "").lower()
    if lock and connection.vendor == "postgresql":
        # Serialize checks and writes for the same mailbox across API workers.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"accounts:gmail:{mailbox}"],
            )

    # Find the first tag or domain separator in the stored address.
    before_tag_or_domain = Left(
        Lower("email"),
        StrIndex(Replace("email", Value("+"), Value("@")), Value("@")) - 1,
    )
    return users.filter(
        email__iregex=r"@(gmail\.com|googlemail\.com)$"
    ).alias(
        gmail_mailbox=Replace(before_tag_or_domain, Value("."), Value(""))
    ).filter(gmail_mailbox=mailbox).exists()
