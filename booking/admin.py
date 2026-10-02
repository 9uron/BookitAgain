from django.contrib import admin
from .models import Booking, Category, Review, Service, TimeSlot


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "duration_minutes", "price", "is_active")
    list_filter = ("is_active", "provider")
    search_fields = ("title",)


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ("provider", "service", "start_time", "end_time", "is_booked")
    list_filter = ("is_booked", "provider")
    date_hierarchy = "start_time"


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("client", "slot", "status", "created_at")
    list_filter = ("status",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("icon", "name")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("booking", "rating", "created_at")
    list_filter = ("rating",)
