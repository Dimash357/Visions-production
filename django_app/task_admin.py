"""Управление заданиями для сотрудников: назначение, редактирование, сроки, архив, удаление."""
import os
import uuid
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST

from .forms import DeadlineShiftForm, TaskCreateForm, TaskEditForm, current_stream_students
from .models import Notification, Task, local_today, profile

GROUP_RE = r'[0-9a-f]{32}'


def _is_staff(user):
    return user.is_staff or user.is_superuser


staff_required = lambda view: login_required(user_passes_test(_is_staff)(view))  # noqa: E731


def _group_tasks(key):
    tasks = Task.objects.filter(group_key=key).select_related('user').order_by('user__username')
    if not tasks.exists():
        raise Http404
    return tasks


def _locked(task):
    """Задание нельзя удалить, если оно уже повлияло на студента: есть ответ или баллы."""
    return bool(task.user_response_file or task.is_approved or task.penalty_applied or task.points_awarded)


def _store_file(uploaded):
    name = get_valid_filename(os.path.basename(uploaded.name))[:100] or 'task'
    return default_storage.save(f'tasks/{name}', uploaded)


def _delete_files_if_unused(names):
    """Общий файл удаляется с диска, только когда на него больше не ссылается ни одно задание."""
    def cleanup():
        for name in {n for n in names if n}:
            if not Task.objects.filter(Q(file=name) | Q(user_response_file=name)).exists():
                default_storage.delete(name)
    transaction.on_commit(cleanup)


# ---------- List / detail ----------

@staff_required
def task_groups(request):
    show_archived = request.GET.get('archived') == '1'
    rows = {}
    for t in (Task.objects.filter(is_archived=show_archived, user__isnull=False)
              .select_related('user').order_by('-created_at', '-deadline', '-id')):
        key = t.group_key or f'legacy-{t.pk}'
        r = rows.setdefault(key, {'key': t.group_key, 'title': t.title, 'deadline': t.deadline,
                                  'students': 0, 'submitted': 0, 'approved': 0, 'pending': 0})
        r['students'] += 1
        r['submitted'] += bool(t.user_response_file or t.is_approved)
        r['approved'] += bool(t.is_approved)
        r['pending'] += t.status == 'pending'
        r['deadline'] = max(r['deadline'], t.extended_deadline or t.deadline)
    return render(request, 'django_app/task_groups.html', {'groups': list(rows.values()), 'show_archived': show_archived})


@staff_required
def task_group(request, key):
    tasks = list(_group_tasks(key))
    first = tasks[0]
    shift_form = DeadlineShiftForm(group_tasks=Task.objects.filter(group_key=key, is_approved=False),
                                   initial={'new_deadline': max(local_today(), first.deadline) + timedelta(days=3)})
    return render(request, 'django_app/task_group.html', {
        'key': key, 'tasks': tasks, 'first': first, 'shift_form': shift_form,
        'archived': all(t.is_archived for t in tasks),
        'can_delete': request.user.is_superuser and not any(_locked(t) for t in tasks),
    })


# ---------- Create / duplicate ----------

@staff_required
def task_create(request):
    source_key = request.GET.get('from', '')
    if request.method == 'POST':
        form = TaskCreateForm(request.POST, request.FILES)
        if form.is_valid():
            return _create_batch(request, form)
    else:
        initial = {'batch': uuid.uuid4().hex, 'deadline': local_today() + timedelta(days=7)}
        student = request.GET.get('student', '')
        if student.isdigit() and current_stream_students().filter(pk=student).exists():
            initial['students'] = [int(student)]
        source = Task.objects.filter(group_key=source_key).first() if len(source_key) == 32 else None
        if source:
            initial.update(title=source.title, description=source.description or '', source=source_key)
        form = TaskCreateForm(initial=initial)
    source_value = form['source'].value() or ''
    source = Task.objects.filter(group_key=source_value).first() if len(source_value) == 32 else None
    return render(request, 'django_app/task_form.html', {
        'form': form, 'mode': 'duplicate' if source else 'create', 'source': source,
    }, status=400 if form.is_bound else 200)


def _create_batch(request, form):
    data = form.cleaned_data
    batch = data['batch']
    if Task.objects.filter(group_key=batch).exists():
        messages.info(request, "Это задание уже назначено (форма была отправлена повторно).")
        return redirect('django_app:task_group', key=batch)

    students = list(data['students'])
    stored_name = data['source_file']
    new_file = None
    if data.get('file'):
        new_file = stored_name = _store_file(data['file'])
    try:
        with transaction.atomic():
            # Блокируем профили выбранных студентов: параллельные назначения не создадут дубли
            profile.objects.filter(user__in=students).update(points=F('points'))
            taken = set(Task.objects.filter(user__in=students, title__iexact=data['title'], is_archived=False)
                        .values_list('user_id', flat=True))
            targets = [s for s in students if s.pk not in taken]
            for student in targets:
                task = Task(user=student, title=data['title'], description=data['description'],
                            deadline=data['deadline'], group_key=batch)
                task.file.name = stored_name
                task.save()  # уведомление «Вам назначено новое задание» создаётся в save()
    except Exception:
        if new_file:
            default_storage.delete(new_file)
        raise
    if new_file and not targets:
        default_storage.delete(new_file)

    if not targets:
        messages.error(request, "У всех выбранных студентов уже есть активное задание с таким названием.")
        return redirect('django_app:task_groups')
    text = f"Задание «{data['title']}» назначено: {len(targets)}."
    if taken:
        text += f" Пропущено {len(taken)} — у них уже есть задание с таким названием."
    messages.success(request, text)
    return redirect('django_app:task_group', key=batch)


# ---------- Edit ----------

@staff_required
def task_edit(request, key):
    tasks = list(_group_tasks(key))
    first = tasks[0]
    initial = {'title': first.title, 'description': first.description or '', 'deadline': first.deadline}
    if request.method == 'POST':
        form = TaskEditForm(request.POST, request.FILES, initial=initial)
        if form.is_valid():
            data = form.cleaned_data
            old_files = {t.file.name for t in tasks}
            new_file = _store_file(data['file']) if data.get('file') else None
            try:
                with transaction.atomic():
                    for task in Task.objects.filter(group_key=key):
                        task.title, task.description = data['title'], data['description']
                        if data['deadline'] != task.deadline:
                            task.deadline = data['deadline']
                            if task.extended_deadline and task.extended_deadline <= data['deadline']:
                                task.extended_deadline = None  # индивидуальное продление устарело
                        if new_file:
                            task.file.name = new_file
                        task.save()
                    if new_file:
                        _delete_files_if_unused(old_files)
            except Exception:
                if new_file:
                    default_storage.delete(new_file)
                raise
            messages.success(request, f"Задание «{data['title']}» обновлено у {len(tasks)} студентов.")
            return redirect('django_app:task_group', key=key)
    else:
        form = TaskEditForm(initial=initial)
    return render(request, 'django_app/task_form.html', {'form': form, 'mode': 'edit', 'first': first, 'key': key},
                  status=400 if form.is_bound else 200)


# ---------- Deadlines / archive / delete ----------

@staff_required
@require_POST
def task_deadline(request, key):
    _group_tasks(key)
    form = DeadlineShiftForm(request.POST, group_tasks=Task.objects.filter(group_key=key, is_approved=False))
    if not form.is_valid():
        for errors in form.errors.values():
            messages.error(request, errors[0])
        return redirect('django_app:task_group', key=key)
    new = form.cleaned_data['new_deadline']
    with transaction.atomic():
        for task in form.cleaned_data['tasks']:
            if new > task.deadline:
                task.extended_deadline = new  # студент увидит «Срок продлён»
            else:
                task.deadline, task.extended_deadline = new, None
            task.save()
            Notification.objects.create(user_id=task.user_id,
                                        message=f"Дедлайн по заданию '{task.title}' перенесён на {new:%d.%m.%Y}.")
    messages.success(request, f"Дедлайн перенесён на {new:%d.%m.%Y} у {len(form.cleaned_data['tasks'])} студентов.")
    return redirect('django_app:task_group', key=key)


@staff_required
@require_POST
def task_archive(request, key):
    _group_tasks(key)
    archive = request.POST.get('action') != 'restore'
    Task.objects.filter(group_key=key).update(is_archived=archive)
    messages.success(request, "Задание перенесено в архив." if archive else "Задание возвращено из архива.")
    return redirect('django_app:task_group', key=key)


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def task_delete(request, key):
    with transaction.atomic():
        tasks = list(Task.objects.select_for_update().filter(group_key=key))
        if not tasks:
            raise Http404
        if any(_locked(t) for t in tasks):
            messages.error(request, "Удалить нельзя: студенты уже сдавали работу или получили баллы. Перенесите задание в архив.")
            return redirect('django_app:task_group', key=key)
        title, files = tasks[0].title, {t.file.name for t in tasks}
        Notification.objects.filter(user_id__in=[t.user_id for t in tasks],
                                    message=f"📚 Вам назначено новое задание: '{title}'.").delete()
        Task.objects.filter(pk__in=[t.pk for t in tasks]).delete()
        _delete_files_if_unused(files)
    messages.success(request, f"Задание «{title}» удалено.")
    return redirect('django_app:task_groups')
