from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("providers/<int:pk>/", views.provider_detail, name="provider_detail"),
    path("providers/<int:pk>/slots.json", views.slots_feed, name="provider_slots"),
    path("slots/<int:slot_id>/book/", views.book_slot, name="book_slot"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("my-bookings/", views.my_bookings, name="my_bookings"),
    path("my-bookings/<int:pk>/cancel/", views.booking_cancel, name="booking_cancel"),
    path("my-bookings/<int:pk>/review/", views.review_create, name="review_create"),
    path("provider/", views.provider_dashboard, name="provider_dashboard"),
    path("provider/services/add/", views.service_create, name="service_create"),
    path("provider/services/<int:pk>/toggle/", views.service_toggle, name="service_toggle"),
    path("provider/slots/generate/", views.slots_generate, name="slots_generate"),
    path("provider/slots/<int:pk>/delete/", views.slot_delete, name="slot_delete"),
    path("provider/bookings/<int:pk>/status/", views.booking_status, name="booking_status"),
]
