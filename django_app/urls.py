from django.urls import path, re_path
from django_app import views

app_name = 'django_app'
urlpatterns = [
    path('', views.home_view, name=''),
    path('home_main/', views.home_main, name='home_main'),


    path('register/', views.register, name='register'),
    path('login/', views.login_, name='login'),
    path('logout/', views.logout_f, name='logout'),


    path('homework/', views.homework, name='homework'),
    # path('visions/', views.visions, name='visions'),
    path('upload_task/<int:task_id>/', views.upload_task, name='upload_task'),
    path('about/', views.about, name='about'),
    path('check-subscription/telegram/', views.check_subscription_telegram, name='check_subscription_telegram'),
    path('check-subscription/instagram/', views.check_subscription_instagram, name='check_subscription_instagram'),
    path('notifications/read/<int:notification_id>/', views.mark_as_read, name='mark_as_read'),


    path('profile/', views.profile_create, name='profile'),
    path('profile_update/', views.profileupdate, name='profile_update'),

]