from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='profile_images', default='profile_images/default.jpg')
    description = models.TextField(max_length=255, blank=False)
    city = models.TextField(max_length=255, blank=False)
    points = models.IntegerField(default=0)
    is_eligible_for_testing = models.BooleanField(default=False)
    passed_testing = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.user.username}'


class Task(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks', null=True)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='tasks/')
    deadline = models.DateField(default=timezone.now)
    description = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    recipient_email = models.EmailField(null=False, blank=False, default='<EMAIL>')

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:50]}"


# class Todo(models.Model):
#     """
#     Модель Task
#     """
#
#     author = models.ForeignKey(
#         User, on_delete=models.CASCADE
#     )
#
#     title = models.CharField(
#         db_column='title_db_column',
#         db_index=True,
#         db_tablespace='title_db_tablespace',
#         error_messages=False,
#         primary_key=False,
#         validators=[MinLengthValidator(0), MaxLengthValidator(300), ],
#         unique=False,
#         editable=True,
#         blank=True,
#         null=True,
#         default='',
#         verbose_name='Заголовок',
#         help_text='<small class="text-muted">CharField [0, 300]</small><hr><br>',
#
#         max_length=300,
#     )
#     description = models.TextField(
#         db_column='description_db_column',
#         db_index=True,
#         db_tablespace='description_db_tablespace',
#         error_messages=False,
#         primary_key=False,
#         validators=[MinLengthValidator(0), MaxLengthValidator(3000), ],
#         unique=False,
#         editable=True,
#         blank=True,
#         null=True,
#         default="",
#         verbose_name='Описание',
#         help_text='<small class="text-muted">TextField [0, 3000]</small><hr><br>',
#
#         max_length=3000,
#     )
#     is_completed = models.BooleanField(
#         db_column='is_completed_db_column',
#         db_index=True,
#         db_tablespace='is_completed_db_tablespace',
#         error_messages=False,
#         primary_key=False,
#         unique=False,
#         editable=True,
#         blank=True,
#         null=False,
#         default=False,
#         verbose_name='Статус выполнения',
#         help_text='<small class="text-muted">BooleanField</small><hr><br>',
#     )
#     created = models.DateTimeField(
#         db_column='created_db_column',
#         db_index=True,
#         db_tablespace='created_db_tablespace',
#         error_messages=False,
#         primary_key=False,
#         unique=False,
#         editable=True,
#         blank=True,
#         null=True,
#         default=timezone.now,
#         verbose_name='Дата и время создания',
#         help_text='<small class="text-muted">DateTimeField</small><hr><br>',
#
#         auto_now=False,
#         auto_now_add=False,
#     )
#     updated = models.DateTimeField(
#         db_column='updated_db_column',
#         db_index=True,
#         db_tablespace='updated_db_tablespace',
#         error_messages=False,
#         primary_key=False,
#         unique=False,
#         editable=True,
#         blank=True,
#         null=True,
#         default=timezone.now,
#         verbose_name='Дата и время обновления',
#         help_text='<small class="text-muted">DateTimeField</small><hr><br>',
#
#         auto_now=False,
#         auto_now_add=False,
#     )
#
#     class Meta:
#         app_label = 'django_app'
#         ordering = ('-updated',)
#         verbose_name = 'Todo'
#         verbose_name_plural = 'Todos'
#         # db_table = 'task_task_list_model_table'
#
#     def __str__(self):
#         if self.is_completed:
#             completed = "Активно"
#         else:
#             completed = "Неактивно"
#         return f"{self.title} | {self.description[0:30]}... | {completed} | {self.updated}"
#
#
# CHOICES = (
#     ("1", "DANGER"),
#     ("2", "WARNING"),
#     ("3", "LIGHT"),
#     ("4", "INFO"),
# )


# class Logging(models.Model):
#     user = models.ForeignKey(User, on_delete=models.DO_NOTHING, blank=False, db_index=True)
#     method = models.CharField(max_length=7)
#     status = models.IntegerField(validators=[MinValueValidator(100), MaxValueValidator(600)])
#     url = models.CharField(max_length=300, default="")
#     description = models.CharField(max_length=500)
#     datetime = models.DateTimeField(default=timezone.now, db_index=True)
#     level = models.CharField(max_length=50, choices=CHOICES, default="4")
#
#     class Meta:
#         app_label = 'django_app'
#         ordering = ('-datetime', 'url')
#         verbose_name = 'Log'
#         verbose_name_plural = 'Logs'
#
#     def __str__(self):
#         return f"{self.datetime} | {self.status} | {self.url} | {self.user}"
