from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count, Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from users.decorators import role_required
from users.models import User

from . import notifications
from .forms import ReviewForm, ServiceForm, SlotGenerateForm
from .models import Booking, Category, Review, Service, TimeSlot
from .services import generate_slots

CANCEL_BEFORE = timedelta(hours=2)
Role = User.Role
Status = Booking.Status


def _dash(tab):
    return redirect(f"{reverse('provider_dashboard')}#{tab}")


def _flash_form_errors(request, form):
    for field_errors in form.errors.values():
        for error in field_errors:
            messages.error(request, error)


def home(request):
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")

    providers = list(
        User.objects.filter(role=Role.PROVIDER, services__is_active=True)
        .distinct()
        .prefetch_related(Prefetch(
            "services", queryset=Service.objects.filter(is_active=True).select_related("category"),
            to_attr="active_services",
        ))
    )
    now = timezone.now()
    for p in providers:
        ratings = [r.rating for r in Review.objects.filter(booking__slot__provider=p).only("rating")]
        p.avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
        p.reviews_count = len(ratings)
        p.next_free = (
            TimeSlot.objects.filter(provider=p, is_booked=False, start_time__gt=now)
            .order_by("start_time").values_list("start_time", flat=True).first()
        )

    if category_id.isdigit():
        providers = [p for p in providers if any(s.category_id == int(category_id) for s in p.active_services)]
    if q:
        needle = q.casefold()
        providers = [
            p for p in providers
            if needle in " ".join([p.display_name, p.username, p.specialty] + [s.title for s in p.active_services]).casefold()
        ]
    providers.sort(key=lambda p: (p.avg_rating is None, -(p.avg_rating or 0), p.display_name))

    categories = Category.objects.filter(services__is_active=True).distinct()
    return render(request, "booking/home.html", {
        "providers": providers, "categories": categories, "q": q, "cat": category_id})


@login_required
def dashboard(request):
    if request.user.role == Role.PROVIDER:
        return redirect("provider_dashboard")
    if request.user.role == Role.ADMIN:
        return redirect("admin:index")
    return redirect("my_bookings")


def provider_detail(request, pk):
    provider = get_object_or_404(User, pk=pk, role=Role.PROVIDER)
    services = provider.services.filter(is_active=True).select_related("category")
    reviews = Review.objects.filter(booking__slot__provider=provider).select_related("booking__client")[:20]
    ratings = [r.rating for r in reviews]
    return render(request, "booking/provider_detail.html", {
        "provider": provider, "services": services, "reviews": reviews,
        "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "reviews_count": len(ratings),
    })


def slots_feed(request, pk):
    provider = get_object_or_404(User, pk=pk, role=Role.PROVIDER)
    mine = request.GET.get("mine") == "1" and request.user.is_authenticated and request.user.pk == provider.pk

    qs = TimeSlot.objects.filter(provider=provider).select_related("service").prefetch_related(
        Prefetch(
            "bookings",
            queryset=Booking.objects.exclude(status=Status.CANCELLED).select_related("client"),
            to_attr="active_bookings",
        )
    )
    start = parse_datetime(request.GET.get("start", ""))
    end = parse_datetime(request.GET.get("end", ""))
    if start:
        qs = qs.filter(end_time__gt=start)
    if end:
        qs = qs.filter(start_time__lt=end)
    if request.GET.get("service", "").isdigit():
        qs = qs.filter(service_id=int(request.GET["service"]))
    if not mine:
        qs = qs.filter(start_time__gt=timezone.now())

    events = []
    for slot in qs:
        service = slot.service
        client = slot.active_bookings[0].client.display_name if (mine and slot.active_bookings) else ""
        if slot.is_booked:
            title = f"Занято: {client}" if client else "Занято"
        else:
            title = service.title if service else "Свободно"
        events.append({
            "id": slot.pk,
            "title": title,
            "start": timezone.localtime(slot.start_time).isoformat(),
            "end": timezone.localtime(slot.end_time).isoformat(),
            "classNames": ["fc-event-booked"] if slot.is_booked else [],
            "extendedProps": {
                "booked": slot.is_booked,
                "service": service.title if service else "",
                "price": str(service.price) if service else "",
                "client": client,
            },
        })
    return JsonResponse(events, safe=False)


@role_required(Role.CLIENT)
@require_POST
def book_slot(request, slot_id):
    slot = get_object_or_404(TimeSlot, pk=slot_id)
    try:
        booking = Booking.create_for_slot(request.user, slot.pk, request.POST.get("comment", "")[:500])
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect("provider_detail", pk=slot.provider_id)
    notifications.notify_created(booking)
    messages.success(request, "Вы записаны! Специалист скоро подтвердит запись.")
    return redirect("my_bookings")


@role_required(Role.CLIENT)
def my_bookings(request):
    now = timezone.now()
    bookings = list(
        Booking.objects.filter(client=request.user)
        .select_related("slot__provider", "slot__service", "review")
        .order_by("slot__start_time")
    )
    upcoming, history = [], []
    for b in bookings:
        is_active = b.status in (Status.PENDING, Status.CONFIRMED)
        b.can_cancel = is_active and b.slot.start_time - now >= CANCEL_BEFORE
        b.has_review = hasattr(b, "review")
        (upcoming if is_active and b.slot.start_time > now else history).append(b)
    history.reverse()
    return render(request, "booking/my_bookings.html", {"upcoming": upcoming, "history": history})


@role_required(Role.CLIENT)
@require_POST
def booking_cancel(request, pk):
    booking = get_object_or_404(Booking, pk=pk, client=request.user)
    if booking.status not in (Status.PENDING, Status.CONFIRMED):
        messages.error(request, "Эту запись уже нельзя отменить.")
    elif booking.slot.start_time - timezone.now() < CANCEL_BEFORE:
        messages.error(request, "Отменить запись можно не позже чем за 2 часа до начала.")
    else:
        booking.cancel()
        notifications.notify_cancelled(booking, by="client")
        messages.success(request, "Запись отменена.")
    return redirect("my_bookings")


@role_required(Role.CLIENT)
@require_POST
def review_create(request, pk):
    booking = get_object_or_404(Booking, pk=pk, client=request.user)
    if booking.status != Status.COMPLETED:
        messages.error(request, "Отзыв можно оставить только после завершённого приёма.")
    elif hasattr(booking, "review"):
        messages.error(request, "Вы уже оставили отзыв на эту запись.")
    else:
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.booking = booking
            review.save()
            messages.success(request, "Спасибо за отзыв!")
        else:
            messages.error(request, "Поставьте оценку от 1 до 5.")
    return redirect("my_bookings")


@role_required(Role.PROVIDER)
def provider_dashboard(request):
    provider = request.user
    now, today = timezone.now(), timezone.localdate()
    all_bookings = Booking.objects.filter(slot__provider=provider)
    revenue = all_bookings.filter(
        status=Status.COMPLETED, slot__start_time__year=today.year, slot__start_time__month=today.month
    ).aggregate(total=Sum("slot__service__price"))["total"] or 0
    ratings = Review.objects.filter(booking__slot__provider=provider).aggregate(avg=Avg("rating"), n=Count("id"))
    stats = {
        "today": all_bookings.exclude(status=Status.CANCELLED).filter(slot__start_time__date=today).count(),
        "pending": all_bookings.filter(status=Status.PENDING).count(),
        "free": TimeSlot.objects.filter(provider=provider, is_booked=False, start_time__gt=now).count(),
        "revenue": revenue,
        "rating": ratings["avg"],
        "reviews": ratings["n"],
    }
    bookings = all_bookings.select_related("client", "slot__service", "review").order_by("-slot__start_time")[:50]
    return render(request, "booking/provider_dashboard.html", {
        "provider": provider,
        "stats": stats,
        "services": provider.services.select_related("category"),
        "bookings": bookings,
        "service_form": ServiceForm(),
        "slot_form": SlotGenerateForm(provider),
    })


@role_required(Role.PROVIDER)
@require_POST
def service_create(request):
    form = ServiceForm(request.POST)
    if form.is_valid():
        service = form.save(commit=False)
        service.provider = request.user
        service.save()
        messages.success(request, "Услуга добавлена.")
    else:
        _flash_form_errors(request, form)
    return _dash("services")


@role_required(Role.PROVIDER)
@require_POST
def service_toggle(request, pk):
    service = get_object_or_404(Service, pk=pk, provider=request.user)
    service.is_active = not service.is_active
    service.save(update_fields=["is_active"])
    return _dash("services")


@role_required(Role.PROVIDER)
@require_POST
def slots_generate(request):
    form = SlotGenerateForm(request.user, request.POST)
    if form.is_valid():
        d = form.cleaned_data
        created, skipped = generate_slots(request.user, d["service"], d["days"], d["start"], d["end"])
        messages.success(request, f"Создано слотов: {created}. Пропущено (занято/в прошлом): {skipped}.")
    else:
        _flash_form_errors(request, form)
    return _dash("schedule")


@role_required(Role.PROVIDER)
@require_POST
def slot_delete(request, pk):
    slot = get_object_or_404(TimeSlot, pk=pk, provider=request.user)
    if slot.is_booked:
        return JsonResponse({"ok": False, "error": "Слот забронирован"}, status=400)
    slot.delete()
    return JsonResponse({"ok": True})


@role_required(Role.PROVIDER)
@require_POST
def booking_status(request, pk):
    booking = get_object_or_404(Booking, pk=pk, slot__provider=request.user)
    action = request.POST.get("action")
    if action == "confirm" and booking.status == Status.PENDING:
        booking.status = Status.CONFIRMED
        booking.save(update_fields=["status"])
        notifications.notify_confirmed(booking)
    elif action == "complete" and booking.status == Status.CONFIRMED:
        booking.status = Status.COMPLETED
        booking.save(update_fields=["status"])
    elif action == "cancel" and booking.status in (Status.PENDING, Status.CONFIRMED):
        booking.cancel()
        notifications.notify_cancelled(booking, by="provider")
    else:
        messages.error(request, "Это действие сейчас недоступно.")
    return _dash("bookings")
