"""Защита от перебора паролей и проверка загружаемых файлов."""
import hashlib
import os

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError


# ---------- Brute force ----------

def client_ip(request):
    if getattr(settings, 'TRUST_X_FORWARDED_FOR', False):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            # последний адрес добавлен нашим reverse proxy — ему и доверяем
            return forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _key(kind, value):
    digest = hashlib.sha256(value.strip().lower().encode('utf-8')).hexdigest()[:32]
    return f'login-fail:{kind}:{digest}'


def login_blocked(request, identifier):
    return (
        cache.get(_key('id', identifier), 0) >= settings.LOGIN_FAILURE_LIMIT
        or cache.get(_key('ip', client_ip(request)), 0) >= settings.LOGIN_IP_FAILURE_LIMIT
    )


def register_login_failure(request, identifier):
    for key in (_key('id', identifier), _key('ip', client_ip(request))):
        if not cache.add(key, 1, settings.LOGIN_LOCKOUT_SECONDS):
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, settings.LOGIN_LOCKOUT_SECONDS)


def reset_login_failures(request, identifier):
    cache.delete(_key('id', identifier))


# ---------- Uploads ----------

_MAGIC = {
    '.pdf': [b'%PDF'],
    '.png': [b'\x89PNG\r\n\x1a\n'],
    '.jpg': [b'\xff\xd8\xff'],
    '.jpeg': [b'\xff\xd8\xff'],
    # OOXML и OpenDocument — это zip
    '.docx': [b'PK\x03\x04'], '.xlsx': [b'PK\x03\x04'], '.pptx': [b'PK\x03\x04'],
    '.odt': [b'PK\x03\x04'], '.ods': [b'PK\x03\x04'], '.odp': [b'PK\x03\x04'],
    '.zip': [b'PK\x03\x04', b'PK\x05\x06'],
    # старые форматы Office (OLE2)
    '.doc': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'], '.xls': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],
    '.ppt': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],
    '.rtf': [b'{\\rtf'],
}


def validate_task_upload(uploaded_file):
    """Расширение из белого списка, размер и сигнатура содержимого."""
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    allowed = [e.strip().lower() for e in settings.TASK_UPLOAD_EXTENSIONS if e.strip()]
    if ext not in allowed:
        raise ValidationError(
            'Этот тип файла не принимается. Допустимые форматы: %s.' % ', '.join(allowed)
        )
    max_bytes = settings.TASK_UPLOAD_MAX_MB * 1024 * 1024
    if uploaded_file.size == 0:
        raise ValidationError('Файл пустой. Выберите файл с ответом.')
    if uploaded_file.size > max_bytes:
        raise ValidationError(f'Файл больше {settings.TASK_UPLOAD_MAX_MB} МБ. Сожмите его или загрузите архивом.')
    signatures = _MAGIC.get(ext)
    if signatures:
        head = uploaded_file.read(8)
        uploaded_file.seek(0)
        if not any(head.startswith(sig) for sig in signatures):
            raise ValidationError('Содержимое файла не соответствует его расширению.')
    return ext
