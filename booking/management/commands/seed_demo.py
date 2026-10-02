from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.models import Booking, Category, Review, Service, TimeSlot
from booking.services import generate_slots
from users.models import User


def make_user(username, role, password, **extra):
    user, created = User.objects.get_or_create(username=username, defaults={"role": role, **extra})
    if created:
        user.set_password(password)
        user.save()
    return user


class Command(BaseCommand):
    help = "Создаёт демо-данные: админа, специалистов, клиентов, категории, услуги, слоты и отзывы."

    def handle(self, *args, **options):
        make_user("admin", User.Role.ADMIN, "admin12345", is_staff=True, is_superuser=True)
        clients = [
            make_user("client1", User.Role.CLIENT, "demo12345", first_name="Алия", email="aliya@example.com", phone="+7 700 111 22 33"),
            make_user("client2", User.Role.CLIENT, "demo12345", first_name="Марат", phone="+7 701 222 33 44"),
        ]
        cats = {n: Category.objects.get_or_create(name=n, defaults={"icon": i})[0]
                for n, i in [("Красота", "💇"), ("Здоровье", "💆"), ("Обучение", "🎓"), ("Спорт", "🏋️")]}
        demo = {
            "anna": ("Анна Петрова", "Парикмахер-стилист", "Стилист с опытом 8 лет. Стрижки, окрашивание, укладки.",
                     [("Женская стрижка", "Красота", 60, 5000), ("Окрашивание", "Красота", 120, 12000)]),
            "ivan": ("Иван Соколов", "Массажист", "Лечебный и расслабляющий массаж. Работаю с болью в спине и шее.",
                     [("Классический массаж", "Здоровье", 45, 6000), ("Массаж спины", "Здоровье", 30, 4000)]),
            "dana": ("Дана Ержанова", "Репетитор по английскому", "IELTS, разговорный английский, подготовка к собеседованиям.",
                     [("Урок английского", "Обучение", 60, 4500)]),
            "timur": ("Тимур Алиев", "Персональный тренер", "Силовые тренировки и снижение веса. Первое занятие — знакомство.",
                      [("Персональная тренировка", "Спорт", 60, 7000)]),
        }
        today = timezone.localdate()
        for username, (name, specialty, bio, services) in demo.items():
            provider = make_user(username, User.Role.PROVIDER, "demo12345", first_name=name.split()[0],
                                 last_name=name.split()[1], specialty=specialty, bio=bio)
            for title, cat, minutes, price in services:
                Service.objects.get_or_create(provider=provider, title=title, defaults={
                    "category": cats[cat], "duration_minutes": minutes, "price": price})
            first = provider.services.first()
            days = [today + timedelta(days=i) for i in range(10) if (today + timedelta(days=i)).weekday() < 6]
            generate_slots(provider, first, days, time(10, 0), time(18, 0))

            if not Review.objects.filter(booking__slot__provider=provider).exists():
                for i, (rating, text) in enumerate([(5, "Всё отлично, рекомендую!"), (5, "Очень внимательный специалист."), (4, "Хорошо, но пришлось немного подождать.")]):
                    start = timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=i + 2)
                    slot = TimeSlot.objects.create(provider=provider, service=first, start_time=start,
                                                   end_time=start + timedelta(minutes=first.duration_minutes), is_booked=True)
                    booking = Booking.objects.create(client=clients[i % 2], slot=slot, status=Booking.Status.COMPLETED)
                    Review.objects.create(booking=booking, rating=rating, text=text)
        self.stdout.write(self.style.SUCCESS(
            "Готово. Логины: admin/admin12345, anna|ivan|dana|timur/demo12345 (специалисты), client1|client2/demo12345"))
