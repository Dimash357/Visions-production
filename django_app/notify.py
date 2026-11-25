"""Фоновая отправка писем и сообщений в Telegram без внешних очередей."""
import logging
import threading

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction

logger = logging.getLogger(__name__)


def _send_email(subject, body, to):
    try:
        EmailMessage(subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=to).send()
    except Exception:
        logger.exception("E-mail '%s' was not sent", subject)


def send_email_now(subject, body, to):
    """Синхронная отправка — для cron-команд (фоновый поток умер бы вместе с процессом)."""
    to = [addr for addr in to if addr]
    if to:
        _send_email(subject, body, to)


def send_email_background(subject, body, to):
    """Письмо уходит после коммита транзакции в отдельном потоке и не задерживает ответ."""
    to = [addr for addr in to if addr]
    if not to:
        return
    if getattr(settings, 'EMAIL_SYNC', False):  # для тестов
        transaction.on_commit(lambda: _send_email(subject, body, to))
        return
    # daemon=False: при штатном перезапуске воркера gunicorn интерпретатор дождётся отправки
    transaction.on_commit(
        lambda: threading.Thread(target=_send_email, args=(subject, body, to), daemon=False).start()
    )


class TelegramError(Exception):
    pass


def telegram_api(method, **params):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return None
    try:
        response = requests.post(f'https://api.telegram.org/bot{token}/{method}', json=params, timeout=15)
    except requests.RequestException as exc:
        # Текст исключения requests содержит URL с токеном бота — в логи его не пускаем
        raise TelegramError(f'{method}: network error ({type(exc).__name__})') from None
    if response.status_code != 200:
        try:
            description = response.json().get('description', '')
        except ValueError:
            description = ''
        raise TelegramError(f'{method}: HTTP {response.status_code} {description}'.strip())
    return response.json()


def send_telegram(chat_id, text):
    if not chat_id or not settings.TELEGRAM_BOT_TOKEN:
        return False
    try:
        telegram_api('sendMessage', chat_id=chat_id, text=text, disable_web_page_preview=True)
        return True
    except TelegramError as exc:
        logger.warning("Telegram message was not sent: %s", exc)
        return False
