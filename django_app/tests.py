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
    STAFF_NOTIFY_EMAILS=['mentor@example.com'],
    EMAIL_SYNC=True,
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
    @override_settings(SOCIAL_POINTS_AUTO_AWARD=True)
    def test_social_points_once(self):
        self.client.force_login(self.student)
        for _ in range(3):
            r = self.client.get(reverse('django_app:check_subscription_telegram'))
            self.assertEqual(r.url, 'https://t.me/visionskz')
        self.assertEqual(self.points(self.student), 100)

    def test_social_points_need_confirmation_by_default(self):
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
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.upload(task), reverse('django_app:homework'))
        task.refresh_from_db()
        self.assertIsNotNone(task.submitted_at)
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



@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
    MEDIA_ROOT=tempfile.mkdtemp(), EMAIL_SYNC=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STAFF_NOTIFY_EMAILS=['mentor@example.com'], SITE_URL='https://example.com',
)
class FeatureTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.today = timezone.localtime().date()
        self.student = User.objects.create_user('student', 'student@example.com', 'pass-12345')
        self.mentor = User.objects.create_user('mentor', 'mentor@example.com', 'pass-12345', is_staff=True)

    def make_task(self, **kw):
        kw.setdefault('deadline', self.today + datetime.timedelta(days=3))
        task = Task(user=self.student, title=kw.pop('title', 'Backlog'), **kw)
        task.file.save('task.pdf', ContentFile(PDF), save=False)
        task.save()
        return task

    def points(self):
        self.student.profile.refresh_from_db()
        return self.student.profile.points

    # 1. Mentor review
    def submitted_task(self):
        task = self.make_task()
        self.client.force_login(self.student)
        self.client.post(reverse('django_app:upload_task', args=[task.id]),
                         {'attachment': SimpleUploadedFile('a.pdf', PDF)})
        task.refresh_from_db()
        self.assertEqual(task.status, 'pending')
        return task

    def test_review_accept(self):
        task = self.submitted_task()
        self.client.force_login(self.mentor)
        self.assertContains(self.client.get(reverse('django_app:homework')), task.title)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse('django_app:review_task', args=[task.id]), {'action': 'accept', 'comment': 'Отлично'})
        self.assertRedirects(r, reverse('django_app:user_homework_detail', args=[self.student.id]))
        task.refresh_from_db()
        self.assertEqual(task.status, 'completed')
        self.assertIsNotNone(task.reviewed_at)
        self.assertEqual(self.points(), 300)
        self.assertTrue(any('student@example.com' in m.to for m in mail.outbox))
        self.assertFalse(any(m.attachments for m in mail.outbox))

    def test_review_return_requires_comment_and_allows_resubmit(self):
        task = self.submitted_task()
        self.client.force_login(self.mentor)
        self.client.post(reverse('django_app:review_task', args=[task.id]), {'action': 'return', 'comment': ''})
        task.refresh_from_db()
        self.assertEqual(task.status, 'pending')
        self.client.post(reverse('django_app:review_task', args=[task.id]), {'action': 'return', 'comment': 'Добавьте цель'})
        task.refresh_from_db()
        self.assertEqual(task.status, 'rejected')
        self.assertTrue(Notification.objects.filter(user=self.student, message__contains='Добавьте цель').exists())
        self.client.force_login(self.student)
        self.client.post(reverse('django_app:upload_task', args=[task.id]), {'attachment': SimpleUploadedFile('b.pdf', PDF)})
        task.refresh_from_db()
        self.assertEqual(task.status, 'pending')

    def test_review_staff_only(self):
        task = self.submitted_task()
        self.client.force_login(self.student)
        self.client.post(reverse('django_app:review_task', args=[task.id]), {'action': 'accept'})
        task.refresh_from_db()
        self.assertEqual(task.status, 'pending')

    # 2. Reminders / Telegram
    def test_deadline_reminder_once_email_fallback(self):
        from django.core.management import call_command
        due = self.make_task(title='Due', deadline=self.today + datetime.timedelta(days=1))
        self.make_task(title='Later', deadline=self.today + datetime.timedelta(days=5))
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            call_command('send_deadline_reminders', stdout=open('/dev/null', 'w'))
            call_command('send_deadline_reminders', stdout=open('/dev/null', 'w'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Due', mail.outbox[0].body)
        due.refresh_from_db()
        self.assertIsNotNone(due.reminder_sent_at)
        due.deadline = self.today + datetime.timedelta(days=2)
        due.save()
        due.refresh_from_db()
        self.assertIsNone(due.reminder_sent_at)

    @override_settings(TELEGRAM_BOT_TOKEN='test-token', TELEGRAM_BOT_USERNAME='visions_bot')
    def test_telegram_link_and_reminder(self):
        from unittest import mock
        from django.core.management import call_command
        self.client.force_login(self.student)
        r = self.client.post(reverse('django_app:telegram_connect'))
        self.assertTrue(r.url.startswith('https://t.me/visions_bot?start='))
        token = r.url.split('=', 1)[1]
        updates = {'result': [{'update_id': 7, 'message': {'text': f'/start {token}', 'chat': {'id': 555, 'type': 'private'}}}]}
        with mock.patch('django_app.management.commands.telegram_sync.telegram_api', return_value=updates), \
                mock.patch('django_app.management.commands.telegram_sync.send_telegram') as sent:
            call_command('telegram_sync', stdout=open('/dev/null', 'w'))
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.telegram_chat_id, '555')
        self.assertEqual(self.student.profile.telegram_link_token, '')
        sent.assert_called_once()
        self.make_task(title='Due', deadline=self.today)
        with mock.patch('django_app.notify.telegram_api') as api:
            call_command('send_deadline_reminders', stdout=open('/dev/null', 'w'))
        self.assertEqual(api.call_args.kwargs['chat_id'], '555')

    # 3. Rewards & social claims
    def test_redeem_reward_balance_and_rank(self):
        from .models import Reward, RewardRedemption
        reward = Reward.objects.get(cost=3000)
        self.student.profile.points = 3200
        self.student.profile.save()
        self.client.force_login(self.student)
        self.client.post(reverse('django_app:redeem_reward', args=[reward.id]))
        self.client.post(reverse('django_app:redeem_reward', args=[reward.id]))  # второй раз не хватит
        self.assertEqual(RewardRedemption.objects.filter(user=self.student).count(), 1)
        self.assertEqual(self.points(), 3200)  # рейтинг не меняется
        self.assertEqual(self.student.profile.available_points(), 200)
        red = RewardRedemption.objects.get()
        self.client.force_login(self.mentor)
        self.client.post(reverse('django_app:staff_requests'), {'kind': 'redemption', 'id': red.id, 'action': 'cancel'})
        self.assertEqual(self.student.profile.available_points(), 3200)

    def test_redeem_requires_post_and_login(self):
        from .models import Reward
        reward = Reward.objects.first()
        self.assertEqual(self.client.post(reverse('django_app:redeem_reward', args=[reward.id])).status_code, 302)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('django_app:redeem_reward', args=[reward.id])).status_code, 405)

    def test_social_claim_flow(self):
        from .models import SocialClaim
        self.client.force_login(self.student)
        self.client.get(reverse('django_app:check_subscription_instagram'))
        self.client.get(reverse('django_app:check_subscription_instagram'))
        self.assertEqual(SocialClaim.objects.count(), 1)
        self.assertEqual(self.points(), 0)
        claim = SocialClaim.objects.get()
        self.client.post(reverse('django_app:staff_requests'), {'kind': 'claim', 'id': claim.id, 'action': 'approve'})
        self.assertEqual(self.points(), 0)  # студент не может подтвердить сам
        self.client.force_login(self.mentor)
        self.client.post(reverse('django_app:staff_requests'), {'kind': 'claim', 'id': claim.id, 'action': 'approve'})
        self.client.post(reverse('django_app:staff_requests'), {'kind': 'claim', 'id': claim.id, 'action': 'approve'})
        self.assertEqual(self.points(), 100)

    # 4. Analytics
    def test_analytics_staff_only_and_metrics(self):
        from .analytics import cohort_report
        self.make_task(title='Old', deadline=self.today - datetime.timedelta(days=2))
        self.make_task(title='Done', is_approved=True)
        report = cohort_report()
        self.assertEqual(report['current']['tasks'], 2)
        self.assertEqual(report['current']['submission_rate'], 50)
        self.assertEqual(report['current']['overdue_rate'], 50)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('django_app:analytics')).status_code, 302)
        self.client.force_login(self.mentor)
        self.assertContains(self.client.get(reverse('django_app:analytics')), 'Done')
        for name in ['staff_requests', 'rewards', 'homework']:
            self.assertEqual(self.client.get(reverse(f'django_app:{name}')).status_code, 200, name)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, MEDIA_ROOT=tempfile.mkdtemp(),
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    TELEGRAM_BOT_TOKEN='SECRET-BOT-TOKEN', TELEGRAM_BOT_USERNAME='visions_bot', SITE_URL='https://example.com',
)
class FeatureReviewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.student = User.objects.create_user('student', 'student@example.com', 'pass-12345')

    def sync(self, text, chat_type='private'):
        from unittest import mock
        from django.core.management import call_command
        updates = {'result': [{'update_id': 1, 'message': {'text': text, 'chat': {'id': 42, 'type': chat_type}}}]}
        with mock.patch('django_app.management.commands.telegram_sync.telegram_api', return_value=updates), \
                mock.patch('django_app.management.commands.telegram_sync.send_telegram'):
            call_command('telegram_sync', stdout=open('/dev/null', 'w'))
        self.student.profile.refresh_from_db()
        return self.student.profile.telegram_chat_id

    def connect(self):
        self.client.force_login(self.student)
        return self.client.post(reverse('django_app:telegram_connect')).url.split('=', 1)[1]

    def test_telegram_token_rejected_from_group_chat(self):
        token = self.connect()
        self.assertEqual(self.sync(f'/start {token}', chat_type='group'), '')
        self.assertEqual(self.sync(f'/start {token}'), '42')

    def test_telegram_token_expires_and_is_single_use(self):
        token = self.connect()
        profile_qs = self.student.profile.__class__.objects.filter(user=self.student)
        profile_qs.update(telegram_link_expires=timezone.now() - datetime.timedelta(minutes=1))
        self.assertEqual(self.sync(f'/start {token}'), '')
        token = self.connect()
        self.assertEqual(self.sync(f'/start {token}'), '42')
        profile_qs.update(telegram_chat_id='')
        self.assertEqual(self.sync(f'/start {token}'), '')  # повторно тот же токен не работает

    def test_bot_token_not_logged(self):
        from unittest import mock
        import requests as rq
        from .notify import send_telegram
        with mock.patch('django_app.notify.requests.post', side_effect=rq.ConnectionError(
                'Max retries exceeded with url: /botSECRET-BOT-TOKEN/sendMessage')), \
                self.assertLogs('django_app.notify', level='WARNING') as logs:
            self.assertFalse(send_telegram('42', 'hi'))
        self.assertNotIn('SECRET-BOT-TOKEN', '\n'.join(logs.output))

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_cron_reminder_email_sent_synchronously(self):
        from django.core.management import call_command
        task = Task(user=self.student, title='Due', deadline=timezone.localtime().date())
        task.file.save('t.pdf', ContentFile(PDF), save=False)
        task.save()
        mail.outbox.clear()
        call_command('send_deadline_reminders', stdout=open('/dev/null', 'w'))  # без captureOnCommitCallbacks
        self.assertEqual(len(mail.outbox), 1)


TM_MEDIA = tempfile.mkdtemp()


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, MEDIA_ROOT=TM_MEDIA,
)
class TaskManagementTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TM_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        import os
        shutil.rmtree(os.path.join(TM_MEDIA, 'tasks'), ignore_errors=True)
        self.a = User.objects.create_user('a', 'a@example.com', 'x')
        self.b = User.objects.create_user('b', 'b@example.com', 'x')
        self.c = User.objects.create_user('c', 'c@example.com', 'x')
        self.old = User.objects.create_user('old', 'o@example.com', 'x')
        self.old.profile.is_former_user = True
        self.old.profile.save()
        self.mentor = User.objects.create_user('m', 'm@example.com', 'x', is_staff=True)
        self.admin = User.objects.create_superuser('root', 'r@example.com', 'x')
        self.client.force_login(self.mentor)
        self.today = timezone.localtime().date()

    def stored_files(self):
        import os
        path = os.path.join(TM_MEDIA, 'tasks')
        return sorted(os.listdir(path)) if os.path.isdir(path) else []

    def create(self, students, title='Sprint Planning', batch=None, **extra):
        import uuid
        data = {'title': title, 'description': 'Цель спринта', 'batch': batch or uuid.uuid4().hex,
                'deadline': (self.today + datetime.timedelta(days=5)).isoformat(),
                'students': [u.id for u in students], 'file': SimpleUploadedFile('plan.pdf', PDF)}
        data.update(extra)
        data = {k: v for k, v in data.items() if v is not None}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('django_app:task_create'), data)

    def key(self, title='Sprint Planning'):
        return Task.objects.filter(title=title).values_list('group_key', flat=True).first()

    # --- create / duplicates / atomicity ---
    def test_create_for_selected_students_shares_one_file(self):
        r = self.create([self.a, self.b])
        key = self.key()
        self.assertRedirects(r, reverse('django_app:task_group', args=[key]))
        self.assertEqual(set(Task.objects.values_list('user__username', flat=True)), {'a', 'b'})
        self.assertEqual(Task.objects.values('file').distinct().count(), 1)
        self.assertEqual(len(self.stored_files()), 1)
        self.assertEqual(Notification.objects.filter(message__contains='Sprint Planning').count(), 2)

    def test_resubmitted_form_is_idempotent(self):
        import uuid
        batch = uuid.uuid4().hex
        self.create([self.a], batch=batch)
        self.create([self.a, self.b], batch=batch)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(len(self.stored_files()), 1)  # второй файл не остался на диске

    def test_duplicate_title_is_skipped_per_student(self):
        self.create([self.a])
        self.create([self.a, self.b], title='sprint planning')
        self.assertEqual(Task.objects.filter(user=self.a).count(), 1)
        self.assertEqual(Task.objects.filter(user=self.b).count(), 1)
        self.create([self.a], title='Sprint Planning')  # всем уже назначено
        self.assertEqual(Task.objects.count(), 2)

    def test_create_validation_leaves_no_files(self):
        past = (self.today - datetime.timedelta(days=1)).isoformat()
        self.assertEqual(self.create([self.a], deadline=past).status_code, 400)
        self.assertEqual(self.create([self.a], file=SimpleUploadedFile('x.html', b'<script>')).status_code, 400)
        self.assertEqual(self.create([]).status_code, 400)
        self.assertEqual(self.create([self.old]).status_code, 400)  # выпускник не из текущего потока
        self.assertEqual(self.create([self.a], file=None).status_code, 400)
        self.assertFalse(Task.objects.exists())
        self.assertEqual(self.stored_files(), [])

    def test_batch_is_atomic(self):
        from unittest import mock
        original = Task.save
        calls = {'n': 0}

        def flaky(task, *args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 2:
                raise RuntimeError('db failure')
            return original(task, *args, **kwargs)
        with mock.patch.object(Task, 'save', flaky), self.assertRaises(RuntimeError):
            self.create([self.a, self.b, self.c])
        self.assertFalse(Task.objects.exists())
        self.assertEqual(self.stored_files(), [])

    # --- permissions ---
    def test_student_has_no_access(self):
        self.create([self.a])
        key = self.key()
        self.client.force_login(self.a)
        for url in [reverse('django_app:task_groups'), reverse('django_app:task_create'),
                    reverse('django_app:task_group', args=[key]), reverse('django_app:task_edit', args=[key])]:
            self.assertEqual(self.client.get(url).status_code, 302, url)
        for name in ['task_deadline', 'task_archive', 'task_delete']:
            self.client.post(reverse(f'django_app:{name}', args=[key]), {'new_deadline': '2099-01-01', 'tasks': []})
        self.assertEqual(Task.objects.filter(is_archived=False).count(), 1)

    def test_only_superuser_can_delete(self):
        self.create([self.a])
        key = self.key()
        self.client.post(reverse('django_app:task_delete', args=[key]))
        self.assertTrue(Task.objects.exists())
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(reverse('django_app:task_delete', args=[key])),
                                 reverse('django_app:task_groups'))
        self.assertFalse(Task.objects.exists())
        self.assertFalse(Notification.objects.filter(message__contains='Sprint Planning').exists())
        self.assertEqual(self.stored_files(), [])

    def test_delete_refused_after_submission(self):
        self.create([self.a])
        task = Task.objects.get()
        task.user_response_file = 'tasks1/answer.pdf'
        task.is_completed = True
        task.save()
        self.client.force_login(self.admin)
        self.client.post(reverse('django_app:task_delete', args=[task.group_key]))
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    # --- edit / duplicate / shared files ---
    def test_edit_updates_all_copies_and_replaces_file(self):
        self.create([self.a, self.b])
        key, old_file = self.key(), Task.objects.first().file.name
        new_deadline = (self.today + datetime.timedelta(days=10)).isoformat()
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse('django_app:task_edit', args=[key]), {
                'title': 'Sprint Planning v2', 'description': 'Новое', 'deadline': new_deadline,
                'file': SimpleUploadedFile('plan2.pdf', PDF)})
        self.assertRedirects(r, reverse('django_app:task_group', args=[key]))
        self.assertEqual(set(Task.objects.values_list('title', flat=True)), {'Sprint Planning v2'})
        self.assertEqual(Task.objects.values('file').distinct().count(), 1)
        self.assertNotEqual(Task.objects.first().file.name, old_file)
        self.assertEqual(len(self.stored_files()), 1)  # старый файл удалён — на него никто не ссылается

    def test_duplicate_reuses_file_and_keeps_it_on_source_delete(self):
        self.create([self.a])
        src = self.key()
        self.assertContains(self.client.get(reverse('django_app:task_create') + f'?from={src}'), 'Дублирование')
        self.create([self.b], title='Sprint Planning (поток 2)', file=None, source=src)
        self.assertEqual(Task.objects.values('file').distinct().count(), 1)
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('django_app:task_delete', args=[src]))
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(len(self.stored_files()), 1)  # файл нужен копии

    def test_source_key_cannot_point_to_arbitrary_file(self):
        self.assertEqual(self.create([self.a], file=None, source='0' * 32).status_code, 400)
        self.assertEqual(self.create([self.a], file=None, source='../../etc/passwd').status_code, 400)

    # --- deadlines / archive ---
    def test_bulk_deadline_shift_for_subset(self):
        self.create([self.a, self.b])
        key = self.key()
        ta = Task.objects.get(user=self.a)
        later = self.today + datetime.timedelta(days=20)
        self.client.post(reverse('django_app:task_deadline', args=[key]),
                         {'new_deadline': later.isoformat(), 'tasks': [ta.id]})
        ta.refresh_from_db()
        tb = Task.objects.get(user=self.b)
        self.assertEqual((ta.extended_deadline, ta.status), (later, 'deadline_extended'))
        self.assertIsNone(tb.extended_deadline)
        self.assertTrue(Notification.objects.filter(user=self.a, message__contains='перенесён').exists())
        earlier = self.today + datetime.timedelta(days=1)
        self.client.post(reverse('django_app:task_deadline', args=[key]),
                         {'new_deadline': earlier.isoformat(), 'tasks': [tb.id]})
        tb.refresh_from_db()
        self.assertEqual((tb.deadline, tb.extended_deadline), (earlier, None))

    def test_archive_hides_task_and_stops_penalties(self):
        self.create([self.a])
        key = self.key()
        self.client.post(reverse('django_app:task_archive', args=[key]), {'action': 'archive'})
        Task.objects.update(deadline=self.today - datetime.timedelta(days=3))
        student = self.client_class()
        student.force_login(self.a)
        self.assertNotContains(student.get(reverse('django_app:homework')), '<h2>Sprint Planning</h2>', html=False)
        Task.objects.get().save()
        self.a.profile.refresh_from_db()
        self.assertEqual(self.a.profile.points, 0)
        self.assertFalse(Task.objects.get().penalty_applied)
        self.client.force_login(self.mentor)
        self.client.post(reverse('django_app:task_archive', args=[key]), {'action': 'restore'})
        self.assertFalse(Task.objects.get().is_archived)

    def test_new_task_page_is_not_duplicate_and_admin_tasks_get_group(self):
        legacy = Task(user=self.a, title='Из админки', deadline=self.today)
        legacy.file.name = 'tasks/x.pdf'
        legacy.save()
        self.assertEqual(len(legacy.group_key), 32)
        r = self.client.get(reverse('django_app:task_create'))
        self.assertContains(r, 'Новое задание')
        self.assertNotContains(r, 'Дублирование')

    def test_pages_render(self):
        self.create([self.a])
        key = self.key()
        for url in [reverse('django_app:task_groups'), reverse('django_app:task_groups') + '?archived=1',
                    reverse('django_app:task_create') + f'?student={self.a.id}',
                    reverse('django_app:task_group', args=[key]), reverse('django_app:task_edit', args=[key]),
                    reverse('django_app:user_homework_detail', args=[self.a.id])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)


class TimezoneTests(TestCase):
    def test_dates_follow_almaty_not_utc(self):
        from unittest import mock
        from .models import local_today
        # 20:00 UTC 10 января = 01:00 11 января в Алматы
        fake_now = datetime.datetime(2026, 1, 10, 20, 0, tzinfo=datetime.timezone.utc)
        with mock.patch('django.utils.timezone.now', return_value=fake_now):
            self.assertEqual(local_today(), datetime.date(2026, 1, 11))
            user = User.objects.create_user('tz', 'tz@example.com', 'x')
            task = Task(user=user, title='TZ')
            self.assertEqual(task.deadline, datetime.date(2026, 1, 11))
            task.deadline = datetime.date(2026, 1, 10)
            self.assertEqual(task.compute_status(), 'overdue')
            task.deadline = datetime.date(2026, 1, 11)
            self.assertEqual(task.compute_status(), 'process')
