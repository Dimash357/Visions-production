from django import forms
from django.conf import settings

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from .models import Task, profile
from .security import validate_task_upload


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


def current_stream_students():
    from django.contrib.auth.models import User
    return (User.objects.filter(profile__is_former_user=False, is_staff=False, is_superuser=False, is_active=True)
            .order_by('username'))


class StudentChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.username.replace('_', ' ')


class _TaskFieldsMixin:
    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if not title:
            raise forms.ValidationError('Укажите название задания.')
        return title

    def clean_deadline(self):
        deadline = self.cleaned_data['deadline']
        if deadline < timezone.localtime().date():
            raise forms.ValidationError('Дедлайн не может быть в прошлом.')
        return deadline

    def clean_file(self):
        uploaded = self.cleaned_data.get('file')
        if uploaded and hasattr(uploaded, 'size') and not isinstance(uploaded, str):
            try:
                validate_task_upload(uploaded)
            except DjangoValidationError as exc:
                raise forms.ValidationError(exc.messages[0])
        return uploaded


class TaskCreateForm(_TaskFieldsMixin, forms.Form):
    title = forms.CharField(label='Название', max_length=255)
    description = forms.CharField(label='Описание', required=False, widget=forms.Textarea(attrs={'rows': 4}))
    deadline = forms.DateField(label='Дедлайн', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    file = forms.FileField(label='Файл задания', required=False)
    students = StudentChoiceField(label='Студенты', queryset=None, widget=forms.CheckboxSelectMultiple,
                                  error_messages={'required': 'Выберите хотя бы одного студента.'})
    # Ключ назначения из формы: повторная отправка той же формы не создаст дубли
    batch = forms.RegexField(regex=r'^[0-9a-f]{32}$', widget=forms.HiddenInput)
    # Дублирование: файл берётся из исходного назначения (по ключу группы, не по пути)
    source = forms.RegexField(regex=r'^[0-9a-f]{32}$', required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['students'].queryset = current_stream_students()

    def clean(self):
        data = super().clean()
        source_file = None
        if data.get('source'):
            source_file = (Task.objects.filter(group_key=data['source']).exclude(file='')
                           .values_list('file', flat=True).first())
        if not data.get('file') and not source_file:
            self.add_error('file', 'Прикрепите файл задания.')
        data['source_file'] = None if data.get('file') else source_file
        return data


class TaskEditForm(_TaskFieldsMixin, forms.Form):
    title = forms.CharField(label='Название', max_length=255)
    description = forms.CharField(label='Описание', required=False, widget=forms.Textarea(attrs={'rows': 4}))
    deadline = forms.DateField(label='Дедлайн', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    file = forms.FileField(label='Заменить файл', required=False)

    def clean_deadline(self):
        # При редактировании прошедший дедлайн допустим, если его не меняли
        deadline = self.cleaned_data['deadline']
        if deadline != self.initial.get('deadline') and deadline < timezone.localtime().date():
            raise forms.ValidationError('Дедлайн не может быть в прошлом.')
        return deadline


class DeadlineShiftForm(forms.Form):
    new_deadline = forms.DateField(label='Новый дедлайн', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    tasks = forms.ModelMultipleChoiceField(queryset=Task.objects.none(), widget=forms.CheckboxSelectMultiple,
                                           error_messages={'required': 'Выберите хотя бы одного студента.'})

    def __init__(self, *args, group_tasks=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tasks'].queryset = group_tasks if group_tasks is not None else Task.objects.none()

    def clean_new_deadline(self):
        value = self.cleaned_data['new_deadline']
        if value < timezone.localtime().date():
            raise forms.ValidationError('Дедлайн не может быть в прошлом.')
        return value
