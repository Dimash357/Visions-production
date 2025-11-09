import os
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from django_app import models
from .forms import ProfileUpdateForm
from django.utils import timezone
from .models import profile, Notification
from django.shortcuts import redirect
from django.contrib import messages
from .models import Task


import requests
from django.http import JsonResponse
from django.conf import settings

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/getChatMember"
CHANNEL_ID = "@visionskz"  # Ваш канал


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
    telegram_username = request.GET.get("username")  # Имя пользователя Telegram
    if not telegram_username:
        return JsonResponse({"success": False, "message": "Введите ваш Telegram username."})

    url = TELEGRAM_API_URL.format(token=settings.TELEGRAM_BOT_TOKEN)
    response = requests.get(url, params={"chat_id": CHANNEL_ID, "user_id": telegram_username})
    data = response.json()

    if data.get("ok") and data.get("result", {}).get("status") in ["member", "administrator", "creator"]:
        # Пользователь подписан
        profile_obj = get_object_or_404(profile, user=request.user)
        if not Notification.objects.filter(user=request.user, message="Вы подписались на Telegram и получили 50 очков!").exists():
            profile_obj.points += 100
            profile_obj.save()
            Notification.objects.create(
                user=request.user,
                message="Вы подписались на Telegram и получили 100 очков!"
            )
        return JsonResponse({"success": True, "message": "Вы успешно подписаны на канал! Баллы начислены."})
    else:
        return JsonResponse({"success": False, "message": "Вы не подписаны на канал. Пожалуйста, подпишитесь и попробуйте снова."})


def check_subscription_instagram(request):
    profile_obj = get_object_or_404(profile, user=request.user)

    # Проверяем, начислялись ли уже баллы за Instagram
    if not Notification.objects.filter(user=request.user, message="Вы подписались на Instagram и получили 100 очков!").exists():
        # Здесь должна быть логика проверки подписки через Instagram API
        # Если подписка успешна:
        profile_obj.points += 100
        profile_obj.save()

        Notification.objects.create(
            user=request.user,
            message="Вы подписались на Instagram и получили 100 очков!"
        )
        messages.success(request, "Вы успешно подписались на Instagram! Баллы начислены.")
    else:
        messages.info(request, "Вы уже получили баллы за подписку на Instagram.")

    return redirect('https://www.instagram.com/visions_kz/')  # Ссылка на ваш аккаунт в Instagram



def login_user(request):
    if not request.user.is_staff:  # Только для обычных пользователей
        user = authenticate(request, username='user', password='password')
        if user is not None:
            login(request, user)


# class CustomPaginator:
#     @staticmethod
#     def paginate(object_list: any, per_page=5, page_number=1):
#         paginator_instance = Paginator(object_list=object_list, per_page=per_page)
#         try:
#             page = paginator_instance.page(number=page_number)
#         except PageNotAnInteger:
#             page = paginator_instance.page(number=1)
#         except EmptyPage:
#             page = paginator_instance.page(number=paginator_instance.num_pages)
#         return page

def home_view(request: HttpRequest) -> HttpResponse:  # TODO контроллер функция
    context = {}
    return render(request, 'django_app/home_main.html', context=context)


def home_main(request):
    if request.user.is_authenticated:
        users = profile.objects.all().order_by('-points')
        notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
        notifications.update(is_read=True)
    else:
        users = [] 
        notifications = []

    return render(request, 'django_app/home_main.html', {'users': users, 'notifications': notifications})



def homework(request):
    if request.user.is_authenticated:
        tasks = Task.objects.filter(user=request.user).order_by('is_completed')
    else:
        return redirect('django_app:login')

    return render(request, 'django_app/homework.html', {'tasks': tasks})


def upload_task(request, task_id):
    if request.method == 'POST':
        try:
            task = Task.objects.get(id=task_id, user=request.user)
            uploaded_file = request.FILES['attachment']

            task_dir = os.path.join('C:/Users/Lenova/Documents/visions/static/media/tasks', str(task_id))
            os.makedirs(task_dir, exist_ok=True)

            username = request.user.username
            file_name = f"{username}_{uploaded_file.name}"
            file_path = os.path.join(task_dir, file_name)

            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            task.is_completed = True
            task.save()

            profile = request.user.profile
            profile.points += 300
            total_tasks = 6  # Общее количество заданий
            completed_tasks = Task.objects.filter(user=request.user, is_completed=True).count()

            if completed_tasks == total_tasks and total_tasks > 0:  # Все задания выполнены
                profile.is_eligible_for_testing = True
                print(f"Статус изменён: {profile.is_eligible_for_testing}")  # Отладка
                Notification.objects.create(
                    user=request.user,
                    message="Поздравляем! Вы выполнили все задания и допущены к тестированию!",
                )
                messages.success(request, "Поздравляем! Вы выполнили все задания и допущены к тестированию!")

            profile.save()
            print(f"Сохранённый статус: {profile.is_eligible_for_testing}")

            Notification.objects.create(
                user=request.user,
                message=f"Вы выполнили задание '{task.title}' и получили 300 очков!",
            )

            return redirect('django_app:homework')

        except Task.DoesNotExist:
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


def register(request):
    if request.method == "POST":
        username = request.POST.get("username", "")
        email = request.POST.get("email", "")
        password = request.POST.get("password", "")

        if User.objects.filter(username=username).exists():
            error_message = "Пользователь с таким логином уже существует."
            return render(request, 'django_app/register.html', {'error_message': error_message})

        if User.objects.filter(email=email).exists():
            error_message = "Пользователь с таким email уже существует."
            return render(request, 'django_app/register.html', {'error_message': error_message})

        try:
            validate_password(password)
        except ValidationError as e:
            error_message = "Вы ввели очень легкий пароль"  # Объединяем все сообщения об ошибках в одну строку
            return render(request, 'django_app/register.html', {'error_message': error_message})

        if username and email and password:
            user = User.objects.create_user(username=username, email=email, password=password)
            login(request, user)

            profile = request.user.profile
            profile.points += 100
            profile.save()

            Notification.objects.create(
                user=request.user,
                message=f"Вы зарегистрировались и получили 100 очков! Заполните свой профиль и получите еще 200 очков",
            )
            return redirect(reverse('django_app:home_main', args=()))
        else:
            error_message = "Все поля обязательны для заполнения."
            return render(request, 'django_app/register.html', {'error_message': error_message})
    else:
        return render(request, 'django_app/register.html')


def login_(request):
    if request.method == "POST":
        username = request.POST.get("username", "")
        email = request.POST.get("email", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, email=email, password=password)
        if user:
            login(request, user)
            return redirect(reverse('django_app:home_main', args=()))
        else:
            error_message = "Логин или пароль не верны!"
            return render(request, 'django_app/login.html', {'error_message': error_message})
    return render(request, 'django_app/login.html')

def logout_f(request):
    logout(request)
    return redirect(reverse('django_app:login', args=()))
