from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.apps import AppConfig
from .models import profile


class DjangoAppConfig(AppConfig):
    name = 'django_app'

    def ready(self):
        import django_app.signals


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = profile
        fields = ['image', 'description', 'city']





# class FileUploadForm(forms.Form):
#     attachment = forms.FileField()