from django.test import TestCase

from course.graph import CycleError, prerequisite_closure, topological_order
from course.models import Course, KnowledgePoint
from user.models import User


class KnowledgeGraphTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            user_id="TSTADM001",
            email="test-admin@classagent.local",
            password="test-pass-12345",
        )
        self.course = Course.objects.create(
            code="TEST-CS101",
            name="测试课程",
            created_by=self.admin,
        )

    def point(self, code, order):
        return KnowledgePoint.objects.create(
            course=self.course,
            code=code,
            name=f"知识点 {code}",
            order=order,
        )

    def test_topological_order_respects_edges(self):
        a, b, c = self.point("A", 1), self.point("B", 2), self.point("C", 3)
        b.prerequisites.add(a)
        c.prerequisites.add(b)
        order = topological_order(self.course)
        self.assertEqual([p.code for p in order], ["A", "B", "C"])

    def test_cycle_is_detected(self):
        a, b, c = self.point("A", 1), self.point("B", 2), self.point("C", 3)
        b.prerequisites.add(a)
        c.prerequisites.add(b)
        a.prerequisites.add(c)
        with self.assertRaises(CycleError):
            topological_order(self.course)

    def test_prerequisite_closure_returns_all_ancestors(self):
        a, b, c, other = (
            self.point("A", 1),
            self.point("B", 2),
            self.point("C", 3),
            self.point("D", 4),
        )
        b.prerequisites.add(a)
        c.prerequisites.add(b)
        closure = prerequisite_closure(self.course, c)
        self.assertEqual([p.code for p in closure], ["A", "B"])
        self.assertNotIn(other, closure)
