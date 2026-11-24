from django.conf import settings
from django.contrib import admin
import posixpath

from django.http import Http404
from django.urls import include, path, re_path
from django.views.static import serve


def serve_public_media(request, path):
    # Нормализуем путь до проверки, чтобы 'profile_images/../tasks1/x' не обходил ограничение
    normalized = posixpath.normpath(path).lstrip('/')
    if not normalized.startswith('profile_images/') or '..' in normalized.split('/'):
        raise Http404
    return serve(request, normalized, document_root=settings.MEDIA_ROOT)

def admin_login(request, extra_context=None):
    """Вход в /admin/ с тем же лимитом попыток, что и основной вход."""
    from django.http import HttpResponse
    from django_app.security import login_blocked, register_login_failure, reset_login_failures

    if request.method == 'POST':
        identifier = request.POST.get('username', '')
        if login_blocked(request, identifier):
            return HttpResponse('Слишком много неудачных попыток входа. Подождите 15 минут.', status=429)
        response = admin.site.login(request, extra_context)
        if response.status_code == 302:
            reset_login_failures(request, identifier)
        else:
            register_login_failure(request, identifier)
        return response
    return admin.site.login(request, extra_context)


urlpatterns = [
    path('grappelli/', include('grappelli.urls')),  # grappelli URLS
    path('admin/login/', admin_login),
    path('admin/', admin.site.urls),
    path('', include('django_app.urls')),
]

# Без nginx статику и публичные медиа (аватары) отдаёт Django.
# Файлы заданий (media/tasks, media/tasks1) публично НЕ раздаются — только через
# django_app:task_file с проверкой прав.
if settings.SERVE_FILES_WITH_DJANGO:
    static_prefix = settings.STATIC_URL.lstrip('/')
    media_prefix = settings.MEDIA_URL.lstrip('/')
    urlpatterns += [
        re_path(r'^%s(?P<path>.*)$' % static_prefix, serve, {'document_root': settings.STATIC_ROOT}),
        re_path(r'^%s(?P<path>.*)$' % media_prefix, serve_public_media),
    ]
