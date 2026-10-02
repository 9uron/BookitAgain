from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import Review, Service

WEEKDAYS = [(0, "Пн"), (1, "Вт"), (2, "Ср"), (3, "Чт"), (4, "Пт"), (5, "Сб"), (6, "Вс")]
MAX_RANGE_DAYS = 62


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ("title", "category", "description", "duration_minutes", "price")
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}
        labels = {"category": "Категория"}


class SlotGenerateForm(forms.Form):
    service = forms.ModelChoiceField(queryset=Service.objects.none(), label="Услуга")
    date_from = forms.DateField(label="С даты", widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(
        label="По дату", required=False, widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Пусто — только один день",
    )
    weekdays = forms.TypedMultipleChoiceField(
        label="Дни недели", required=False, choices=WEEKDAYS, coerce=int,
        widget=forms.CheckboxSelectMultiple, help_text="Пусто — все дни диапазона",
    )
    start = forms.TimeField(label="Начало работы", widget=forms.TimeInput(attrs={"type": "time"}))
    end = forms.TimeField(label="Конец работы", widget=forms.TimeInput(attrs={"type": "time"}))

    def __init__(self, provider, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = provider.services.filter(is_active=True)

    def clean(self):
        data = super().clean()
        d_from, d_to = data.get("date_from"), data.get("date_to")
        if data.get("start") and data.get("end") and data["end"] <= data["start"]:
            raise forms.ValidationError("Конец работы должен быть позже начала.")
        if not d_from:
            return data
        d_to = d_to or d_from
        if d_to < d_from:
            raise forms.ValidationError("Дата «По» раньше даты «С».")
        if d_to < timezone.localdate():
            raise forms.ValidationError("Нельзя создавать слоты на прошедшие дни.")
        if (d_to - d_from).days > MAX_RANGE_DAYS:
            raise forms.ValidationError(f"Максимальный диапазон — {MAX_RANGE_DAYS} дней.")
        wanted = set(data.get("weekdays") or range(7))
        days = [d_from + timedelta(days=i) for i in range((d_to - d_from).days + 1)]
        data["days"] = [d for d in days if d.weekday() in wanted]
        if not data["days"]:
            raise forms.ValidationError("В выбранном диапазоне нет подходящих дней недели.")
        return data


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(i, i) for i in range(1, 6)], coerce=int, widget=forms.RadioSelect, label="Оценка")

    class Meta:
        model = Review
        fields = ("rating", "text")
