from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Notification, Task, profile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        profile.objects.get_or_create(user=instance, defaults={'points': 0})


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


@receiver(pre_save, sender=Task)
def remember_previous_state(sender, instance, **kwargs):
    """Запоминаем прежние значения; при продлении дедлайна сбрасываем флаг штрафа."""
    instance._previous_rejection_reason = None
    if not instance.pk:
        return
    old = Task.objects.filter(pk=instance.pk).only('deadline', 'extended_deadline', 'rejection_reason').first()
    if old is None:
        return
    instance._previous_rejection_reason = old.rejection_reason
    if old.deadline != instance.deadline and instance.deadline > old.deadline:
        instance.penalty_applied = False
    if (old.deadline, old.extended_deadline) != (instance.deadline, instance.extended_deadline):
        instance.reminder_sent_at = None  # новый срок — новое напоминание


@receiver(post_save, sender=Task)
def create_revision_notification(sender, instance, created, **kwargs):
    """Уведомление о доработке — при каждом новом комментарии ментора (раньше не срабатывало никогда)."""
    if created or not instance.user_id:
        return
    reason = instance.rejection_reason
    if instance.status == "rejected" and reason and reason != getattr(instance, '_previous_rejection_reason', None):
        Notification.objects.create(
            user_id=instance.user_id,
            message=f"Ваше задание '{instance.title}' отправлено на доработку. Причина: {reason}"
        )
