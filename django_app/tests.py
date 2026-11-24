import datetime
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Notification, Task

TMP_MEDIA = tempfile.mkdtemp()
PDF = b'%PDF-1.4 test'


@override_settings(
    MEDIA_ROOT=TMP_MEDIA,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    TASK_NOTIFY_EMAILS=['mentor@example.com'],
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    ALLOWED_HOSTS=['testserver'],
)
class VisionsTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.today = timezone.localtime().date()
        self.student = User.objects.create_user('student', 'student@example.com', 'pass-12345')
        self.other = User.objects.create_user('other', 'other@example.com', 'pass-12345')
        self.mentor = User.objects.create_user('mentor', 'mentor@example.com', 'pass-12345', is_staff=True)
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'pass-12345')

    def make_task(self, user=None, **kw):
        kw.setdefault('deadline', self.today + datetime.timedelta(days=3))
        task = Task(user=user or self.student, title=kw.pop('title', 'Backlog'), **kw)
        task.file.save('task.pdf', ContentFile(PDF), save=False)
        task.save()
        return task

    def points(self, user):
        user.profile.refresh_from_db()
        return user.profile.points

    # --- pages / auth ---
    def test_public_pages(self):
        for name in ['', 'home', 'login', 'about', 'instructions']:
            self.assertEqual(self.client.get(reverse(f'django_app:{name}')).status_code, 200, name)

    def test_private_pages_require_login(self):
        for name in ['profile', 'profile_update', 'check_subscription_telegram']:
            response = self.client.get(reverse(f'django_app:{name}'))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn('/login/', response.url)

    def test_login_by_username_and_email(self):
        r = self.client.post(reverse('django_app:login'), {'username': 'STUDENT@example.com', 'password': 'pass-12345'})
        self.assertRedirects(r, reverse('django_app:home_main'))
        self.client.post(reverse('django_app:logout'))
        r = self.client.post(reverse('django_app:login'), {'username': 'student', 'password': 'pass-12345'})
        self.assertRedirects(r, reverse('django_app:home_main'))

    def test_bruteforce_lockout(self):
        url = reverse('django_app:login')
        for _ in range(5):
            r = self.client.post(url, {'username': 'student', 'password': 'wrong'})
            self.assertEqual(r.status_code, 200)
        r = self.client.post(url, {'username': 'student', 'password': 'pass-12345'})
        self.assertEqual(r.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.student)
        self.client.get(reverse('django_app:logout'))
        self.assertIn('_auth_user_id', self.client.session)
        self.client.post(reverse('django_app:logout'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_auto_logout_middleware(self):
        self.client.force_login(self.student)
        session = self.client.session
        session['last_activity'] = timezone.now().timestamp() - 999999
        session.save()
        r = self.client.get(reverse('django_app:home_main'))
        self.assertRedirects(r, reverse('django_app:login'))

    def test_all_logged_in_pages_render(self):
        self.make_task()
        self.client.force_login(self.student)
        for name in ['home_main', 'homework', 'profile', 'profile_update', 'about', 'instructions']:
            self.assertEqual(self.client.get(reverse(f'django_app:{name}')).status_code, 200, name)
        self.client.force_login(self.admin)
        for url in [reverse('django_app:homework'), reverse('django_app:admin_panel'),
                    reverse('django_app:user_homework_detail', args=[self.student.id])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    # --- notifications / CSRF / IDOR ---
    def test_mark_as_read_only_own_and_csrf(self):
        n = Notification.objects.create(user=self.other, message='x')
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse('django_app:mark_as_read', args=[n.id])).status_code, 404)
        own = Notification.objects.create(user=self.student, message='y')
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.force_login(self.student)
        self.assertEqual(csrf_client.post(reverse('django_app:mark_as_read', args=[own.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse('django_app:mark_as_read', args=[own.id])).status_code, 200)
        own.refresh_from_db()
        self.assertTrue(own.is_read)

    def test_home_does_not_mark_everything_read(self):
        Notification.objects.create(user=self.student, message='new')
        self.client.force_login(self.student)
        self.client.get(reverse('django_app:home_main'))
        self.assertTrue(Notification.objects.filter(user=self.student, is_read=False).exists())

    def test_approve_task_admin_post_only(self):
        task = self.make_task()
        url = reverse('django_app:approve_task', args=[task.id])
        self.client.force_login(self.student)
        self.client.post(url)
        task.refresh_from_db()
        self.assertFalse(task.is_approved)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        task.refresh_from_db()
        self.assertTrue(task.is_approved)
        self.assertEqual(task.status, 'completed')

    # --- points ---
    def test_social_points_once(self):
        self.client.force_login(self.student)
        for _ in range(3):
            r = self.client.get(reverse('django_app:check_subscription_telegram'))
            self.assertEqual(r.url, 'https://t.me/visionskz')
        self.assertEqual(self.points(self.student), 100)

    @override_settings(SOCIAL_POINTS_AUTO_AWARD=False)
    def test_social_points_can_be_disabled(self):
        self.client.force_login(self.student)
        self.client.get(reverse('django_app:check_subscription_youtube'))
        self.assertEqual(self.points(self.student), 0)

    def test_approval_points_once_even_after_rename(self):
        task = self.make_task(is_approved=True)
        self.assertEqual(self.points(self.student), 300)
        task.title = 'Renamed'
        task.save()
        task.save()
        self.assertEqual(self.points(self.student), 300)

    def test_overdue_penalty_once_and_never_negative(self):
        task = self.make_task(deadline=self.today - datetime.timedelta(days=1))
        self.assertEqual(task.status, 'overdue')
        task.save()
        self.assertEqual(self.points(self.student), 0)
        self.assertEqual(Notification.objects.filter(user=self.student, message__contains='отняли').count(), 1)

    def test_status_logic(self):
        self.assertEqual(self.make_task().status, 'process')
        self.assertEqual(self.make_task(is_completed=True).status, 'pending')
        self.assertEqual(self.make_task(rejection_reason='fix').status, 'rejected')
        self.assertEqual(self.make_task(deadline=self.today - datetime.timedelta(days=2),
                                        extended_deadline=self.today + datetime.timedelta(days=2)).status,
                         'deadline_extended')

    def test_revision_notification_fires_once_per_reason(self):
        task = self.make_task()
        task.rejection_reason = 'Добавьте цель спринта'
        task.save()
        task.save()
        msgs = Notification.objects.filter(user=self.student, message__contains='на доработку')
        self.assertEqual(msgs.count(), 1)

    def test_profile_bonus_once(self):
        self.client.force_login(self.student)
        avatar = SimpleUploadedFile('a.png', _png(), content_type='image/png')
        data = {'description': 'Hi', 'city': 'Almaty', 'image': avatar}
        self.assertEqual(self.client.post(reverse('django_app:profile_update'), data).status_code, 302)
        self.client.post(reverse('django_app:profile_update'), {'description': 'Hi2', 'city': 'Almaty'})
        self.assertEqual(self.points(self.student), 200)

    def test_profile_rejects_non_image(self):
        self.client.force_login(self.student)
        fake = SimpleUploadedFile('a.png', b'<script>alert(1)</script>', content_type='image/png')
        r = self.client.post(reverse('django_app:profile_update'), {'description': 'x', 'city': 'y', 'image': fake})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'errorlist')

    # --- uploads / private files ---
    def upload(self, task, name='answer.pdf', content=PDF):
        return self.client.post(reverse('django_app:upload_task', args=[task.id]),
                                {'attachment': SimpleUploadedFile(name, content)})

    def test_upload_valid_file(self):
        task = self.make_task(title='Sprint/../Review')
        self.client.force_login(self.student)
        self.assertRedirects(self.upload(task), reverse('django_app:homework'))
        task.refresh_from_db()
        self.assertEqual(task.status, 'pending')
        self.assertRegex(task.user_response_file.name, r'^tasks1/[^/]+\.pdf$')
        self.assertNotIn('..', task.user_response_file.name)
        self.assertEqual(len(mail.outbox), 1)

    def test_resubmission_after_rejection_goes_to_review(self):
        task = self.make_task(rejection_reason='fix it')
        self.client.force_login(self.student)
        self.upload(task)
        task.refresh_from_db()
        self.assertEqual(task.status, 'pending')

    def test_upload_rejects_bad_files(self):
        task = self.make_task()
        self.client.force_login(self.student)
        self.upload(task, 'evil.html', b'<script>')
        self.upload(task, 'fake.pdf', b'MZ\x90\x00 not a pdf')
        with self.settings(TASK_UPLOAD_MAX_MB=0):
            self.upload(task, 'big.pdf', PDF)
        task.refresh_from_db()
        self.assertFalse(task.user_response_file)
        self.assertEqual(task.status, 'process')

    def test_upload_requires_owner_and_post(self):
        task = self.make_task()
        self.client.force_login(self.other)
        self.upload(task)
        task.refresh_from_db()
        self.assertFalse(task.user_response_file)
        self.assertEqual(self.client.get(reverse('django_app:upload_task', args=[task.id])).status_code, 405)

    def test_private_files_access(self):
        task = self.make_task()
        self.client.force_login(self.student)
        self.upload(task)
        for kind in ['assignment', 'response']:
            url = reverse('django_app:task_file', args=[task.id, kind])
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertIn('attachment', r['Content-Disposition'])
            r.close()
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.client.force_login(self.mentor)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            r.close()
            self.client.force_login(self.student)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('django_app:task_file', args=[task.id, 'response'])).status_code, 302)

    @override_settings(SERVE_FILES_WITH_DJANGO=True)
    def test_media_task_dirs_not_served_publicly(self):
        from importlib import reload
        from django.urls import clear_url_caches
        import django_settings.urls as root_urls
        reload(root_urls)
        clear_url_caches()
        try:
            task = self.make_task()
            self.assertEqual(self.client.get('/media/' + task.file.name).status_code, 404)
            self.assertEqual(self.client.get('/media/profile_images/../' + task.file.name).status_code, 404)
            self.assertEqual(self.client.get('/media/profile_images/%2e%2e/' + task.file.name).status_code, 404)
        finally:
            clear_url_caches()


def _png():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), 'blue').save(buf, 'PNG')
    return buf.getvalue()


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
    MEDIA_ROOT=tempfile.mkdtemp(),
)
class ProductionReviewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('st', 'st@example.com', 'pass-12345')

    def test_admin_login_rate_limited(self):
        User.objects.create_superuser('root', 'root@example.com', 'pass-12345')
        for _ in range(5):
            self.client.post('/admin/login/', {'username': 'root', 'password': 'bad'})
        r = self.client.post('/admin/login/', {'username': 'root', 'password': 'pass-12345'})
        self.assertEqual(r.status_code, 429)

    def test_admin_login_still_works(self):
        User.objects.create_superuser('root', 'root@example.com', 'pass-12345')
        r = self.client.post('/admin/login/?next=/admin/', {'username': 'root', 'password': 'pass-12345'})
        self.assertEqual(r.status_code, 302)

    def test_award_points_once_helper(self):
        from .views import award_points_once
        self.assertTrue(award_points_once(self.user, 'bonus', 100))
        self.assertFalse(award_points_once(self.user, 'bonus', 100))
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.points, 100)

    def test_stale_instance_does_not_double_penalty(self):
        today = timezone.localtime().date()
        self.user.profile.points = 500
        self.user.profile.save()
        task = Task(user=self.user, title='T', deadline=today + datetime.timedelta(days=1))
        task.file.save('t.pdf', ContentFile(PDF), save=False)
        task.save()
        # две «параллельные» копии одного задания, обе ещё не знают о штрафе
        a, b = Task.objects.get(pk=task.pk), Task.objects.get(pk=task.pk)
        Task.objects.filter(pk=task.pk).update(deadline=today - datetime.timedelta(days=1))
        a.deadline = b.deadline = today - datetime.timedelta(days=1)
        a.save()
        b.save()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.points, 400)

    def test_stale_instance_does_not_double_approval(self):
        task = Task(user=self.user, title='T', deadline=timezone.localtime().date())
        task.file.save('t.pdf', ContentFile(PDF), save=False)
        task.save()
        a, b = Task.objects.get(pk=task.pk), Task.objects.get(pk=task.pk)
        a.is_approved = b.is_approved = True
        a.save()
        b.title = 'Renamed meanwhile'
        b.save()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.points, 300)
