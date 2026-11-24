from django import forms
from django.conf import settings

from .models import profile


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = profile
        fields = ['image', 'description', 'city']

    def clean_image(self):
        image = self.cleaned_data.get('image')
        # ImageField уже проверяет, что это настоящее изображение (Pillow); добавляем лимит размера
        if image and hasattr(image, 'size') and image.size > settings.PROFILE_IMAGE_MAX_MB * 1024 * 1024:
            raise forms.ValidationError(f'Фото больше {settings.PROFILE_IMAGE_MAX_MB} МБ. Выберите файл поменьше.')
        return image
