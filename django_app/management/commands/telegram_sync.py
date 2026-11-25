"""Привязывает чаты Telegram к профилям по ссылке t.me/<bot>?start=<token>.
Запускать по cron раз в минуту (вебхук не нужен):
    * * * * * cd /app && python manage.py telegram_sync
"""
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from django_app.models import profile
from django_app.notify import TelegramError, send_telegram, telegram_api

OFFSET_KEY = 'telegram-update-offset'


class Command(BaseCommand):
    help = 'Обрабатывает /start <token> в Telegram-боте'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            self.stdout.write('TELEGRAM_BOT_TOKEN is not set')
            return
        offset = cache.get(OFFSET_KEY, 0)
        try:
            data = telegram_api('getUpdates', offset=offset, timeout=0, allowed_updates=['message']) or {}
        except TelegramError as exc:
            self.stderr.write(f'telegram_sync failed: {exc}')
            return
        linked = 0
        for update in data.get('result', []):
            offset = max(offset, update['update_id'] + 1)
            message = update.get('message') or {}
            text = (message.get('text') or '').strip()
            chat = message.get('chat') or {}
            chat_id = str(chat.get('id', ''))
            # Только личные чаты: иначе напоминания студента уйдут в группу
            if not chat_id or chat.get('type') != 'private' or not text.startswith('/start'):
                continue
            token = text.split(maxsplit=1)[1] if ' ' in text else ''
            # Токен одноразовый и живёт 30 минут
            if token and profile.objects.filter(
                    telegram_link_token=token, telegram_link_expires__gt=timezone.now()).update(
                    telegram_chat_id=chat_id, telegram_link_token='', telegram_link_expires=None):
                linked += 1
                send_telegram(chat_id, 'Готово! Сюда будут приходить напоминания о дедлайнах Visions.')
            else:
                send_telegram(chat_id, 'Ссылка устарела. Откройте профиль на сайте и нажмите «Подключить Telegram» ещё раз.')
        cache.set(OFFSET_KEY, offset, None)
        self.stdout.write(f'linked: {linked}')
