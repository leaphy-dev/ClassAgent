"""审计日志：登录/登出信号、写请求兜底中间件与关键业务动作。"""

from django.test import Client, TestCase
from django.urls import reverse

from audit.models import AuditLog, record
from learning.models import Notification
from user.models import User
from user.models.enum import UserRole

PASSWORD = "pass-12345"


class AuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            user_id="A0001", email="a@x.com", password=PASSWORD, role=UserRole.ADMIN
        )

    def test_login_and_logout_are_recorded_by_signals(self):
        client = Client()
        self.assertTrue(client.login(username="A0001", password=PASSWORD))
        self.assertTrue(AuditLog.objects.filter(
            action="用户登录", category=AuditLog.Category.AUTH
        ).exists())
        client.post(reverse("logout"))
        self.assertTrue(AuditLog.objects.filter(action="用户登出").exists())

    def test_record_tolerates_plain_http_request(self):
        """信号里可能拿到手工构造的 HttpRequest（method/path 为 None），不能写崩。"""
        from django.http import HttpRequest

        entry = record(actor=self.user, action="测试", request=HttpRequest())
        self.assertEqual(entry.method, "")
        self.assertEqual(entry.path, "")
        self.assertEqual(entry.actor_label, "A0001 (A0001)")

    def test_middleware_records_write_requests_without_explicit_audit(self):
        client = Client()
        client.login(username="A0001", password=PASSWORD)
        note = Notification.objects.create(
            recipient=self.user, title="测试通知", body="内容"
        )
        response = client.post(reverse("notification_read", args=[note.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AuditLog.objects.filter(
            method="POST", path__contains="/notifications/"
        ).exists())

    def test_audit_page_is_readonly_and_filterable(self):
        record(actor=self.user, action="手工事件", category=AuditLog.Category.SYSTEM)
        client = Client()
        client.login(username="A0001", password=PASSWORD)
        response = client.get(reverse("audit_list"), {"category": "SYSTEM"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "手工事件")
