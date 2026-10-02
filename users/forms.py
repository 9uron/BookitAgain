from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    role = forms.ChoiceField(
        label="Кто вы?",
        choices=[
            (User.Role.CLIENT, "Клиент — хочу записываться"),
            (User.Role.PROVIDER, "Специалист — принимаю записи"),
        ],
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "email", "phone", "role")
        labels = {"first_name": "Имя", "phone": "Телефон", "username": "Логин"}


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "specialty", "bio")
        labels = {"first_name": "Имя", "last_name": "Фамилия", "email": "Email (для уведомлений)"}
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.role != User.Role.PROVIDER:
            del self.fields["specialty"]
            del self.fields["bio"]
