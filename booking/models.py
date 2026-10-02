from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True, verbose_name="Название")
    icon = models.CharField(max_length=8, default="✨", blank=True, verbose_name="Иконка (эмодзи)")

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]

    def __str__(self):
        return f"{self.icon} {self.name}".strip()


class Service(models.Model):
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="services",
        limit_choices_to={"role": "provider"},
        verbose_name="Специалист",
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="services", verbose_name="Категория",
    )
    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    duration_minutes = models.PositiveIntegerField(verbose_name="Длительность (мин)")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    is_active = models.BooleanField(default=True, verbose_name="Активна")

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"

    def __str__(self):
        return f"{self.title} ({self.provider})"


class TimeSlot(models.Model):
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="slots",
        limit_choices_to={"role": "provider"},
        verbose_name="Специалист",
    )
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="slots", verbose_name="Услуга",
    )
    start_time = models.DateTimeField(verbose_name="Начало")
    end_time = models.DateTimeField(verbose_name="Окончание")
    is_booked = models.BooleanField(default=False, verbose_name="Забронирован")

    class Meta:
        verbose_name = "Слот"
        verbose_name_plural = "Слоты"
        ordering = ["start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "start_time"],
                name="unique_slot_start_per_provider",
            )
        ]

    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError("Время окончания должно быть позже времени начала.")

    def __str__(self):
        return f"{self.provider} — {self.start_time:%d.%m.%Y %H:%M}"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подтверждения"
        CONFIRMED = "confirmed", "Подтверждено"
        CANCELLED = "cancelled", "Отменено"
        COMPLETED = "completed", "Завершено"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
        limit_choices_to={"role": "client"},
        verbose_name="Клиент",
    )
    slot = models.ForeignKey(
        TimeSlot, on_delete=models.CASCADE, related_name="bookings", verbose_name="Слот",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="Статус",
    )
    comment = models.TextField(blank=True, verbose_name="Комментарий клиента")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Бронирование"
        verbose_name_plural = "Бронирования"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["slot"],
                condition=~models.Q(status="cancelled"),
                name="unique_active_booking_per_slot",
            )
        ]

    def __str__(self):
        return f"{self.client} → {self.slot}"

    @classmethod
    @transaction.atomic
    def create_for_slot(cls, client, slot_id, comment=""):
        slot = TimeSlot.objects.select_for_update().get(pk=slot_id)
        if slot.is_booked:
            raise ValidationError("Этот слот уже забронирован.")
        if slot.start_time <= timezone.now():
            raise ValidationError("Нельзя записаться на время в прошлом.")
        slot.is_booked = True
        slot.save(update_fields=["is_booked"])
        return cls.objects.create(client=client, slot=slot, comment=comment)

    @transaction.atomic
    def cancel(self):
        if self.status == self.Status.CANCELLED:
            return
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status"])
        self.slot.is_booked = False
        self.slot.save(update_fields=["is_booked"])


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="Оценка",
    )
    text = models.TextField(blank=True, max_length=1000, verbose_name="Отзыв")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ["-created_at"]

    @property
    def stars(self):
        return "★" * self.rating + "☆" * (5 - self.rating)

    def __str__(self):
        return f"{self.booking} — {self.rating}/5"
