import os
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.text import slugify
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.core.mail import EmailMessage
from django.conf import settings
from django.core.paginator import Paginator


from django_app import models
from .forms import ProfileUpdateForm
from django.utils import timezone
from .models import profile, Notification
from django.shortcuts import redirect
from django.contrib import messages
from .models import Task
from django.core.cache import cache
from django.contrib.auth.decorators import login_required


import requests
from django.http import JsonResponse
from django.conf import settings

# TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/getChatMember"
# CHANNEL_ID = "@visionskz"  # Ваш канал


from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from .models import User, Task

def is_admin(user):
    return user.is_superuser  # Или можно сделать кастомную проверку

@login_required
@user_passes_test(is_admin)
def admin_panel(request):
    today = timezone.now().date()
    users = profile.objects.filter(is_former_user=False).order_by('-points')
    tasks = Task.objects.filter(user=request.user).order_by('is_completed')

    for task in tasks:
        current_deadline = task.extended_deadline if task.extended_deadline else task.deadline

        if task.is_approved:
            task.status = "completed"
            task.is_completed = True
        elif task.rejection_reason and not task.is_approved:
            task.status = "rejected"
        elif not task.is_completed and current_deadline < today:
            task.status = "overdue"
        elif not task.is_completed and task.extended_deadline and task.extended_deadline >= today:
            task.status = "deadline_extended"
        elif task.in_process and not task.is_completed:
            task.status = "process"
        else:
            task.status = "pending"

        task.save(update_fields=['status', 'is_completed'])

    return render(request, 'django_app/admin.html', {'tasks': tasks, 'users': users})



@login_required
@user_passes_test(is_admin)
def approve_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    task.status = 'approved'  # Зависит от твоих названий
    task.save()
    return redirect('django_app:admin_panel')


@csrf_exempt
def mark_as_read(request, notification_id):
    if request.method == 'POST':
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.is_read = True
            notification.save()
            return JsonResponse({'success': True})
        except Notification.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

def check_subscription_telegram(request):
    """ Пользователь переходит на Telegram, и ему начисляются 100 очков """
    profile_obj = get_object_or_404(profile, user=request.user)

    # Проверяем, получал ли пользователь уже очки за подписку
    if not Notification.objects.filter(user=request.user, message="Вы подписались на Telegram и получили 100 очков!").exists():
        profile_obj.points += 100
        profile_obj.save()

        Notification.objects.create(
            user=request.user,
            message="Вы подписались на Telegram и получили 100 очков!"
        )
        messages.success(request, "Вы успешно подписались на Telegram! Баллы начислены.")
    else:
        messages.info(request, "Вы уже получили баллы за подписку на Telegram.")

    return redirect('https://t.me/visionskz')  # Переход на Telegram


def check_subscription_youtube(request):
    profile_obj = get_object_or_404(profile, user=request.user)

    # Проверяем, получал ли пользователь уже очки за подписку
    if not Notification.objects.filter(user=request.user, message="Вы подписались на Youtube и получили 100 очков!").exists():
        profile_obj.points += 100
        profile_obj.save()

        Notification.objects.create(
            user=request.user,
            message="Вы подписались на Youtube и получили 100 очков!"
        )
        messages.success(request, "Вы успешно подписались на Youtube! Баллы начислены.")
    else:
        messages.info(request, "Вы уже получили баллы за подписку на Youtube.")

    return redirect('https://www.youtube.com/@visionskz')  # Переход на Telegram


def check_subscription_linkedn(request):
    profile_obj = get_object_or_404(profile, user=request.user)

    # Проверяем, получал ли пользователь уже очки за подписку
    if not Notification.objects.filter(user=request.user, message="Вы подписались на Linkedn и получили 100 очков!").exists():
        profile_obj.points += 100
        profile_obj.save()

        Notification.objects.create(
            user=request.user,
            message="Вы подписались на Linkedn и получили 100 очков!"
        )
        messages.success(request, "Вы успешно подписались на Linkedn! Баллы начислены.")
    else:
        messages.info(request, "Вы уже получили баллы за подписку на Linkedn.")

    return redirect('https://linkedn')  # Переход на Telegram


def check_subscription_instagram(request):
    profile_obj = get_object_or_404(profile, user=request.user)

    if not Notification.objects.filter(user=request.user, message="Вы подписались на Instagram и получили 100 очков!").exists():
        profile_obj.points += 100
        profile_obj.save()

        Notification.objects.create(
            user=request.user,
            message="Вы подписались на Instagram и получили 100 очков!"
        )
        messages.success(request, "Вы успешно подписались на Instagram! Баллы начислены.")
    else:
        messages.info(request, "Вы уже получили баллы за подписку на Instagram.")

    return redirect('https://www.instagram.com/visions_kz/')  # Переход на Instagram


def check_subscription_facebook(request):
    profile_obj = get_object_or_404(profile, user=request.user)

    if not Notification.objects.filter(user=request.user, message="Вы подписались на Facebook и получили 100 очков!").exists():
        profile_obj.points += 100
        profile_obj.save()

        Notification.objects.create(
            user=request.user,
            message="Вы подписались на Facebook и получили 100 очков!"
        )
        messages.success(request, "Вы успешно подписались на Facebook! Баллы начислены.")
    else:
        messages.info(request, "Вы уже получили баллы за подписку на Facebook.")

    return redirect('https://www.facebook.com/profile.php?id=61558414774839')  # Переход на Instagram


def login_user(request):
    if not request.user.is_staff:  # Только для обычных пользователей
        user = authenticate(request, username='user', password='password')
        if user is not None:
            login(request, user)


def home_view(request: HttpRequest) -> HttpResponse:  # TODO контроллер функция
    context = {}
    return render(request, 'django_app/welcome.html', context=context)


def home_main(request):
    if not request.user.is_authenticated:
        return redirect('django_app:home')

    filter_former = request.GET.get('former')  # Получаем параметр из URL

    if filter_former == 'yes':
        users = profile.objects.filter(is_former_user=True).order_by('-points')
    else:
        users = profile.objects.filter(is_former_user=False).order_by('-points')

    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    notifications.update(is_read=True)

    paginator = Paginator(users, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'django_app/home_main.html', {
        'users': users,
        'notifications': notifications,
        'filter_former': filter_former,
        'page_obj': page_obj,
    })


def scrum_welcome(request):
    return render(request, 'django_app/welcome.html')


def instructions(request):
    return render(request, 'django_app/instructions.html')


def homework(request):
    if not request.user.is_authenticated:
        return redirect('django_app:login')

    if request.user.is_staff or request.user.is_superuser:
        tasks = Task.objects.all()
        for task in tasks:
            task.save()

        users = User.objects.filter(
            profile__is_former_user=False
        ).order_by('-profile__points')

        return render(request, 'django_app/homework_admin.html', {'users': users})

    tasks = Task.objects.filter(user=request.user).order_by('is_completed')

    for task in tasks:
        task.save()

    return render(request, 'django_app/homework.html', {'tasks': tasks})


@login_required
def user_homework_detail(request, user_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('django_app:homework')

    user = get_object_or_404(User, id=user_id)
    tasks = Task.objects.filter(user=user).order_by('-deadline')
    return render(request, 'django_app/user_homework_detail.html', {'user': user, 'tasks': tasks})


import os
from django.core.files.base import ContentFile

def upload_task(request, task_id):
    if request.method == 'POST':
        try:
            task = Task.objects.get(id=task_id, user=request.user)

            if 'attachment' not in request.FILES:
                return redirect('django_app:homework')

            uploaded_file = request.FILES['attachment']

            # --- 🔹 Генерация нового имени файла ---
            original_name = uploaded_file.name
            extension = os.path.splitext(original_name)[1]  # .pdf, .docx, .png и т.д.

            safe_title = task.title.replace(' ', '_')  # заменяем пробелы на "_"
            safe_username = request.user.username.replace(' ', '_')

            new_filename = f"{safe_title}_{safe_username}{extension}"

            # --- 🔹 Переименование файла ---
            uploaded_file.name = new_filename

            # --- 🔹 Сохраняем ---
            task.user_response_file = uploaded_file
            task.is_completed = True
            task.is_approved = False
            task.in_process = False
            task.save()

            # --- 🔹 Уведомление ---
            Notification.objects.create(
                user=request.user,
                message=f"Вы загрузили задание '{task.title}', ожидайте проверки."
            )

            email_subject = 'Новое загруженное задание'
            email_body = (
                f"Пользователь {request.user.username} загрузил задание:\n"
                f"Название: {task.title}\n"
                f"Файл: {uploaded_file.name}"
            )

            email = EmailMessage(
                subject=email_subject,
                body=email_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=['son090984@gmail.com'],  # ← твой email
            )

            # Прикрепляем файл
            email.attach_file(task.user_response_file.path)

            # Отправляем письмо
            email.send(fail_silently=False)

            return redirect('django_app:homework')

        except Task.DoesNotExist:
            print(f"Задание с ID {task_id} не найдено для пользователя {request.user.username}")
            return redirect('django_app:homework')
        except Exception as e:
            print(f"Ошибка при загрузке задания: {e}")
            return redirect('django_app:homework')



def about(request):
    return render(request, 'django_app/about.html')


def profile_create(request):
    return render(request, 'django_app/profile.html')


def profileupdate(request):
    if request.method == 'POST':
        profile = request.user.profile

        pform = ProfileUpdateForm(request.POST, request.FILES, instance=profile)

        if pform.is_valid():
            pform.save()

            if all([profile.image, profile.city, profile.description]):
                if profile.points == 100:
                    profile.points += 200
                    profile.save()

                    Notification.objects.create(
                        user=request.user,
                        message="Вы заполнили все данные и получили 200 очков!",
                    )

                    messages.success(request, "Вы получили 200 очков за заполнение профиля!")

            return redirect('django_app:profile')
    else:
        profile = request.user.profile
        pform = ProfileUpdateForm(instance=profile)

    return render(request, 'django_app/profileupdate.html', {'pform': pform})


# def register(request):
#     if request.method == "POST":
#         username = request.POST.get("username", "")
#         email = request.POST.get("email", "")
#         password = request.POST.get("password", "")
#
#         if User.objects.filter(username=username).exists():
#             error_message = "Пользователь с таким логином уже существует."
#             return render(request, 'django_app/register.html', {'error_message': error_message})
#
#         if User.objects.filter(email=email).exists():
#             error_message = "Пользователь с таким email уже существует."
#             return render(request, 'django_app/register.html', {'error_message': error_message})
#
#         try:
#             validate_password(password)
#         except ValidationError as e:
#             error_message = "Вы ввели очень легкий пароль"
    #         return render(request, 'django_app/register.html', {'error_message': error_message})
    #
    #     if username and email and password:
    #         user = User.objects.create_user(username=username, email=email, password=password)
    #         login(request, user)
    #
    #         profile = request.user.profile
    #         profile.points += 100
    #         profile.save()
    #
    #         Notification.objects.create(
    #             user=request.user,
    #             message=f"Вы зарегистрировались и получили 100 очков! Заполните свой профиль и получите еще 200 очков",
    #         )
    #         return redirect(reverse('django_app:home_main', args=()))
    #     else:
    #         error_message = "Все поля обязательны для заполнения."
    #         return render(request, 'django_app/register.html', {'error_message': error_message})
    # else:
    #     return render(request, 'django_app/register.html')


def login_(request):
    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()

        user = None
        if "@" in identifier:
            try:
                user = User.objects.get(email=identifier)
                username = user.username
            except User.DoesNotExist:
                username = None
        else:
            username = identifier

        if username:
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                request.session.set_expiry(settings.SESSION_TIMEOUT)  # Устанавливаем таймер на 30 минут
                return redirect(reverse('django_app:home_main'))

        return render(request, 'django_app/login.html', {'error_message': "Логин или пароль неверны!"})

    return render(request, 'django_app/login.html')


def logout_f(request):
    logout(request)
    return redirect(reverse('django_app:login', args=()))
