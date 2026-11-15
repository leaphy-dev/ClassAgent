"""算法工具与业务服务层的单元测试（不依赖种子数据）。"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from classroom.models import ClassRoom, Enrollment, Teaching
from course.models import Course, KnowledgePoint
from learning.algorithms import (
    Trie, build_review_queue, difficulty_band, edit_distance, fuzzy_search,
    mastery_summary, merge_sorted_runs, multi_key_rank, review_priority,
    select_questions,
)
from learning.models import Assignment, AssignmentQuestion, Question, Submission, WrongQuestion
from learning.services import grade_submission, notify_classroom, question_stats, review_short_answers
from user.models import User
from user.models.enum import UserRole


class AlgorithmTests(TestCase):
    def test_trie_prefix_and_edit_distance(self):
        trie = Trie().build([("线性表", 1), ("线性结构", 2), ("二叉树", 3)])
        self.assertEqual(trie.prefix_ids("线性"), {1, 2})
        self.assertEqual(trie.prefix_ids("不存在的"), set())
        self.assertEqual(edit_distance("kitten", "sitting"), 3)
        self.assertEqual(edit_distance("abc", "abc"), 0)

    def test_fuzzy_search_prefers_exact_prefix(self):
        items = ["线性结构基础", "线性表与链表", "二叉树", "复杂度分析"]
        text_of = lambda x: x  # noqa: E731
        self.assertEqual(fuzzy_search(items, "线性表", text_of)[0], "线性表与链表")
        self.assertEqual(fuzzy_search(items, "二叉树", text_of)[0], "二叉树")
        self.assertIn("复杂度分析", fuzzy_search(items, "复杂度", text_of))

    def test_difficulty_band_bisect(self):
        self.assertEqual(difficulty_band(1), 1)
        self.assertEqual(difficulty_band(3), 3)
        self.assertEqual(difficulty_band(99), 5)

    def test_greedy_question_selection_covers_points(self):
        pool = [
            {"point": 1, "difficulty": 1},
            {"point": 1, "difficulty": 2},
            {"point": 2, "difficulty": 3},
            {"point": 3, "difficulty": 4},
            {"point": None, "difficulty": 5},
        ]
        chosen = select_questions(
            pool, 3, difficulty_of=lambda q: q["difficulty"],
            point_of=lambda q: q["point"],
        )
        self.assertEqual(len(chosen), 3)
        self.assertEqual(
            len({q["point"] for q in chosen if q["point"] is not None}), 3
        )

    def test_review_queue_is_min_heap_topk(self):
        now = timezone.now()

        class FakeQuestion:
            difficulty = 5

        class FakeWrong:
            def __init__(self, pk, count, hours, mastered=False):
                self.pk = pk
                self.wrong_count = count
                self.last_wrong_at = now - timedelta(hours=hours)
                self.mastered = mastered
                self.question = FakeQuestion()

        wrongs = [FakeWrong(i, i, i * 12) for i in range(1, 8)]
        wrongs.append(FakeWrong(99, 100, 500, mastered=True))
        queue = build_review_queue(wrongs, now, limit=3)
        self.assertEqual(len(queue), 3)
        self.assertTrue(all(p > 0 for p, _ in queue))
        self.assertEqual([p for p, _ in queue], sorted([p for p, _ in queue], reverse=True))
        self.assertEqual(review_priority(wrongs[-1], now), 0.0)

    def test_multi_key_rank_and_merge(self):
        rows = [
            {"name": "B", "completion": 0.5, "score": 80},
            {"name": "A", "completion": 1.0, "score": 70},
            {"name": "C", "completion": 1.0, "score": 90},
        ]
        ranked = multi_key_rank(rows, ["completion", "score", "name"])
        self.assertEqual([r["name"] for r in ranked], ["C", "A", "B"])
        merged = merge_sorted_runs([ranked[:2], ranked[2:]], key="score")
        self.assertEqual([r["name"] for r in merged], ["C", "B", "A"])

    def test_mastery_summary(self):
        class FakePoint:
            name = "栈与队列"

        class FakeQuestion:
            knowledge_point = FakePoint()

        class FakeAnswer:
            def __init__(self, correct):
                self.question = FakeQuestion()
                self.is_correct = correct

        result = mastery_summary([FakeAnswer(True), FakeAnswer(False), FakeAnswer(None)])
        self.assertEqual(result["栈与队列"]["total"], 3)
        self.assertEqual(result["栈与队列"]["rate"], 0.5)


class ServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            user_id="A0001", email="a@x.com", password="pass-12345", role=UserRole.ADMIN
        )
        self.teacher = User.objects.create_user(
            user_id="T0001", email="t@x.com", password="pass-12345", role=UserRole.TEACHER
        )
        self.student = User.objects.create_user(
            user_id="S0001", email="s@x.com", password="pass-12345", role=UserRole.STUDENT
        )
        self.course = Course.objects.create(
            code="TEST", name="测试课程", created_by=self.admin
        )
        self.point = KnowledgePoint.objects.create(
            course=self.course, code="P1", name="知识点一", difficulty=2
        )
        self.classroom = ClassRoom.objects.create(
            course=self.course, serial="TEST-01", subject="测试", term="2026秋",
            created_by=self.admin,
        )
        Teaching.objects.create(classroom=self.classroom, teacher=self.teacher)
        Enrollment.objects.create(classroom=self.classroom, student=self.student)
        self.q1 = Question.objects.create(
            course=self.course, knowledge_point=self.point, qtype=Question.QType.SINGLE,
            title="1+1=?", options=[{"key": "A", "text": "2"}, {"key": "B", "text": "3"}],
            answer="A", difficulty=2, score=5, created_by=self.teacher,
        )
        self.q2 = Question.objects.create(
            course=self.course, knowledge_point=self.point, qtype=Question.QType.SHORT,
            title="简述栈", answer="后进先出", difficulty=3, score=10,
            created_by=self.teacher,
        )
        self.assignment = Assignment.objects.create(
            classroom=self.classroom, title="单元测验", created_by=self.teacher,
            status=Assignment.Status.PUBLISHED,
        )
        AssignmentQuestion.objects.create(assignment=self.assignment, question=self.q1, order=1)
        AssignmentQuestion.objects.create(assignment=self.assignment, question=self.q2, order=2)

    def test_grade_submission_creates_answers_and_wrong_book(self):
        sub = grade_submission(self.assignment, self.student, {
            f"q_{self.q1.pk}": "B", f"q_{self.q2.pk}": "先进先出",
        })
        self.assertEqual(sub.status, Submission.Status.PENDING)  # 含简答题待复核
        self.assertEqual(sub.score, 0)
        self.assertEqual(sub.answers.count(), 2)
        self.assertEqual(WrongQuestion.objects.filter(student=self.student).count(), 2)

        reviewed = review_short_answers(sub, self.teacher, {
            f"a_{sub.answers.get(question=self.q2).pk}": "8",
            f"c_{sub.answers.get(question=self.q2).pk}": "on",
            f"f_{sub.answers.get(question=self.q2).pk}": "要点基本完整",
        })
        self.assertEqual(reviewed.status, Submission.Status.GRADED)
        self.assertEqual(reviewed.score, 8)
        self.assertEqual(reviewed.graded_by, self.teacher)
        self.assertTrue(self.student.notifications.filter(kind="FEEDBACK").exists())

    def test_notify_classroom_and_question_stats(self):
        count = notify_classroom(self.assignment)
        self.assertEqual(count, 1)
        self.assertEqual(self.student.notifications.count(), 1)
        grade_submission(self.assignment, self.student, {
            f"q_{self.q1.pk}": "A", f"q_{self.q2.pk}": "后进先出",
        })
        stats = question_stats(self.assignment)
        self.assertEqual(len(stats), 2)
        self.assertEqual(stats[0]["rate"], 1.0)
