from django.urls import path, re_path
from django_app import views

app_name = 'django_app'
urlpatterns = [
    path('', views.scrum_welcome, name=''),
    path('home_main/', views.home_main, name='home_main'),
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('approve-task/<int:task_id>/', views.approve_task, name='approve_task'),


    # path('register/', views.register, name='register'),
    path('login/', views.login_, name='login'),
    path('logout/', views.logout_f, name='logout'),


    path('homework/', views.homework, name='homework'),
    path('homework/<int:user_id>/', views.user_homework_detail, name='user_homework_detail'),
    path('home/', views.home_view, name='home'),
    path('upload_task/<int:task_id>/', views.upload_task, name='upload_task'),
    path('about/', views.about, name='about'),
    path('check-subscription/telegram/', views.check_subscription_telegram, name='check_subscription_telegram'),
    path('check-subscription/linkedn/', views.check_subscription_linkedn, name='check_subscription_linkedn'),
    path('check-subscription/youtube/', views.check_subscription_youtube, name='check_subscription_youtube'),
    path('check-subscription/instagram/', views.check_subscription_instagram, name='check_subscription_instagram'),
    path('check-subscription/facebook/', views.check_subscription_facebook, name='check_subscription_facebook'),
    path('notifications/read/<int:notification_id>/', views.mark_as_read, name='mark_as_read'),
    path('instructions/', views.instructions, name='instructions'),


    path('profile/', views.profile_create, name='profile'),
    path('profile_update/', views.profileupdate, name='profile_update'),

]