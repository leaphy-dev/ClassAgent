# ClassAgent 更新日志

本文件记录项目的重要变更，条目按时间倒序排列，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
基线版本为 `8f4a49e`（合并 PR #1「创建三张表，班级管理模型」）。

---

## [未发布] — 2026-11-15

**阶段定位：课程项目方案 P1「数据底座」第一步 + 登录/账户模块缺陷修复。**

本次变更对应本阶段的独立提交。核心目标是把「课程」补成顶层聚合根，使后续每门课可以独立挂载知识库与 Dify 工作流，并让知识点图谱、角色、教学班之间形成可复用的数据结构。同时在补齐种子数据的过程中，发现并修复了两个会直接阻塞建号的真实缺陷。

一句话概括：**从「只有登录 + 班级管理三张表」推进到「课程顶层 + 知识点图谱 + 可重复生成的演示数据」**。

### 新增

**新应用 `course/`（课程域）**

| 模型 | 说明 |
| --- | --- |
| `Course` | 顶层聚合根。`code` 唯一、名称/简介、`status`（DRAFT / ACTIVE / ARCHIVED）、`created_by`（`PROTECT`）、创建与更新时间 |
| `CourseDifyConfig` | 与课程一对一。保存 `base_url`、`dataset_id`、`workflows`（`qa` / `quiz` / `grading` / `analytics` 四个工作流槽位）、`api_key_env`、`prompt_version`、`is_enabled`。库里**只存环境变量名**，密钥由 `resolve_api_key()` 从部署环境读取；`is_ready` 判断是否具备调用条件 |
| `KnowledgePoint` | 课程内知识点。难度 1–5、教学顺序、`prerequisites` 自关联多对多构成 DAG；`(course, code)` 唯一约束，`clean()` 禁止自环 |

- `course/graph.py`：面向知识点 DAG 的算法工具
  - `topological_order(course)`：Kahn 拓扑排序，复杂度 **O(V + E)**，同时承担**环检测**（发现环抛 `CycleError`）
  - `prerequisite_closure(course, point)`：反向 BFS 求某知识点的全部前置，复杂度 **O(V + E)**
  - 供后续学习路径推荐、智能出题、错题复盘复用
- `course/admin.py`：三张表注册到 Django Admin
- `course/tests.py`：3 个图谱测试（拓扑序遵守前置边、环被检出、前置闭包返回全部祖先）
- `scripts/seed_data.py`：**可重复执行**的种子脚本（`update_or_create` / `get_or_create`），生成
  - 2 门课程（数据结构与算法基础 / 计算机网络，用于验证配置可复用、知识库彼此隔离）
  - 18 个知识点、20 条前置关系，两门课各自一张 DAG
  - 1 名管理员、3 位教师、25 名学生
  - 2 个教学班、6 条任课绑定、44 条选课记录
  - 每门课一份占位 Dify 配置（默认 `is_enabled=False`）
  - 演示密码 `ClassAgent@2026`，可用环境变量 `SEED_PASSWORD` 覆盖（仅首次创建用户时生效）
- `user/tests.py`：2 个用户管理器测试（连续创建多个用户不撞唯一约束、`create_superuser` 自动设为 ADMIN）

### 修复

1. **`is_banned()` 语义反了**（`user/models/user.py`）：原实现返回 `self.is_active`，活跃用户会被误判为「已封禁」。改为 `return not self.is_active`。
2. **`user_id` 允许留空**（`user/models/user.py`）：`blank=True` + `unique=True` 会让空字符串占掉唯一键，后台新增第二个用户即撞 `IntegrityError`。改为 `blank=False`。
3. **重复路由名**（`ClassAgent/urls.py`）：`/` 与 `/dashboard/` 都注册为 `name='home'`，`reverse('home')` / `{% url 'home' %}` 会解析到后注册者。`/dashboard/` 改名为 `name='dashboard'`。
4. **批量建用户撞 `username` 唯一约束**（`user/managers.py`，种子脚本首次运行时暴露）：`AbstractUser.username` 仍是唯一且必填，但 `USERNAME_FIELD` 早已改为 `user_id`，导致所有新建用户的 `username` 落成空串，**第二个用户就报 `UNIQUE constraint failed: user_user.username`**。在 `UserManager.create_user` 中 `setdefault('username', user_id)`，种子脚本也显式填充；`createsuperuser` 这条路径同时修好。
5. **根目录多余的空 `__init__.py`**：会让 `manage.py test course` 被解析成 `ClassAgent.course` 而报 `ImportError`。已删除，测试发现恢复正常。

> 更正此前一次代码审查的结论：`user/admin.py` 的 `add_fieldsets` **本来就包含 `('role', 'user_id')`**，「后台新增表单缺少 user_id」的判断不成立；真实风险只有上面的 `blank=True`。

### 变更

- `classroom/models/classroom.py`：`ClassRoom` 新增到 `Course` 的外键（`PROTECT`、`related_name='classrooms'`）。**过渡期 `null=True, blank=True`**，兼容队友本地已有数据；P2 收口为必填。班级的 `subject` / `term` 仍是原有字符串列，课程归属现在由关系表表达。
- `ClassAgent/settings.py`：`INSTALLED_APPS` 增加 `"course"`。
- `README.md`：从单行标题补全为本地起步说明（正确解释器、迁移 / 种子 / 测试 / 启动命令、演示账号、结构速览、密钥不落库说明）。
- `.gitignore`：排除 `.workbuddy/`（本地工作数据、临时导出）。

### 数据库迁移（**必须随代码一起提交**）

| 文件 | 内容 |
| --- | --- |
| `course/migrations/0001_initial.py` | 新建 `Course` / `CourseDifyConfig` / `KnowledgePoint` |
| `classroom/migrations/0002_classroom_course.py` | `ClassRoom.course` 加字段 |
| `user/migrations/0004_alter_user_user_id.py` | `user_id` 改为 `blank=False` |

队友拉取后按顺序执行（本机 `python` 是 3.13 且未装 Django，**必须显式使用 `C:/Python314/python.exe`**）：

```bash
C:/Python314/python.exe manage.py migrate
C:/Python314/python.exe scripts/seed_data.py
```

### 验证结果

| 检查项 | 结果 |
| --- | --- |
| `manage.py check` | 通过，无告警 |
| `manage.py makemigrations --check --dry-run` | 模型与迁移完全对齐，无待生成迁移 |
| `manage.py test` | **5 个测试全部通过**（图谱 3 + 用户管理器 2） |
| 种子脚本二次执行 | 新增用户 0 人、任课 0 条、选课 0 条，幂等 ✓ |
| 图谱冒烟 | 两门课拓扑排序均无环；未挂课程的教学班 0 个 |
| 登录冒烟 | 学号 `T001` 与邮箱 `t001@classagent.local` 均可登录，错误密码被拒 |
| 行为回归 | `is_banned()` 初始 `False` → 封禁后 `True` → 解封后 `False`；`reverse('home')='/'`、`reverse('dashboard')='/dashboard/'` |
| Dify 配置 | `is_ready=False`（未部署，符合预期） |

演示账号：`ADMIN001`（管理员）、`T001`~`T003`（教师）、`S0001`~`S0025`（学生）；密码 `ClassAgent@2026`。

### 已知遗留 / 下一步

- **P2 三端业务闭环**：管理员端课程配置页 + RBAC + 审计日志优先（直接消费本次建好的三张表），再补教师端、学生端；顺手补 `?next=` 回跳。
- `ClassRoom.course` 过渡期可空，P2 数据收口后改为必填。
- **P3 Dify 接入**：部署后填 `dataset_id` 与四个工作流应用 ID、设置 `DIFY_API_KEY` 环境变量，再把 `is_enabled` 打开。
- **P4 算法与性能实测**：组卷贪心 / 背包、错题复习优先队列、Trie + 编辑距离检索，以及 20 / 200 / 2000 规模下的响应时间与复杂度对比。
- **工程规范欠账（仍未处理）**：`SECRET_KEY` 硬编码在 git 中、`STATIC_ROOT = BASE_DIR` 与 `STATICFILES_DIRS` 重叠、`TIME_ZONE=UTC` / `LANGUAGE_CODE=en-us`、`requirements.txt` 未锁版本（迁移由 Django 6.1.3 生成、本地为 6.1.2）、`DEBUG` / `ALLOWED_HOSTS` 上线前需收口。
- `core/` 仍是首页占位，还没有 `urls.py` 与三端页面。
