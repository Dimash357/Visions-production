from django.contrib import admin
from django import forms
from django.contrib.auth.models import User
from .models import profile, Notification, Reward, RewardRedemption, SocialClaim, Task


class TaskAdminForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(profile__is_former_user=False)

class NotificationAdminForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(profile__is_former_user=False)

class TaskAdmin(admin.ModelAdmin):
    form = TaskAdminForm
    list_display = ('title', 'user', 'status', 'deadline')
    list_filter = ('status', 'user__profile__is_former_user')
    search_fields = ('title', 'user__username')

class NotificationAdmin(admin.ModelAdmin):
    form = NotificationAdminForm
    list_display = ('user', 'message', 'created_at', 'is_former_user_status')
    list_filter = ('user__profile__is_former_user',)
    ordering = ('user', '-created_at')
    search_fields = ('user__username', 'message')

    def is_former_user_status(self, obj):
        return obj.user.profile.is_former_user
    is_former_user_status.short_description = 'Former User'
    is_former_user_status.boolean = True

admin.site.register(profile)
admin.site.register(Task, TaskAdmin)
admin.site.register(Notification, NotificationAdmin)


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ('title', 'cost', 'is_active', 'sort_order')
    list_editable = ('cost', 'is_active', 'sort_order')


@admin.register(RewardRedemption)
class RewardRedemptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'reward', 'cost', 'status', 'created_at', 'handled_by')
    list_filter = ('status', 'reward')
    search_fields = ('user__username',)
    readonly_fields = ('user', 'reward', 'cost', 'created_at')


@admin.register(SocialClaim)
class SocialClaimAdmin(admin.ModelAdmin):
    list_display = ('user', 'network', 'status', 'created_at', 'reviewed_by')
    list_filter = ('status', 'network')
    search_fields = ('user__username',)



# class LogAdmin(admin.ModelAdmin):
#     list_display = (
#         'user',
#         'method',
#         'status',
#         'url',
#         'description',
#         'level',
#         'datetime',
#     )
#     list_display_links = (
#         'user',
#         'method',
#         'status',
#         'url',
#     )
#     list_editable = (
#         'level',
#     )
#     list_filter = (
#         'user',
#         'method',
#         'status',
#         'url',
#         'description',
#         'datetime',
#         'level',
#     )
#     fieldsets = (
#         ('Main', {'fields': (
#             'user',
#             'method',
#             'status',
#             'url',
#             'description',
#             'datetime',
#             'level',
#         )}),
#     )
#     search_fields = [
#         'user',
#         'method',
#         'status',
#         'url',
#         'description',
#         'datetime',
#         'level',
#     ]
#
#
# admin.site.register(models.Logging, LogAdmin)
