"""Метрики по потокам: текущий поток и выпускники (is_former_user)."""
from datetime import timedelta
from statistics import median

from django.utils import timezone

from .models import SocialClaim, Task, profile


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def _group_metrics(profiles, tasks, today, week_ago):
    students = len(profiles)
    due = [t for t in tasks if t.user_response_file or t.is_approved or (t.extended_deadline or t.deadline) < today]
    submitted = [t for t in tasks if t.user_response_file or t.is_approved]
    approved = [t for t in tasks if t.is_approved]
    overdue = [t for t in tasks if t.penalty_applied]
    review_hours = [
        (t.reviewed_at - t.submitted_at).total_seconds() / 3600
        for t in tasks if t.submitted_at and t.reviewed_at and t.reviewed_at >= t.submitted_at
    ]
    return {
        'students': students,
        'tasks': len(tasks),
        'submission_rate': _pct(len([t for t in due if t in submitted]), len(due)),
        'overdue_rate': _pct(len([t for t in due if t in overdue]), len(due)),
        'approval_rate': _pct(len(approved), len(submitted)),
        'waiting_review': len([t for t in tasks if t.status == 'pending']),
        'on_rework': len([t for t in tasks if t.status == 'rejected']),
        'median_review_hours': round(median(review_hours)) if review_hours else None,
        'active_week': _pct(len([p for p in profiles if p.user.last_login and p.user.last_login >= week_ago]), students),
        'telegram': _pct(len([p for p in profiles if p.telegram_chat_id]), students),
        'profile_complete': _pct(len([p for p in profiles if p.city and p.description
                                      and p.image and p.image.name != 'profile_images/default.jpg']), students),
        'avg_points': round(sum(p.points for p in profiles) / students) if students else None,
    }


def _per_task(tasks, today):
    rows = {}
    for t in tasks:
        r = rows.setdefault(t.title, {'title': t.title, 'assigned': 0, 'submitted': 0, 'approved': 0,
                                      'overdue': 0, 'deadline': t.deadline})
        r['assigned'] += 1
        r['submitted'] += bool(t.user_response_file or t.is_approved)
        r['approved'] += bool(t.is_approved)
        r['overdue'] += bool(t.penalty_applied)
        r['deadline'] = max(r['deadline'], t.deadline)
    for r in rows.values():
        r['submitted_pct'] = _pct(r['submitted'], r['assigned']) or 0
    return sorted(rows.values(), key=lambda r: r['deadline'], reverse=True)


def cohort_report():
    now = timezone.now()
    today, week_ago = timezone.localtime(now).date(), now - timedelta(days=7)
    profiles = list(profile.objects.select_related('user').filter(user__is_staff=False, user__is_superuser=False))
    tasks = list(Task.objects.select_related('user__profile').filter(user__isnull=False,
                                                                     user__is_staff=False, user__is_superuser=False))
    groups = []
    for key, label, former in (('current', 'Текущий поток', False), ('former', 'Выпускники', True)):
        g_profiles = [p for p in profiles if p.is_former_user == former]
        g_tasks = [t for t in tasks if t.user.profile.is_former_user == former]
        groups.append({'key': key, 'label': label, **_group_metrics(g_profiles, g_tasks, today, week_ago)})

    current_tasks = [t for t in tasks if not t.user.profile.is_former_user]
    return {
        'groups': groups,
        'current': groups[0],
        'per_task': _per_task(current_tasks, today),
        'pending_claims': SocialClaim.objects.filter(status=SocialClaim.PENDING).count(),
    }
