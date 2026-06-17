from datetime import date, time, datetime, timedelta

SLOT_START_HOUR = 9   # 9 AM
SLOT_END_HOUR   = 22  # 10 PM
SLOT_DURATION   = 15  # minutes
BUFFER_MINUTES  = 60  # don't allow slots within 60 min of now


def generate_slots(for_date: date) -> list[dict]:
    """
    Returns a list of available 15-min slots for the given date.
    Slots in the past (+ buffer) are marked unavailable for today.
    """
    slots = []
    now = datetime.now()
    current = datetime.combine(for_date, time(SLOT_START_HOUR, 0))
    end     = datetime.combine(for_date, time(SLOT_END_HOUR, 0))

    while current < end:
        slot_end = current + timedelta(minutes=SLOT_DURATION)
        is_today = for_date == date.today()
        available = True

        if is_today and current <= now + timedelta(minutes=BUFFER_MINUTES):
            available = False

        slots.append({
            "slot_start": current.strftime("%I:%M %p"),
            "slot_end":   slot_end.strftime("%I:%M %p"),
            "available":  available,
        })
        current = slot_end

    return slots