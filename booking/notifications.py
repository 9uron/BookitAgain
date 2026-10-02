from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


def _send(email, subject, body):
    if email:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=True)


def _describe(booking):
    slot = booking.slot
    when = timezone.localtime(slot.start_time).strftime("%d.%m.%Y в %H:%M")
    service = slot.service.title if slot.service else "приём"
    return service, when


def notify_created(booking):
    service, when = _describe(booking)
    provider, client = booking.slot.provider, booking.client
    _send(client.email, "Вы записаны — BookIt",
          f"Здравствуйте, {client.display_name}!\n\nВы записались к {provider.display_name}: {service}, {when}.\n"
          "Специалист скоро подтвердит запись.")
    _send(provider.email, "Новая запись — BookIt",
          f"Клиент {client.display_name} записался на «{service}», {when}.\nПодтвердите запись в кабинете.")


def notify_confirmed(booking):
    service, when = _describe(booking)
    _send(booking.client.email, "Запись подтверждена — BookIt",
          f"{booking.slot.provider.display_name} подтвердил(а) вашу запись: {service}, {when}. Ждём вас!")


def notify_cancelled(booking, by):
    service, when = _describe(booking)
    provider, client = booking.slot.provider, booking.client
    if by == "provider":
        _send(client.email, "Запись отменена — BookIt",
              f"К сожалению, {provider.display_name} отменил(а) вашу запись: {service}, {when}.")
    else:
        _send(provider.email, "Клиент отменил запись — BookIt",
              f"{client.display_name} отменил(а) запись на «{service}», {when}. Слот снова свободен.")
