# ClassAgent

智慧教学管理软件系统 / 课程智能体（Django 业务底座 + Dify 智能体编排）。

## 本地起步

项目基于 Django 6.1，本机请显式使用装了 Django 的解释器（PATH 上的 python 是 3.13，未装 Django）：

```bash
C:/Python314/python.exe manage.py migrate
C:/Python314/python.exe scripts/seed_data.py
C:/Python314/python.exe manage.py test
C:/Python314/python.exe manage.py runserver
```

种子脚本可重复执行，生成 2 门课程、18 个知识点（含前置关系 DAG）、1 名管理员、3 位教师、25 名学生，以及教学班 / 任课 / 选课数据。默认演示密码 `ClassAgent@2026`，可用环境变量 `SEED_PASSWORD` 覆盖（仅首次创建用户时生效）。

演示账号：`ADMIN001`（管理员）、`T001`~`T003`（教师）、`S0001`~`S0025`（学生）。登录支持学号或邮箱。

## 结构速览

- `user/` — 自定义用户模型、角色、学号/邮箱双方式认证、登录与登出
- `course/` — 课程（顶层组织单位）、按课程的 Dify 配置、知识点图谱与图算法
- `classroom/` — 教学班、教师任课绑定、学生选课
- `learning/` — 题库、作业、作答、错题、通知、学情服务与算法工具
- `audit/` — 审计日志模型、登录信号与写请求中间件
- `core/` — 三端页面、RBAC、通用表单与路由（`core/urls.py`）
- `template/panel/`、`static/css/panel.css` — 三端统一后台页面与样式
- `scripts/seed_data.py` — 可重复执行的种子数据
- `CHANGELOG.md` — 分阶段更新日志（变更、迁移清单、验证结果与演示路径）

## 三端演示

| 角色 | 入口 | 演示账号 | 主要能力 |
| --- | --- | --- | --- |
| 管理员 | `/manage/` | `ADMIN001` | 课程与 Dify 配置、用户角色、任课选课、审计、系统状态 |
| 教师 | `/teacher/` | `T001`~`T003` | 班级学情、知识点治理、题库、智能组卷、作业发布与复核 |
| 学生 | `/student/` | `S0001`~`S0025` | 学习中心、作答、错题复盘、个人学情、知识图谱 |

闭环顺序：管理员建课并配置 → 绑定教师与学生 → 教师出题 / 组卷 / 发布作业 →
学生作答自动判分 → 教师复核简答题 → 学生错题复盘与学情分析 → 全过程写入审计日志。
完整步骤与验证结果见 `CHANGELOG.md` 的 P2 条目。

课程 Dify 配置默认 `is_enabled=False`，密钥只存环境变量名（`DIFY_API_KEY`），不落库；部署 Dify 后填入 `dataset_id` 与工作流应用 ID 再启用。
