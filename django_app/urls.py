from django.urls import path, re_path
from django_app import task_admin, views

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
    path('files/task/<int:task_id>/<str:kind>/', views.task_file, name='task_file'),
    path('review/<int:task_id>/', views.review_task, name='review_task'),
    path('rewards/', views.rewards, name='rewards'),
    path('rewards/<int:reward_id>/redeem/', views.redeem_reward, name='redeem_reward'),
    path('staff/requests/', views.staff_requests, name='staff_requests'),
    path('telegram/connect/', views.telegram_connect, name='telegram_connect'),
    path('telegram/disconnect/', views.telegram_disconnect, name='telegram_disconnect'),
    path('analytics/', views.analytics, name='analytics'),
    path('manage/tasks/', task_admin.task_groups, name='task_groups'),
    path('manage/tasks/new/', task_admin.task_create, name='task_create'),
    re_path(r'^manage/tasks/(?P<key>[0-9a-f]{32})/$', task_admin.task_group, name='task_group'),
    re_path(r'^manage/tasks/(?P<key>[0-9a-f]{32})/edit/$', task_admin.task_edit, name='task_edit'),
    re_path(r'^manage/tasks/(?P<key>[0-9a-f]{32})/deadline/$', task_admin.task_deadline, name='task_deadline'),
    re_path(r'^manage/tasks/(?P<key>[0-9a-f]{32})/archive/$', task_admin.task_archive, name='task_archive'),
    re_path(r'^manage/tasks/(?P<key>[0-9a-f]{32})/delete/$', task_admin.task_delete, name='task_delete'),
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