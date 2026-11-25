"""Напоминания о дедлайне за 24 часа. Запускать по cron раз в час:
    0 * * * * cd /app && python manage.py send_deadline_reminders
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from django_app.models import Task
from django_app.notify import send_email_now, send_telegram


class Command(BaseCommand):
    help = 'Отправляет напоминания по заданиям с дедлайном в ближайшие 24 часа'

    def handle(self, *args, **options):
        now = timezone.localtime()
        tomorrow = (now + timedelta(hours=24)).date()
        today = now.date()
        # Дедлайн — конец дня; напоминаем, когда до него осталось не больше суток
        tasks = (Task.objects
                 .select_related('user', 'user__profile')
                 .filter(user__isnull=False, reminder_sent_at__isnull=True, is_completed=False,
                         is_approved=False, user__profile__is_former_user=False)
                 .filter(Q(extended_deadline__isnull=True, deadline__gte=today, deadline__lte=tomorrow)
                         | Q(extended_deadline__gte=today, extended_deadline__lte=tomorrow)))
        sent = 0
        link = settings.SITE_URL + reverse('django_app:homework')
        for task in tasks:
            # Атомарно «забираем» задание: параллельный запуск команды не продублирует напоминание
            if not Task.objects.filter(pk=task.pk, reminder_sent_at__isnull=True).update(reminder_sent_at=timezone.now()):
                continue
            deadline = (task.extended_deadline or task.deadline).strftime('%d.%m.%Y')
            text = (f"Напоминание: дедлайн по заданию «{task.title}» — {deadline}. "
                    f"Сдайте работу вовремя, чтобы не потерять 100 баллов.\n{link}")
            if not send_telegram(task.user.profile.telegram_chat_id, text):
                send_email_now('Дедлайн по заданию завтра', text, [task.user.email])
            sent += 1
        self.stdout.write(f'reminders: {sent}')
