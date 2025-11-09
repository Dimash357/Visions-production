from django.contrib import admin
from django_app import models
from .models import profile, Notification
from .models import Task


class TodosAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'description',
    )
    list_display_links = (
        'title',
    )
    list_editable = (
        'description',
    )
    list_filter = (
        'title',
        'description',
    )
    search_fields = (
        'title',
        'description',
    )
    fieldsets = (
        ("Основное", {"fields": ('title',)}),
        ("Дополнительное", {"fields": ('description',)}),
    )


admin.site.register(profile)
admin.site.register(Task)
admin.site.register(Notification)



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
