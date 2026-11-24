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
    is_former_user = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.user.username}'


class Task(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks', null=True)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='tasks/')
    deadline = models.DateField(default=timezone.now)
    extended_deadline = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    in_process = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True, null=True)
    recipient_email = models.EmailField(null=False, blank=False, default='sarsendimas@gmail.com')
    penalty_applied = models.BooleanField(default=False)
    user_response_file = models.FileField(upload_to='tasks1/', blank=True, null=True)

    STATUS_CHOICES = [
        ('pending', 'Ожидает проверки'),
        ('process', 'В процессе выполнения'),
        ('completed', 'Одобрено'),
        ('rejected', 'Отклонено'),
        ('overdue', 'Просрочено'),
        ('deadline_extended', 'Срок продлен'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='process')

    # Защита от повторного начисления 300 баллов (раньше проверялось по тексту уведомления)
    points_awarded = models.BooleanField(default=False, db_default=False, editable=False)

    APPROVAL_POINTS = 300
    OVERDUE_PENALTY = 100

    def approval_message(self):
        return f"Ваше задание '{self.title}' одобрено! Вы получили {self.APPROVAL_POINTS} очков."

    def compute_status(self, today=None):
        """Статус задания без побочных эффектов (та же логика, что раньше была в save)."""
        today = today or timezone.localtime().date()
        current_deadline = self.extended_deadline or self.deadline
        if self.is_approved:
            return "completed"
        if self.rejection_reason:
            return "rejected"
        if not self.is_completed and current_deadline < today:
            return "overdue"
        if self.is_completed:
            return "pending"
        if self.extended_deadline and self.extended_deadline >= today:
            return "deadline_extended"
        return "process"

    def needs_refresh(self, today=None):
        status = self.compute_status(today)
        return status != self.status or (status == "overdue" and self.user_id and not self.penalty_applied)

    def _claim_flag(self, field):
        """Атомарно переводит флаг False -> True в БД. True — только у одного из параллельных сохранений."""
        if self.pk is None:
            return True
        return type(self).objects.filter(pk=self.pk, **{field: False}).update(**{field: True}) == 1

    def save(self, *args, **kwargs):
        from django.db import transaction
        from django.db.models import F, Value
        from django.db.models.functions import Greatest

        is_new = self.pk is None
        self.status = self.compute_status()

        with transaction.atomic():
            if self.status == "completed":
                self.is_completed = True
                self.in_process = False
            elif self.status == "rejected":
                self.in_process = True
            elif self.status == "overdue" and self.user_id and not self.penalty_applied:
                # Автоматический штраф за просрочку: строго один раз, даже при параллельных сохранениях
                if self._claim_flag('penalty_applied'):
                    profile.objects.filter(user_id=self.user_id).update(
                        points=Greatest(F('points') - self.OVERDUE_PENALTY, Value(0))
                    )
                    Notification.objects.create(
                        user_id=self.user_id,
                        message=f"У вас отняли {self.OVERDUE_PENALTY} очков за несвоевременное выполнение задания '{self.title}'."
                    )
                self.penalty_applied = True

            # Начисление очков за выполнение — строго один раз
            if self.status == "completed" and self.user_id and not self.points_awarded:
                # Сначала запись (захват флага), затем чтение: на SQLite транзакция, начатая
                # с чтения, при попытке записи может получить «database is locked».
                if self._claim_flag('points_awarded') and not Notification.objects.filter(
                        user_id=self.user_id, message=self.approval_message()).exists():
                    profile.objects.filter(user_id=self.user_id).update(points=F('points') + self.APPROVAL_POINTS)
                    Notification.objects.create(user_id=self.user_id, message=self.approval_message())
                self.points_awarded = True

            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {
                    'status', 'is_completed', 'in_process', 'penalty_applied', 'points_awarded'}

            super().save(*args, **kwargs)

            if is_new and self.user_id:
                Notification.objects.create(
                    user_id=self.user_id,
                    message=f"📚 Вам назначено новое задание: '{self.title}'."
                )

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:50]}"