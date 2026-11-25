import logging
from datetime import timedelta
import mimetypes
import os
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST

from .forms import ProfileUpdateForm
from .models import Notification, Reward, RewardRedemption, SocialClaim, Task, profile
from .notify import send_email_background
from .security import (
    client_ip,
    login_blocked,
    register_login_failure,
    reset_login_failures,
    validate_task_upload,
)

logger = logging.getLogger(__name__)

NOTIFICATIONS_ON_PAGE = 50
PROFILE_BONUS_POINTS = 200
PROFILE_BONUS_MESSAGE = "Вы заполнили все данные и получили 200 очков!"


def is_admin(user):
    return user.is_superuser


def is_staff(user):
    return user.is_staff or user.is_superuser


def award_points_once(user, message, points):
    """Начисляет баллы один раз на (пользователь, сообщение). Безопасно при параллельных запросах:
    первая операция в транзакции — UPDATE строки профиля, она берёт блокировку записи
    (row lock в PostgreSQL, write lock в SQLite), поэтому проверки сериализуются."""
    with transaction.atomic():
        locked = profile.objects.filter(user=user).update(points=F('points'))
        if not locked or Notification.objects.filter(user=user, message=message).exists():
            return False
        profile.objects.filter(user=user).update(points=F('points') + points)
        Notification.objects.create(user=user, message=message)
        return True


def refresh_task_statuses(tasks):
    """Пересохраняет только задания, у которых изменился статус (или нужен штраф)."""
    today = timezone.localtime().date()
    for task in tasks:
        if task.needs_refresh(today):
            task.save()


# ---------- Admin ----------

@login_required
@user_passes_test(is_admin)
def admin_panel(request):
    users = profile.objects.filter(is_former_user=False).select_related('user').order_by('-points')
    tasks = list(Task.objects.filter(user=request.user).order_by('is_completed'))
    refresh_task_statuses(tasks)
    return render(request, 'django_app/admin.html', {'tasks': tasks, 'users': users})


@login_required
@user_passes_test(is_admin)
@require_POST
def approve_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    task.is_approved = True
    task.save()
    return redirect('django_app:admin_panel')


# ---------- Notifications ----------

@login_required
@require_POST
def mark_as_read(request, notification_id):
    updated = Notification.objects.filter(id=notification_id, user=request.user).update(is_read=True)
    if not updated:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    return JsonResponse({'success': True})


# ---------- Social subscriptions ----------

SOCIAL_NETWORKS = {
    'telegram': ('Telegram', 'https://t.me/visionskz'),
    'youtube': ('Youtube', 'https://www.youtube.com/@visionskz'),
    'linkedn': ('Linkedn', 'https://linkedn'),
    'instagram': ('Instagram', 'https://www.instagram.com/visions_kz/'),
    'facebook': ('Facebook', 'https://www.facebook.com/profile.php?id=61558414774839'),
}


def _social_message(label):
    return f"Вы подписались на {label} и получили 100 очков!"


def _social_subscription(request, network):
    """Переход на соцсеть. Баллы — после подтверждения сотрудником (или сразу, если так настроено)."""
    label, target = SOCIAL_NETWORKS[network]
    message = _social_message(label)

    if Notification.objects.filter(user=request.user, message=message).exists():
        messages.info(request, f"Вы уже получили баллы за подписку на {label}.")
        return redirect(target)

    if settings.SOCIAL_POINTS_AUTO_AWARD:
        if award_points_once(request.user, message, 100):
            messages.success(request, f"Вы успешно подписались на {label}! Баллы начислены.")
        return redirect(target)

    claim, created = SocialClaim.objects.get_or_create(user=request.user, network=network)
    if created:
        messages.success(request, f"Заявка за подписку на {label} отправлена. Баллы начислим после проверки.")
    elif claim.status == SocialClaim.REJECTED:
        messages.info(request, f"Подписка на {label} не подтверждена. Если вы подписались, напишите куратору.")
    else:
        messages.info(request, f"Заявка за подписку на {label} уже на проверке.")
    return redirect(target)


@login_required
def check_subscription_telegram(request):
    return _social_subscription(request, 'telegram')


@login_required
def check_subscription_youtube(request):
    return _social_subscription(request, 'youtube')


@login_required
def check_subscription_linkedn(request):
    return _social_subscription(request, 'linkedn')


@login_required
def check_subscription_instagram(request):
    return _social_subscription(request, 'instagram')


@login_required
def check_subscription_facebook(request):
    return _social_subscription(request, 'facebook')


# ---------- Pages ----------

def home_view(request: HttpRequest) -> HttpResponse:
    return render(request, 'django_app/welcome.html')


def scrum_welcome(request):
    return render(request, 'django_app/welcome.html')


def instructions(request):
    return render(request, 'django_app/instructions.html')


def about(request):
    return render(request, 'django_app/about.html')


def home_main(request):
    if not request.user.is_authenticated:
        return redirect('django_app:home')

    filter_former = request.GET.get('former')
    users = (profile.objects
             .filter(is_former_user=(filter_former == 'yes'))
             .select_related('user')
             .order_by('-points', 'user__username'))

    # Уведомления больше не помечаются прочитанными при открытии страницы:
    # непрочитанные видны, отметка ставится по клику.
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:NOTIFICATIONS_ON_PAGE]

    page_obj = Paginator(users, 5).get_page(request.GET.get('page'))

    return render(request, 'django_app/home_main.html', {
        'users': users,
        'notifications': notifications,
        'filter_former': filter_former,
        'page_obj': page_obj,
    })


def homework(request):
    if not request.user.is_authenticated:
        return redirect('django_app:login')

    if is_staff(request.user):
        refresh_task_statuses(Task.objects.select_related('user'))
        users = (User.objects
                 .filter(profile__is_former_user=False)
                 .select_related('profile')
                 .order_by('-profile__points'))
        pending = (Task.objects.filter(status='pending', user__isnull=False)
                   .select_related('user').order_by(F('submitted_at').asc(nulls_last=True), 'deadline'))
        return render(request, 'django_app/homework_admin.html', {
            'users': users,
            'pending': pending,
            'open_requests': (SocialClaim.objects.filter(status=SocialClaim.PENDING).count()
                              + RewardRedemption.objects.filter(status=RewardRedemption.REQUESTED).count()),
        })

    tasks = list(Task.objects.filter(user=request.user).order_by('is_completed'))
    refresh_task_statuses(tasks)
    return render(request, 'django_app/homework.html', {'tasks': tasks})


@login_required
def user_homework_detail(request, user_id):
    if not is_staff(request.user):
        return redirect('django_app:homework')

    user = get_object_or_404(User, id=user_id)
    tasks = Task.objects.filter(user=user).order_by('-deadline')
    return render(request, 'django_app/user_homework_detail.html', {'user': user, 'tasks': tasks})


# ---------- Files ----------

@login_required
def task_file(request, task_id, kind):
    """Отдаёт файл задания или ответа только владельцу задания и сотрудникам."""
    task = get_object_or_404(Task, id=task_id)
    if task.user_id != request.user.id and not is_staff(request.user):
        raise Http404
    field = {'assignment': task.file, 'response': task.user_response_file}.get(kind)
    if not field:
        raise Http404

    filename = os.path.basename(field.name)
    accel_prefix = settings.PROTECTED_MEDIA_ACCEL_PREFIX
    if accel_prefix:
        response = HttpResponse()
        response['X-Accel-Redirect'] = accel_prefix.rstrip('/') + '/' + field.name
        response['Content-Type'] = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        response['Content-Disposition'] = content_disposition_header(True, filename)
    else:
        try:
            handle = field.open('rb')
        except FileNotFoundError:
            raise Http404
        response = FileResponse(handle, as_attachment=True, filename=filename)
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_POST
def upload_task(request, task_id):
    task = Task.objects.filter(id=task_id, user=request.user).first()
    if task is None:
        logger.warning("Upload to foreign or missing task %s by user %s", task_id, request.user.pk)
        return redirect('django_app:homework')

    if task.is_completed or task.status in ('pending', 'completed'):
        messages.info(request, f"Задание «{task.title}» уже отправлено на проверку.")
        return redirect('django_app:homework')

    uploaded_file = request.FILES.get('attachment')
    if uploaded_file is None:
        messages.error(request, "Выберите файл с ответом.")
        return redirect('django_app:homework')

    try:
        extension = validate_task_upload(uploaded_file)
    except ValidationError as exc:
        messages.error(request, f"«{task.title}»: {exc.messages[0]}")
        return redirect('django_app:homework')

    base = re.sub(r'\.{2,}', '.', get_valid_filename(f"{task.title}_{request.user.username}".replace(' ', '_')))
    base = base.strip('.')[:120] or 'answer'
    uploaded_file.name = f"{base}{extension}"

    task.user_response_file = uploaded_file
    task.is_completed = True
    task.is_approved = False
    task.in_process = False
    # Повторная сдача после доработки: комментарий ментора уже сохранён в уведомлении,
    # поэтому сбрасываем его, чтобы задание снова попало в статус «Ждёт проверки».
    task.rejection_reason = None
    task.submitted_at = timezone.now()
    task.save()

    Notification.objects.create(
        user=request.user,
        message=f"Вы загрузили задание '{task.title}', ожидайте проверки."
    )
    messages.success(request, f"Ответ на «{task.title}» отправлен на проверку.")

    review_url = request.build_absolute_uri(reverse('django_app:user_homework_detail', args=[request.user.id]))
    send_email_background(
        'Новое задание на проверку',
        f"{request.user.username} отправил(а) задание «{task.title}».\n"
        f"Проверить в кабинете: {review_url}",
        settings.TASK_NOTIFY_EMAILS,
    )

    return redirect('django_app:homework')


# ---------- Profile ----------

@login_required
def profile_create(request):
    return render(request, 'django_app/profile.html')


def _profile_complete(p):
    return bool(p.image and p.image.name != 'profile_images/default.jpg' and p.city and p.description)


@login_required
def profileupdate(request):
    user_profile = request.user.profile
    if request.method == 'POST':
        pform = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
        if pform.is_valid():
            pform.save()

            if _profile_complete(user_profile):
                if award_points_once(request.user, PROFILE_BONUS_MESSAGE, PROFILE_BONUS_POINTS):
                    messages.success(request, "Вы получили 200 очков за заполнение профиля!")

            messages.success(request, "Профиль сохранён.")
            return redirect('django_app:profile')
    else:
        pform = ProfileUpdateForm(instance=user_profile)

    return render(request, 'django_app/profileupdate.html', {'pform': pform})


# ---------- Auth ----------

def _authenticate_identifier(request, identifier, password):
    if "@" in identifier:
        for candidate in User.objects.filter(email__iexact=identifier)[:5]:
            user = authenticate(request, username=candidate.username, password=password)
            if user:
                return user
        return None
    return authenticate(request, username=identifier, password=password)


def login_(request):
    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if login_blocked(request, identifier):
            logger.warning("Login temporarily blocked (ip=%s)", client_ip(request))
            return render(request, 'django_app/login.html', {
                'error_message': "Слишком много неудачных попыток входа. Подождите 15 минут.",
                'blocked': True,
            }, status=429)

        user = _authenticate_identifier(request, identifier, password) if identifier and password else None
        if user:
            reset_login_failures(request, identifier)
            login(request, user)
            request.session.set_expiry(settings.SESSION_TIMEOUT)
            return redirect(reverse('django_app:home_main'))

        register_login_failure(request, identifier)
        return render(request, 'django_app/login.html', {'error_message': "Логин или пароль неверны!"})

    return render(request, 'django_app/login.html')


def logout_f(request):
    # Выход только POST-запросом (защита от CSRF-logout через <img src="/logout/">)
    if request.method == 'POST':
        logout(request)
        return redirect(reverse('django_app:login'))
    if request.user.is_authenticated:
        return redirect('django_app:home_main')
    return redirect('django_app:login')


# ---------- Mentor review ----------

@login_required
@user_passes_test(is_staff)
@require_POST
def review_task(request, task_id):
    """Ментор принимает работу или возвращает её на доработку с комментарием."""
    task = get_object_or_404(Task.objects.select_related('user'), id=task_id)
    back = redirect('django_app:user_homework_detail', user_id=task.user_id)
    action = request.POST.get('action')
    comment = request.POST.get('comment', '').strip()

    if action not in ('accept', 'return'):
        return back
    if action == 'return' and not comment:
        messages.error(request, "Напишите, что нужно исправить: без комментария студент не поймёт, что доработать.")
        return back

    with transaction.atomic():
        # Только один из параллельных запросов (двух менторов) может принять решение по работе
        claimed = Task.objects.filter(pk=task.pk, status='pending').update(reviewed_at=timezone.now())
        if not claimed:
            messages.info(request, f"«{task.title}» уже не ждёт проверки.")
            return back
        task.refresh_from_db()
        subject, text = _apply_review(request, task, action, comment)

    send_email_background(subject, f"{text}\n\n{settings.SITE_URL}{reverse('django_app:homework')}", [task.user.email])
    return back


def _apply_review(request, task, action, comment):
    if action == 'accept':
        task.is_approved = True
        task.save()
        subject, text = 'Задание принято', f"Ментор принял задание «{task.title}». Начислено {Task.APPROVAL_POINTS} баллов."
        if comment:
            text += f"\nКомментарий: {comment}"
            Notification.objects.create(user=task.user, message=f"Комментарий к заданию '{task.title}': {comment}")
        messages.success(request, f"«{task.title}» принято, студенту начислено {Task.APPROVAL_POINTS} баллов.")
    else:
        task.rejection_reason = comment[:2000]
        task.is_completed = False
        task.in_process = True
        task.save()  # уведомление о доработке создаёт сигнал
        subject, text = 'Задание на доработке', f"Ментор вернул задание «{task.title}» на доработку.\nКомментарий: {comment}"
        messages.success(request, f"«{task.title}» возвращено на доработку.")
    return subject, text


# ---------- Rewards ----------

@login_required
def rewards(request):
    balance = request.user.profile.available_points()
    reward_list = list(Reward.objects.filter(is_active=True))
    for reward in reward_list:
        reward.missing = max(0, reward.cost - balance)
    return render(request, 'django_app/rewards.html', {
        'rewards': reward_list,
        'balance': balance,
        'my_redemptions': RewardRedemption.objects.filter(user=request.user).select_related('reward')[:20],
    })


@login_required
@require_POST
def redeem_reward(request, reward_id):
    reward = get_object_or_404(Reward, id=reward_id, is_active=True)
    with transaction.atomic():
        # Блокируем строку профиля (на SQLite — блокировка записи), чтобы двойной клик не потратил баллы дважды
        profile.objects.filter(user=request.user).update(points=F('points'))
        user_profile = profile.objects.get(user=request.user)
        if user_profile.available_points() < reward.cost:
            messages.error(request, f"Не хватает баллов: нужно {reward.cost}, доступно {user_profile.available_points()}.")
            return redirect('django_app:rewards')
        RewardRedemption.objects.create(user=request.user, reward=reward, cost=reward.cost)
        Notification.objects.create(user=request.user,
                                    message=f"Заявка на награду «{reward.title}» принята. Мы свяжемся с вами.")
    send_email_background(
        'Заявка на награду',
        f"{request.user.username} обменял(а) {reward.cost} баллов на «{reward.title}».\n"
        f"Обработать: {settings.SITE_URL}{reverse('django_app:staff_requests')}",
        settings.STAFF_NOTIFY_EMAILS,
    )
    messages.success(request, f"Заявка на «{reward.title}» отправлена. Куратор свяжется с вами.")
    return redirect('django_app:rewards')


# ---------- Staff requests (social claims, rewards) ----------

@login_required
@user_passes_test(is_staff)
def staff_requests(request):
    if request.method == 'POST':
        kind, action = request.POST.get('kind'), request.POST.get('action')
        obj_id = request.POST.get('id', '')
        if not obj_id.isdigit():
            return redirect('django_app:staff_requests')
        now = timezone.now()
        if kind == 'claim' and action in ('approve', 'reject'):
            status = SocialClaim.APPROVED if action == 'approve' else SocialClaim.REJECTED
            with transaction.atomic():
                # Решение по заявке принимается ровно один раз, даже при двух одновременных кликах
                if SocialClaim.objects.filter(id=obj_id, status=SocialClaim.PENDING).update(
                        status=status, reviewed_at=now, reviewed_by=request.user):
                    claim = SocialClaim.objects.select_related('user').get(id=obj_id)
                    label = SOCIAL_NETWORKS.get(claim.network, (claim.network,))[0]
                    if action == 'approve':
                        award_points_once(claim.user, _social_message(label), 100)
                    else:
                        Notification.objects.create(user=claim.user,
                                                    message=f"Подписка на {label} не подтверждена.")
        elif kind == 'redemption' and action in ('fulfill', 'cancel'):
            status = RewardRedemption.FULFILLED if action == 'fulfill' else RewardRedemption.CANCELLED
            with transaction.atomic():
                if RewardRedemption.objects.filter(id=obj_id, status=RewardRedemption.REQUESTED).update(
                        status=status, handled_at=now, handled_by=request.user):
                    red = RewardRedemption.objects.select_related('reward').get(id=obj_id)
                    text = (f"Награда «{red.reward.title}» выдана." if action == 'fulfill'
                            else f"Заявка на «{red.reward.title}» отменена, {red.cost} баллов вернулись на баланс.")
                    Notification.objects.create(user_id=red.user_id, message=text)
        return redirect('django_app:staff_requests')

    return render(request, 'django_app/staff_requests.html', {
        'claims': SocialClaim.objects.filter(status=SocialClaim.PENDING).select_related('user'),
        'redemptions': RewardRedemption.objects.filter(status=RewardRedemption.REQUESTED).select_related('user', 'reward'),
        'networks': {k: v[0] for k, v in SOCIAL_NETWORKS.items()},
    })


# ---------- Telegram ----------

@login_required
@require_POST
def telegram_connect(request):
    import secrets
    bot = settings.TELEGRAM_BOT_USERNAME
    if not (bot and settings.TELEGRAM_BOT_TOKEN):
        messages.error(request, "Telegram-бот пока не настроен. Напишите куратору.")
        return redirect('django_app:profile')
    token = secrets.token_urlsafe(24)
    profile.objects.filter(user=request.user).update(
        telegram_link_token=token, telegram_link_expires=timezone.now() + timedelta(minutes=30))
    return redirect(f"https://t.me/{bot}?start={token}")


@login_required
@require_POST
def telegram_disconnect(request):
    profile.objects.filter(user=request.user).update(telegram_chat_id='', telegram_link_token='', telegram_link_expires=None)
    messages.success(request, "Telegram отключён. Напоминания будут приходить на почту.")
    return redirect('django_app:profile')


# ---------- Analytics ----------

@login_required
@user_passes_test(is_staff)
def analytics(request):
    from .analytics import cohort_report
    return render(request, 'django_app/analytics.html', cohort_report())
