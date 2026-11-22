

def audience_of(user) -> str:
    """判断当前用户属于哪种视角，返回 "guest" / "admin" / "teacher" / "student"。

    user.is_admin() 这类方法是 user/models/user.py 里定义的，
    核心就是判断 role 字段（外加 is_superuser）。
    """
    if not user.is_authenticated:
        return "guest"
    if user.is_admin:
        return "admin"
    if user.is_teacher:
        return "teacher"
    return "student"

# 这样写不合适，未来可以改成i8n
ROLE_LABEL = {
    "guest": "访客",
    "admin": "管理员",
    "teacher": "教师",
    "student": "学生",
}

# 欢迎页上的三张"能力卡片"，按角色不一样。
# 之所以用字典放在模块顶层，是因为它是静态文案，不依赖数据库，
# 每次请求都重新构造纯属浪费。
CAPABILITIES = {
    "admin": [
        ("教学班配置", "创建教学班，维护编号、科目与学期。"),
        ("成员与角色", "管理教师、学生账号以及角色分配。"),
        ("任课与选课", "绑定任课教师，维护学生选课关系。"),
    ],
    "teacher": [
        ("我的教学班", "查看任教班级、学生名单与班级规模。"),
        ("学生名单", "按教学班查看已选课的学生。"),
        ("课程信息", "核对科目、学期与班级编号。"),
    ],
    "student": [
        ("我的课程", "查看已选教学班与所在学期。"),
        ("授课教师", "查看每门课程的任课教师。"),
        ("个人账号", "核对学号、邮箱与账号状态。"),
    ],
}

WELCOME_LEDE = {
    "admin": "你有系统管理权限，可以维护教学班、成员与全部绑定关系。",
    "teacher": "工作台会汇总你任教的教学班与学生规模，从这里开始今天的工作。",
    "student": "工作台会汇总你已选的教学班与授课教师，从这里开始今天的学习。",
}
