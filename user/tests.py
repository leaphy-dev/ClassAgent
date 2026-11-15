from django.test import TestCase

from .models import User


class UserManagerTests(TestCase):
    def test_multiple_users_can_be_created(self):
        """USERNAME_FIELD 改成 user_id 后，username 仍需自动填充，否则空串会撞唯一约束。"""
        first = User.objects.create_user(
            user_id="U0001", email="u1@example.com", password="test-pass-12345"
        )
        second = User.objects.create_user(
            user_id="U0002", email="u2@example.com", password="test-pass-12345"
        )
        self.assertEqual(first.username, "U0001")
        self.assertEqual(second.username, "U0002")
        self.assertEqual(User.objects.count(), 2)

    def test_create_superuser_sets_admin_role(self):
        admin = User.objects.create_superuser(
            user_id="U9999", email="admin@example.com", password="test-pass-12345"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_admin())
