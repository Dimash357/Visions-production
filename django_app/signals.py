from django.db.models.signals import pre_save, post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.utils import timezone
from .models import profile, Task, Notification


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        profile.objects.create(user=instance, points=0)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    instance.profile.save()


@receiver(post_save, sender=Task)
def create_revision_notification(sender, instance, created, **kwargs):
    if not created:
        if instance.status == "process" and instance.rejection_reason:
            if not Notification.objects.filter(
                user=instance.user,
                message__icontains=f"Задание '{instance.title}' отправлено на доработку"
            ).exists():
                Notification.objects.create(
                    user=instance.user,
                    message=f"Ваше задание '{instance.title}' отправлено на доработку. Причина: {instance.rejection_reason}"
                )

@receiver(pre_save, sender=Task)
def reset_penalty_if_deadline_changed(sender, instance, **kwargs):
    """
    Если дедлайн продлили — сбрасываем флаг penalty_applied.
    """
    if instance.pk:  # значит, объект уже существует
        old_instance = Task.objects.get(pk=instance.pk)
        if old_instance.deadline != instance.deadline:
            # если новый дедлайн позже старого — сбрасываем штраф
            if instance.deadline > old_instance.deadline:
                instance.penalty_applied = False


