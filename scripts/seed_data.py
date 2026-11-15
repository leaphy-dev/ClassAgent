"""项目种子数据：可重复执行，不会重复插入。

用法：
    C:/Python314/python.exe scripts/seed_data.py
    SEED_PASSWORD=xxx C:/Python314/python.exe scripts/seed_data.py

生成 2 门课程（验证「同一套结构复用于多门课程」）、各自的 Dify 占位配置、
知识点 DAG、1 名管理员、3 位教师、25 名学生，以及教学班 / 任课 / 选课关系。
P2 追加：每门课的题库、已发布作业 / 草稿、学生作答、错题本与站内通知，
让三端页面第一次打开就有可分析的真实数据。
Dify 配置默认 is_enabled=False：P3 部署好平台后再填入 dataset_id 与工作流 ID。
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ClassAgent.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from audit.models import AuditLog  # noqa: E402
from classroom.models import ClassRoom, Enrollment, Teaching  # noqa: E402
from core.forms import QuestionForm  # noqa: E402
from course.graph import CycleError, topological_order  # noqa: E402
from course.models import (  # noqa: E402
    WORKFLOW_SLOTS,
    Course,
    CourseDifyConfig,
    KnowledgePoint,
)
from learning.models import (  # noqa: E402
    Assignment,
    AssignmentQuestion,
    Notification,
    Question,
    Submission,
    WrongQuestion,
)
from learning.services import grade_submission, notify_classroom  # noqa: E402
from user.models import User  # noqa: E402
from user.models.enum import UserRole  # noqa: E402

SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "ClassAgent@2026")
TERM = "2026秋"

COURSES = [
    {
        "code": "DSA2026",
        "name": "数据结构与算法基础",
        "description": "线性结构、树、图、查找与排序，配套知识点图谱与智能出题。",
        "class_serial": "DSA2026-01",
        "points": [
            ("K01", "线性结构基础", 1, []),
            ("K02", "线性表与链表", 2, ["K01"]),
            ("K03", "栈与队列", 2, ["K02"]),
            ("K04", "递归与分治", 3, ["K03"]),
            ("K05", "树与二叉树", 3, ["K02"]),
            ("K06", "堆与优先队列", 3, ["K05"]),
            ("K07", "图与遍历", 4, ["K03", "K05"]),
            ("K08", "拓扑排序与最短路径", 4, ["K07"]),
            ("K09", "查找与哈希", 3, ["K02"]),
            ("K10", "排序算法", 4, ["K04", "K06"]),
            ("K11", "动态规划", 5, ["K04", "K08"]),
            ("K12", "复杂度分析", 2, ["K01"]),
        ],
    },
    {
        "code": "NET2026",
        "name": "计算机网络",
        "description": "第二门课程，用于验证课程配置可复用、知识库彼此隔离。",
        "class_serial": "NET2026-01",
        "points": [
            ("N01", "网络分层模型", 1, []),
            ("N02", "数据链路层", 2, ["N01"]),
            ("N03", "IP 与子网划分", 3, ["N01"]),
            ("N04", "路由算法", 4, ["N03"]),
            ("N05", "TCP 可靠传输", 4, ["N02", "N03"]),
            ("N06", "应用层协议", 3, ["N05"]),
        ],
    },
]


def seed_users(admin_id="ADMIN001"):
    """管理员 1 名、教师 3 名、学生 25 名；密码只在首次创建时设置。"""
    people = [
        (admin_id, "系统管理员", "", UserRole.ADMIN, True, True),
    ]
    for i in range(1, 4):
        people.append((f"T{i:03d}", f"教师{i}", "", UserRole.TEACHER, False, False))
    for i in range(1, 26):
        people.append((f"S{i:04d}", f"学生{i:02d}", "", UserRole.STUDENT, False, False))

    created_count = 0
    for uid, first_name, last_name, role, is_staff, is_superuser in people:
        user, created = User.objects.update_or_create(
            user_id=uid,
            defaults={
                "username": uid,  # AbstractUser 的 username 仍唯一必填
                "email": f"{uid.lower()}@classagent.local",
                "first_name": first_name,
                "last_name": last_name,
                "role": role,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
                "is_active": True,
            },
        )
        if created:
            user.set_password(SEED_PASSWORD)
            user.save(update_fields=["password"])
            created_count += 1
    return created_count


def seed_courses(admin):
    courses = []
    for spec in COURSES:
        course, _ = Course.objects.update_or_create(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "description": spec["description"],
                "status": Course.Status.ACTIVE,
                "created_by": admin,
            },
        )
        CourseDifyConfig.objects.update_or_create(
            course=course,
            defaults={
                "base_url": "http://localhost/v1",
                "dataset_id": "",
                "workflows": {slot: "" for slot in WORKFLOW_SLOTS},
                "api_key_env": "DIFY_API_KEY",
                "prompt_version": "v1",
                "is_enabled": False,
            },
        )
        courses.append((course, spec))
    return courses


def seed_knowledge(course, spec):
    points = {}
    for code, name, difficulty, _ in spec["points"]:
        point, _ = KnowledgePoint.objects.update_or_create(
            course=course,
            code=code,
            defaults={
                "name": name,
                "difficulty": difficulty,
                "order": int(code[1:]),
                "description": f"{course.name} · {name}",
            },
        )
        points[code] = point
    for code, _, _, prerequisites in spec["points"]:
        if prerequisites:
            points[code].prerequisites.set(points[pre] for pre in prerequisites)
    return points


def seed_classes(courses, admin, teachers, students):
    teaching_count = 0
    enrollment_count = 0
    for course, spec in courses:
        classroom, _ = ClassRoom.objects.update_or_create(
            serial=spec["class_serial"],
            defaults={
                "course": course,
                "subject": course.name,
                "term": TERM,
                "created_by": admin,
            },
        )
        # 每门课至少 3 位任课教师
        for teacher in teachers[:3]:
            _, created = Teaching.objects.get_or_create(classroom=classroom, teacher=teacher)
            teaching_count += int(created)
        # 每门课 20+ 名学生
        for student in students[:22]:
            _, created = Enrollment.objects.get_or_create(classroom=classroom, student=student)
            enrollment_count += int(created)
    return teaching_count, enrollment_count


# 每门课的演示题库：(知识点编码, 题型, 题干, 选项文本, 参考答案, 难度, 分值, 解析)
QUESTION_SPECS = {
    "DSA2026": [
        ("K01", "SINGLE", "线性结构中元素之间的逻辑关系是？",
         "A. 一对一\nB. 一对多\nC. 多对多\nD. 没有确定关系", "A", 1, 5,
         "线性表的元素排成一个序列，除首尾外每个元素有唯一前驱与后继。"),
        ("K02", "JUDGE", "链表支持 O(1) 的随机访问。", "", "F", 2, 5,
         "链表只能顺序访问，随机访问为 O(n)；数组才支持 O(1) 随机访问。"),
        ("K03", "SINGLE", "栈的元素进出特点是？",
         "A. 先进先出\nB. 后进先出\nC. 任意顺序\nD. 按优先级", "B", 2, 5,
         "栈只在栈顶插入与删除，最后入栈的元素最先出栈。"),
        ("K05", "SINGLE", "二叉树第 i 层最多有多少个结点？",
         "A. 2^i\nB. 2^(i-1)\nC. i\nD. i^2", "B", 3, 5,
         "根为第 1 层时，第 i 层最多 2^(i-1) 个结点。"),
        ("K06", "JUDGE", "二叉堆总是一棵完全二叉树。", "", "T", 3, 5,
         "堆用数组存储，其结构约束正是完全二叉树。"),
        ("K08", "SINGLE", "拓扑排序适用于下面哪类图？",
         "A. 有向无环图\nB. 任意有向图\nC. 无向连通图\nD. 完全图", "A", 4, 5,
         "存在环则无法给出线性次序，Kahn 算法会检测到剩余入度非零的结点。"),
        ("K10", "SINGLE", "下列排序算法平均时间复杂度为 O(n log n) 的是？",
         "A. 冒泡排序\nB. 归并排序\nC. 插入排序\nD. 选择排序", "B", 4, 5,
         "归并排序分治递归，每层合并 O(n)，共 log n 层。"),
        ("K12", "SHORT", "简述时间复杂度的含义，并比较 O(n) 与 O(n²) 的增长差异。", "",
         "要点：描述输入规模 n 增大时运行时间的增长量级；O(n) 线性，O(n²) 平方级，规模翻倍时后者约变为 4 倍。",
         2, 10, "考察渐近分析与大 O 记号，属于主观题，需要教师复核。"),
    ],
    "NET2026": [
        ("N01", "SINGLE", "OSI 参考模型共有几层？",
         "A. 4\nB. 5\nC. 7\nD. 8", "C", 1, 5, "物理、数据链路、网络、传输、会话、表示、应用共 7 层。"),
        ("N02", "JUDGE", "数据链路层的传输单位是比特。", "", "F", 2, 5,
         "数据链路层的协议数据单元是帧，物理层才是比特。"),
        ("N03", "SINGLE", "IPv4 地址由多少位组成？",
         "A. 16\nB. 32\nC. 64\nD. 128", "B", 3, 5, "IPv4 为 32 位，通常写成点分十进制。"),
        ("N04", "JUDGE", "子网划分通过借用主机位来扩展网络位。", "", "T", 4, 5,
         "子网掩码变长，主机位减少，网络位增加。"),
        ("N05", "SINGLE", "TCP 建立连接采用？",
         "A. 一次握手\nB. 二次握手\nC. 三次握手\nD. 四次握手", "C", 4, 5,
         "SYN → SYN+ACK → ACK。"),
        ("N06", "SHORT", "说明 DNS 的作用，并写出一次域名解析的大致流程。", "",
         "要点：把域名映射为 IP；先查本地缓存与 hosts，再向递归服务器查询，必要时迭代查询根 / 顶级 / 权威 DNS。",
         3, 10, "主观题，教师复核后计入得分。"),
    ],
}


def _wrong_answer(question):
    """为演示数据构造一个「答错」的答案。"""
    if question.qtype == Question.QType.JUDGE:
        return "T" if question.answer.strip().upper() == "F" else "F"
    if question.qtype == Question.QType.SINGLE:
        for option in question.options or []:
            if option.get("key") != question.answer.strip().upper():
                return option["key"]
    return "（作答不完整）"


def seed_learning(courses, admin, teachers, students):
    """题库 → 作业 → 学生作答 → 错题本 → 站内通知，构成可演示的业务闭环。"""
    created_questions = created_assignments = created_submissions = 0
    for course, spec in courses:
        points = {p.code: p for p in course.knowledge_points.all()}
        questions = []
        for code, qtype, title, options_text, answer, difficulty, score, analysis in QUESTION_SPECS[course.code]:
            question, created = Question.objects.get_or_create(
                course=course,
                title=title,
                defaults={
                    "knowledge_point": points.get(code),
                    "qtype": qtype,
                    "options": QuestionForm.parse_options(options_text),
                    "answer": answer,
                    "analysis": analysis,
                    "difficulty": difficulty,
                    "score": score,
                    "created_by": teachers[0],
                },
            )
            questions.append(question)
            created_questions += int(created)

        classroom = ClassRoom.objects.get(serial=spec["class_serial"])
        plans = [
            ("阶段测验 · 基础概念", questions[:5], 12, True),
            ("随堂练习 · 进阶应用", questions[5:], 8, True),
            ("期末复习卷（草稿）", questions[:4], 0, False),
        ]
        enrolled = list(
            User.objects.filter(enrollments__classroom=classroom).order_by("user_id")
        )
        for title, chosen, submit_count, publish in plans:
            assignment, created = Assignment.objects.get_or_create(
                classroom=classroom,
                title=title,
                defaults={
                    "description": f"{course.name} 演示作业，用于验证作业作答与班级学情分析。",
                    "status": Assignment.Status.DRAFT,
                    "created_by": teachers[0],
                    "due_at": timezone.now() + timedelta(days=14),
                },
            )
            if created:
                created_assignments += 1
                for order, question in enumerate(chosen, 1):
                    AssignmentQuestion.objects.create(
                        assignment=assignment, question=question, order=order
                    )
                if publish:
                    assignment.publish()
                    notify_classroom(assignment)
            else:
                # 保证题目关联存在（老数据可能只有作业没有题）
                for order, question in enumerate(chosen, 1):
                    AssignmentQuestion.objects.get_or_create(
                        assignment=assignment, question=question, defaults={"order": order}
                    )

            for idx, student in enumerate(enrolled[:submit_count]):
                if Submission.objects.filter(assignment=assignment, student=student).exists():
                    continue
                answers = {}
                for j, question in enumerate(chosen):
                    correct = (idx + j) % 4 != 0
                    answers[f"q_{question.pk}"] = (
                        question.answer if correct else _wrong_answer(question)
                    )
                grade_submission(assignment, student, answers)
                created_submissions += 1
    return created_questions, created_assignments, created_submissions


def seed_audit():
    """首次运行时补两条系统审计记录，让日志页不是空的。"""
    if AuditLog.objects.exists():
        return 0
    AuditLog.objects.create(
        actor_label="系统", category=AuditLog.Category.SYSTEM,
        action="初始化演示数据", target="seed_data.py",
        detail="课程、知识点图谱、成员、题库与作业演示数据已生成",
    )
    AuditLog.objects.create(
        actor_label="系统", category=AuditLog.Category.SYSTEM,
        action="系统状态检查", target="db.sqlite3",
        detail="迁移已执行，数据库可读写",
    )
    return 2


def verify(courses):
    """检查图谱无环，并打印可写进报告的数据规模。"""
    print("\n--- 知识点图谱（拓扑序）---")
    for course, _ in courses:
        try:
            order = topological_order(course)
        except CycleError as exc:
            raise SystemExit(f"[失败] {course.code}: {exc}") from exc
        print(f"{course.code}: {len(order)} 个知识点，无环；顺序 "
              f"{' → '.join(p.code for p in order[:6])} ...")

    print("\n--- 数据规模 ---")
    print(f"课程 {Course.objects.count()} 门 / 教学班 {ClassRoom.objects.count()} 个")
    print(f"知识点 {KnowledgePoint.objects.count()} 个 / 前置关系 "
          f"{sum(p.prerequisites.count() for p in KnowledgePoint.objects.all())} 条")
    for role, label in UserRole.choices:
        print(f"  {label}({role}): {User.objects.filter(role=role).count()} 人")
    print(f"任课绑定 {Teaching.objects.count()} 条 / 选课记录 {Enrollment.objects.count()} 条")
    print(f"Dify 配置 {CourseDifyConfig.objects.count()} 份（默认未启用）")
    print("--- 业务闭环数据 ---")
    print(f"题目 {Question.objects.count()} 道 / 作业 {Assignment.objects.count()} 份")
    print(f"提交 {Submission.objects.count()} 份 / 通知 {Notification.objects.count()} 条")
    print(f"错题 {WrongQuestion.objects.count()} 条 / 审计日志 {AuditLog.objects.count()} 条")


def main():
    with transaction.atomic():
        created = seed_users()
        admin = User.objects.get(user_id="ADMIN001")
        teachers = list(User.objects.filter(role=UserRole.TEACHER).order_by("user_id"))
        students = list(User.objects.filter(role=UserRole.STUDENT).order_by("user_id"))
        courses = seed_courses(admin)
        for course, spec in courses:
            seed_knowledge(course, spec)
        teaching, enrollment = seed_classes(courses, admin, teachers, students)
        new_questions, new_assignments, new_submissions = seed_learning(
            courses, admin, teachers, students
        )
        new_logs = seed_audit()
        verify(courses)
    print(f"\n新增用户 {created} 人、任课 {teaching} 条、选课 {enrollment} 条")
    print(f"新增题目 {new_questions} 道、作业 {new_assignments} 份、"
          f"提交 {new_submissions} 份、审计日志 {new_logs} 条")
    print(f"演示账号密码（仅首次创建时生效）：{SEED_PASSWORD}")
    print("提示：Dify 配置仍是占位，P3 部署后填入 dataset_id 与工作流 ID 再启用。")


if __name__ == "__main__":
    main()
