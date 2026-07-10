from django.contrib.auth import logout
from django.utils.timezone import now
from django.conf import settings

class AutoLogoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if 'last_activity' in request.session:
                last_activity = request.session['last_activity']
                session_timeout = settings.SESSION_TIMEOUT  # 30 минут
                if (now().timestamp() - last_activity) > session_timeout:
                    logout(request)
                    del request.session['last_activity']
                    return redirect('django_app:login')
            request.session['last_activity'] = now().timestamp()
        return self.get_response(request)
