from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import User

from .models import Booking, Category, Review, Service, TimeSlot

PWD = "pass12345!"


class BookingTests(TestCase):
    def setUp(self):
        self.provider = User.objects.create_user("prov", password=PWD, role="provider")
        self.alice = User.objects.create_user("alice", password=PWD, role="client")
        self.bob = User.objects.create_user("bob", password=PWD, role="client")
        self.service = Service.objects.create(provider=self.provider, title="Стрижка", duration_minutes=60, price=1000)
        start = timezone.now() + timedelta(days=1)
        self.slot = TimeSlot.objects.create(
            provider=self.provider, service=self.service, start_time=start, end_time=start + timedelta(hours=1))

    def test_public_pages_render(self):
        for name, args in [("home", []), ("login", []), ("register", []), ("provider_detail", [self.provider.pk])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)
        events = self.client.get(reverse("provider_slots", args=[self.provider.pk])).json()
        self.assertEqual(len(events), 1)

    def test_cannot_register_as_admin(self):
        resp = self.client.post(reverse("register"), {
            "username": "hacker", "password1": PWD, "password2": PWD, "role": "admin"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="hacker").exists())

    def test_client_books_slot(self):
        self.client.login(username="alice", password=PWD)
        resp = self.client.post(reverse("book_slot", args=[self.slot.pk]), {"comment": "hi"})
        self.assertRedirects(resp, reverse("my_bookings"))
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_booked)
        self.assertEqual(Booking.objects.get().status, Booking.Status.PENDING)
        self.assertEqual(self.client.get(reverse("my_bookings")).status_code, 200)

    def test_double_booking_prevented(self):
        Booking.create_for_slot(self.alice, self.slot.pk)
        with self.assertRaises(ValidationError):
            Booking.create_for_slot(self.bob, self.slot.pk)
        self.assertEqual(Booking.objects.count(), 1)

    def test_cannot_book_past_slot(self):
        past = timezone.now() - timedelta(hours=3)
        old = TimeSlot.objects.create(provider=self.provider, start_time=past, end_time=past + timedelta(hours=1))
        with self.assertRaises(ValidationError):
            Booking.create_for_slot(self.alice, old.pk)

    def test_cancel_frees_slot_for_rebooking(self):
        b = Booking.create_for_slot(self.alice, self.slot.pk)
        self.client.login(username="alice", password=PWD)
        self.client.post(reverse("booking_cancel", args=[b.pk]))
        b.refresh_from_db(); self.slot.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.CANCELLED)
        self.assertFalse(self.slot.is_booked)
        Booking.create_for_slot(self.bob, self.slot.pk)
        self.assertEqual(Booking.objects.exclude(status="cancelled").count(), 1)

    def test_late_cancel_blocked(self):
        soon = timezone.now() + timedelta(hours=1)
        slot = TimeSlot.objects.create(provider=self.provider, start_time=soon, end_time=soon + timedelta(hours=1))
        b = Booking.create_for_slot(self.alice, slot.pk)
        self.client.login(username="alice", password=PWD)
        self.client.post(reverse("booking_cancel", args=[b.pk]))
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.PENDING)

    def test_role_restrictions(self):
        self.client.login(username="alice", password=PWD)
        self.assertEqual(self.client.get(reverse("provider_dashboard")).status_code, 403)
        self.client.login(username="prov", password=PWD)
        self.assertEqual(self.client.post(reverse("book_slot", args=[self.slot.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("provider_dashboard")).status_code, 200)

    def test_provider_generates_slots_and_manages_booking(self):
        self.client.login(username="prov", password=PWD)
        day = (timezone.localtime() + timedelta(days=2)).date()
        self.client.post(reverse("slots_generate"), {
            "service": self.service.pk, "date_from": day.isoformat(), "start": "10:00", "end": "13:00"})
        self.assertEqual(TimeSlot.objects.filter(start_time__date=day).count(), 3)
        b = Booking.create_for_slot(self.alice, self.slot.pk)
        self.client.post(reverse("booking_status", args=[b.pk]), {"action": "confirm"})
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.CONFIRMED)
        self.client.post(reverse("booking_status", args=[b.pk]), {"action": "complete"})
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.COMPLETED)


class FeatureTests(TestCase):
    def setUp(self):
        self.provider = User.objects.create_user("prov", password=PWD, role="provider", first_name="Анна", specialty="Стилист")
        self.alice = User.objects.create_user("alice", password=PWD, role="client", email="a@example.com")
        self.cat = Category.objects.create(name="Красота")
        self.service = Service.objects.create(
            provider=self.provider, title="Стрижка", category=self.cat, duration_minutes=60, price=1000)
        start = timezone.now() + timedelta(days=1)
        self.slot = TimeSlot.objects.create(
            provider=self.provider, service=self.service, start_time=start, end_time=start + timedelta(hours=1))

    def test_search_and_category_filter(self):
        url = reverse("home")
        self.assertContains(self.client.get(url, {"q": "стрижка"}), "Анна")
        self.assertContains(self.client.get(url, {"q": "СТИЛИСТ"}), "Анна")
        self.assertNotContains(self.client.get(url, {"q": "массаж"}), "Анна")
        self.assertContains(self.client.get(url, {"category": self.cat.pk}), "Анна")
        self.assertNotContains(self.client.get(url, {"category": self.cat.pk + 99}), "Анна")

    def test_multi_day_slot_generation_with_weekdays(self):
        self.client.login(username="prov", password=PWD)
        start = timezone.localdate() + timedelta(days=7)
        self.client.post(reverse("slots_generate"), {
            "service": self.service.pk, "date_from": start.isoformat(),
            "date_to": (start + timedelta(days=6)).isoformat(), "weekdays": [0, 2],
            "start": "10:00", "end": "12:00"})
        created = TimeSlot.objects.exclude(pk=self.slot.pk).filter(start_time__date__gte=start)
        self.assertEqual(created.count(), 4)
        self.assertEqual({timezone.localtime(t.start_time).weekday() for t in created}, {0, 2})

    def test_feed_service_filter(self):
        other = Service.objects.create(provider=self.provider, title="Окрашивание", duration_minutes=60, price=1)
        start = timezone.now() + timedelta(days=2)
        TimeSlot.objects.create(provider=self.provider, service=other, start_time=start, end_time=start + timedelta(hours=1))
        url = reverse("provider_slots", args=[self.provider.pk])
        self.assertEqual(len(self.client.get(url).json()), 2)
        self.assertEqual(len(self.client.get(url, {"service": self.service.pk}).json()), 1)

    def test_review_flow(self):
        booking = Booking.create_for_slot(self.alice, self.slot.pk)
        self.client.login(username="alice", password=PWD)
        url = reverse("review_create", args=[booking.pk])
        self.client.post(url, {"rating": 5})
        self.assertEqual(Review.objects.count(), 0)
        booking.status = Booking.Status.COMPLETED; booking.save()
        self.client.post(url, {"rating": 9})
        self.assertEqual(Review.objects.count(), 0)
        self.client.post(url, {"rating": 5, "text": "Супер"})
        self.client.post(url, {"rating": 1})
        self.assertEqual(Review.objects.get().rating, 5)
        page = self.client.get(reverse("provider_detail", args=[self.provider.pk]))
        self.assertContains(page, "Супер")
        self.assertContains(self.client.get(reverse("home")), "5,0")

    def test_profile_and_dashboards_render(self):
        self.client.login(username="alice", password=PWD)
        self.assertEqual(self.client.get(reverse("my_bookings")).status_code, 200)
        self.client.post(reverse("profile"), {"first_name": "Алия", "last_name": "", "email": "new@example.com", "phone": ""})
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.email, "new@example.com")
        self.client.login(username="prov", password=PWD)
        self.assertEqual(self.client.get(reverse("provider_dashboard")).status_code, 200)
        self.client.post(reverse("profile"), {"first_name": "Анна", "specialty": "Колорист", "bio": "Опыт 8 лет", "email": "", "phone": "", "last_name": ""})
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.specialty, "Колорист")

    def test_email_notifications(self):
        self.client.login(username="alice", password=PWD)
        self.client.post(reverse("book_slot", args=[self.slot.pk]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Вы записаны", mail.outbox[0].subject)
