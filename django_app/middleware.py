from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils.timezone import now


class AutoLogoutMiddleware:
    """Выход из системы после SESSION_TIMEOUT секунд бездействия."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            last_activity = request.session.get('last_activity')
            current = now().timestamp()
            if last_activity is not None and (current - last_activity) > settings.SESSION_TIMEOUT:
                logout(request)  # flush() очищает сессию целиком
                return redirect('django_app:login')
            request.session['last_activity'] = current
        return self.get_response(request)
