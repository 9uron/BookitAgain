from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = "client", "Клиент"
        PROVIDER = "provider", "Специалист"
        ADMIN = "admin", "Администратор"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CLIENT,
        verbose_name="Роль",
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон")
    specialty = models.CharField(max_length=100, blank=True, verbose_name="Специальность")
    bio = models.TextField(blank=True, max_length=1000, verbose_name="О себе")

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def initial(self):
        return self.display_name[:1].upper()

    @property
    def avatar_hue(self):
        return (self.pk or 0) * 47 % 360

    @property
    def is_client(self):
        return self.role == self.Role.CLIENT

    @property
    def is_provider(self):
        return self.role == self.Role.PROVIDER

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
