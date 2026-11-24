from django.db import migrations, models


def mark_existing_approved(apps, schema_editor):
    # Баллы за уже одобренные задания были начислены раньше — помечаем, чтобы не начислить повторно.
    Task = apps.get_model('django_app', 'Task')
    Task.objects.filter(is_approved=True).update(points_awarded=True)


class Migration(migrations.Migration):

    dependencies = [
        ('django_app', '0012_alter_task_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='points_awarded',
            field=models.BooleanField(default=False, db_default=False, editable=False),
        ),
        migrations.RunPython(mark_existing_approved, migrations.RunPython.noop),
    ]
