from datetime import datetime, timedelta

from django.utils import timezone

from .models import TimeSlot


def generate_slots(provider, service, days, start, end):
    tz = timezone.get_current_timezone()
    step = timedelta(minutes=service.duration_minutes)
    now = timezone.now()
    created = skipped = 0
    for day in days:
        cur = timezone.make_aware(datetime.combine(day, start), tz)
        stop = timezone.make_aware(datetime.combine(day, end), tz)
        while cur + step <= stop:
            nxt = cur + step
            clash = TimeSlot.objects.filter(
                provider=provider, start_time__lt=nxt, end_time__gt=cur
            ).exists()
            if cur < now or clash:
                skipped += 1
            else:
                TimeSlot.objects.create(provider=provider, service=service, start_time=cur, end_time=nxt)
                created += 1
            cur = nxt
    return created, skipped
