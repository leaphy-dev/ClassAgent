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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ClassAgent.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from classroom.models import ClassRoom, Enrollment, Teaching  # noqa: E402
from course.graph import CycleError, topological_order  # noqa: E402
from course.models import (  # noqa: E402
    WORKFLOW_SLOTS,
    Course,
    CourseDifyConfig,
    KnowledgePoint,
)
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
        verify(courses)
    print(f"\n新增用户 {created} 人、任课 {teaching} 条、选课 {enrollment} 条")
    print(f"演示账号密码（仅首次创建时生效）：{SEED_PASSWORD}")
    print("提示：Dify 配置仍是占位，P3 部署后填入 dataset_id 与工作流 ID 再启用。")


if __name__ == "__main__":
    main()
