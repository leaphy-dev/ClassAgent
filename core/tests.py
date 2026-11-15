"""三端权限、页面可达性与「管理员 → 教师 → 学生」端到端业务闭环。"""

from django.test import Client, TestCase
from django.urls import reverse

from audit.models import AuditLog
from classroom.models import ClassRoom, Enrollment, Teaching
from course.models import WORKFLOW_SLOTS, Course, CourseDifyConfig, KnowledgePoint
from learning.models import (
    Assignment,
    Notification,
    Question,
    Submission,
    WrongQuestion,
)
from user.models import User
from user.models.enum import UserRole

PASSWORD = "pass-12345"


class FixtureMixin:
    def build_fixture(self):
        self.admin = User.objects.create_user(
            user_id="A0001", email="a@x.com", password=PASSWORD, role=UserRole.ADMIN
        )
        self.teacher = User.objects.create_user(
            user_id="T0001", email="t@x.com", password=PASSWORD, role=UserRole.TEACHER
        )
        self.student = User.objects.create_user(
            user_id="S0001", email="s@x.com", password=PASSWORD, role=UserRole.STUDENT
        )
        self.course = Course.objects.create(code="DSA", name="数据结构", created_by=self.admin)
        CourseDifyConfig.objects.create(course=self.course)
        self.point = KnowledgePoint.objects.create(
            course=self.course, code="K1", name="线性结构", difficulty=1
        )
        self.classroom = ClassRoom.objects.create(
            course=self.course, serial="DSA-01", subject="数据结构", term="2026秋",
            created_by=self.admin,
        )
        Teaching.objects.create(classroom=self.classroom, teacher=self.teacher)
        Enrollment.objects.create(classroom=self.classroom, student=self.student)
        for i in range(1, 4):
            Question.objects.create(
                course=self.course, knowledge_point=self.point,
                qtype=Question.QType.SINGLE, title=f"单选题 {i}",
                options=[{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}],
                answer="A", difficulty=i, score=5, created_by=self.teacher,
            )
        Question.objects.create(
            course=self.course, knowledge_point=self.point,
            qtype=Question.QType.SHORT, title="简述题", answer="参考要点",
            difficulty=3, score=10, created_by=self.teacher,
        )

    def login_as(self, user):
        client = Client()
        self.assertTrue(client.login(username=user.user_id, password=PASSWORD))
        return client


class AccessControlTests(FixtureMixin, TestCase):
    def setUp(self):
        self.build_fixture()

    def test_anonymous_redirect_carries_next(self):
        response = Client().get(reverse("teacher_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/teacher/", response["Location"])

    def test_landing_page_for_anonymous(self):
        self.assertEqual(Client().get("/").status_code, 200)

    def test_wrong_role_is_forbidden(self):
        self.assertEqual(
            self.login_as(self.student).get(reverse("manage_dashboard")).status_code, 403
        )
        self.assertEqual(
            self.login_as(self.admin).get(reverse("teacher_dashboard")).status_code, 403
        )
        self.assertEqual(
            self.login_as(self.teacher).get(reverse("student_dashboard")).status_code, 403
        )

    def test_login_honours_safe_next_and_blocks_open_redirect(self):
        client = Client()
        response = client.post("/login/?next=/student/", {
            "username": "S0001", "password": PASSWORD, "next": "/student/",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/student/")

        evil = Client().post("/login/", {
            "username": "T0001", "password": PASSWORD, "next": "https://evil.example/",
        })
        self.assertEqual(evil["Location"], "/")

    def test_three_role_landings_are_reachable(self):
        for client, name in [
            (self.login_as(self.admin), "manage_dashboard"),
            (self.login_as(self.teacher), "teacher_dashboard"),
            (self.login_as(self.student), "student_dashboard"),
        ]:
            self.assertEqual(client.get(reverse(name)).status_code, 200)


class EndToEndTests(FixtureMixin, TestCase):
    """一条完整链路：建课 → 配置 → 绑定 → 出题 → 布置 → 发布 → 作答 → 复核 → 复盘。"""

    def setUp(self):
        self.build_fixture()
        self.extra_student = User.objects.create_user(
            user_id="S0002", email="s2@x.com", password=PASSWORD, role=UserRole.STUDENT
        )

    def test_full_loop(self):
        admin = self.login_as(self.admin)

        # 1. 管理员新建课程，自动生成占位 Dify 配置
        response = admin.post(reverse("course_form"), {
            "code": "NET", "name": "计算机网络", "description": "第二门课程",
            "status": Course.Status.ACTIVE,
        })
        self.assertEqual(response.status_code, 302)
        new_course = Course.objects.get(code="NET")
        self.assertTrue(CourseDifyConfig.objects.filter(course=new_course).exists())

        # 2. 按课程配置知识库与工作流槽位
        config_url = reverse("course_config", args=[self.course.pk])
        payload = {
            "base_url": "http://localhost/v1", "dataset_id": "ds-001",
            "api_key_env": "DIFY_API_KEY", "prompt_version": "v2",
            "is_enabled": "on",
            **{f"wf_{slot}": f"app-{slot}" for slot in WORKFLOW_SLOTS},
        }
        self.assertEqual(admin.post(config_url, payload).status_code, 302)
        config = self.course.dify_config
        config.refresh_from_db()
        self.assertEqual(config.workflows["qa"], "app-qa")
        self.assertEqual(config.dataset_id, "ds-001")

        # 3. 添加一名选课学生
        self.assertEqual(admin.post(reverse("bindings"), {
            "action": "add_student", "classroom": self.classroom.pk,
            "student": self.extra_student.pk,
        }).status_code, 302)
        self.assertTrue(Enrollment.objects.filter(
            classroom=self.classroom, student=self.extra_student
        ).exists())

        # 4. 教师录入题目
        teacher = self.login_as(self.teacher)
        self.assertEqual(teacher.post(reverse("question_form"), {
            "course": self.course.pk, "knowledge_point": self.point.pk,
            "qtype": Question.QType.SINGLE, "title": "新增题目",
            "options_text": "A. 甲\nB. 乙", "answer": "A", "analysis": "解析",
            "difficulty": 2, "score": 5,
        }).status_code, 302)
        self.assertTrue(Question.objects.filter(title="新增题目").exists())

        # 5. 智能组卷布置作业
        self.assertEqual(teacher.post(reverse("assignment_form"), {
            "classroom": self.classroom.pk, "title": "阶段测验",
            "description": "端到端测试", "due_at": "",
            "mode": "auto", "auto_count": "5",
        }).status_code, 302)
        assignment = Assignment.objects.get(title="阶段测验")
        self.assertEqual(assignment.questions.count(), 5)

        # 6. 发布并通知全班
        self.assertEqual(teacher.post(
            reverse("assignment_publish", args=[assignment.pk]), {}
        ).status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, Assignment.Status.PUBLISHED)
        self.assertEqual(
            Notification.objects.filter(kind=Notification.Kind.ASSIGNMENT).count(), 2
        )

        # 7. 学生作答（客观题给正确答案，简答题留待复核）
        student = self.login_as(self.student)
        answers = {}
        for item in assignment.items.all():
            question = item.question
            answers[f"q_{question.pk}"] = (
                "A" if question.qtype == Question.QType.SINGLE else "我的回答"
            )
        self.assertEqual(student.post(
            reverse("answer_view", args=[assignment.pk]), answers
        ).status_code, 302)
        submission = Submission.objects.get(assignment=assignment, student=self.student)
        self.assertEqual(submission.answers.count(), 5)
        self.assertTrue(WrongQuestion.objects.filter(student=self.student).exists()
                        or submission.status == Submission.Status.GRADED)

        # 8. 教师复核简答题
        short = submission.answers.filter(question__qtype=Question.QType.SHORT).first()
        self.assertIsNotNone(short, "智能组卷应覆盖到简答题")
        self.assertEqual(teacher.post(
            reverse("grading_detail", args=[submission.pk]),
            {f"a_{short.pk}": "8", f"c_{short.pk}": "on", f"f_{short.pk}": "不错"},
        ).status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.GRADED)
        self.assertEqual(submission.score, 8 + 20)  # 四道客观题各 5 分 + 简答题 8 分

        # 9. 学生标记错题已掌握
        wrong = WrongQuestion.objects.filter(student=self.student).first()
        if wrong:
            self.assertEqual(student.post(
                reverse("wrong_master", args=[wrong.pk]), {}
            ).status_code, 302)
            wrong.refresh_from_db()
            self.assertTrue(wrong.mastered)

        # 10. 关键动作全部留痕
        actions = set(AuditLog.objects.values_list("action", flat=True))
        for expected in ["新建课程", "修改课程智能体配置", "添加选课学生",
                         "录入题目", "布置作业", "发布作业", "提交作业"]:
            self.assertIn(expected, actions)

        # 11. 三端列表页在闭环跑完后仍可访问
        self.assertEqual(admin.get(reverse("audit_list")).status_code, 200)
        self.assertEqual(teacher.get(reverse("class_detail", args=[self.classroom.pk])).status_code, 200)
        self.assertEqual(student.get(reverse("student_analytics")).status_code, 200)
        self.assertEqual(student.get(reverse("graph_view")).status_code, 200)
