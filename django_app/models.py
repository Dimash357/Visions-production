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
    in_process = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    recipient_email = models.EmailField(null=False, blank=False, default='sarsendimas@gmail.com')

    def save(self, *args, **kwargs):
        from .models import Notification

        if self.is_approved and not self.in_process:
            self.is_completed = True

            profile_obj = self.user.profile
            if not Notification.objects.filter(user=self.user, message=f"Ваше задание '{self.title}' одобрено! Вы получили 300 очков.").exists():
                profile_obj.points += 300
                profile_obj.save()

                Notification.objects.create(
                    user=self.user,
                    message=f"Ваше задание '{self.title}' одобрено! Вы получили 300 очков."
                )
                print(f"✅ Уведомление создано: {self.title}")

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:50]}"