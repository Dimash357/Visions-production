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

    def save(self, *args, **kwargs):
        from django.utils import timezone

        is_new = self.pk is None  # проверяем, новое ли это задание

        today = timezone.localtime().date()
        current_deadline = self.extended_deadline if self.extended_deadline else self.deadline

        # Обновляем статус
        if self.is_approved:
            self.status = "completed"
            self.is_completed = True
            self.in_process = False
        elif self.rejection_reason and not self.is_approved:
            self.status = "rejected"
            self.in_process = True
        elif not self.is_completed and current_deadline < today:
            self.status = "overdue"

            # 🔹 АВТОМАТИЧЕСКИЙ ШТРАФ ЗА ПРОСРОЧКУ
            if self.user and not self.penalty_applied:
                profile_obj = self.user.profile
                profile_obj.points = max(0, profile_obj.points - 100)
                profile_obj.save()

                Notification.objects.create(
                    user=self.user,
                    message=f"У вас отняли 100 очков за несвоевременное выполнение задания '{self.title}'."
                )
                self.penalty_applied = True

        elif self.is_completed and not self.is_approved and not self.rejection_reason:
            self.status = "pending"
        elif not self.is_completed and self.extended_deadline and self.extended_deadline >= today:
            self.status = "deadline_extended"
        else:
            self.status = "process"

        # --- НАЧИСЛЕНИЕ ОЧКОВ ЗА ВЫПОЛНЕНИЕ ---
        if self.is_approved and self.status == "completed":
            profile_obj = self.user.profile
            if not Notification.objects.filter(
                    user=self.user,
                    message=f"Ваше задание '{self.title}' одобрено! Вы получили 300 очков."
            ).exists():
                profile_obj.points += 300
                profile_obj.save()

                Notification.objects.create(
                    user=self.user,
                    message=f"Ваше задание '{self.title}' одобрено! Вы получили 300 очков."
                )

        super().save(*args, **kwargs)

        if is_new:
            Notification.objects.create(
                user=self.user,
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