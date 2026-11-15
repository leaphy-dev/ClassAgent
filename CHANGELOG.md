# ClassAgent 更新日志

本文件记录项目的重要变更，按阶段倒序排列，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
基线版本为 `8f4a49e`（合并 PR #1「创建三张表，班级管理模型」）。
**P1 与 P2 两个阶段各自对应一条独立提交记录，条目按阶段倒序排列。**

---

## [未发布 · P2 三端业务闭环] — 2026-11-15

**阶段定位：课程项目方案 P2「三端业务闭环」。**

从「只有数据模型、没有业务页面」推进到 **管理员 / 教师 / 学生三端可登录、可操作、串成一条完整链路**：
管理员建课并配置智能体 → 绑定教师与学生 → 教师录入题目、智能组卷、发布作业 →
学生作答自动判分 → 教师复核简答题 → 学生错题复盘与学情分析 → 全过程留痕审计。

### 新增：数据层

**新应用 `learning/`（7 张表）**

| 模型 | 作用 |
| --- | --- |
| `Question` | 课程题库。单选 / 判断 / 简答三种题型，选项 JSON、参考答案、解析、难度、分值、知识点；`check_answer()` 对客观题自动判分，简答题返回 `None` 交教师复核 |
| `Assignment` | 教学班下的作业，状态 DRAFT / PUBLISHED / CLOSED，截止时间、发布人、发布时间 |
| `AssignmentQuestion` | 作业与题目的有序 through 模型，`(assignment, question)` 唯一 |
| `Submission` | 学生对一次作业的一次提交，`(assignment, student)` 唯一，得分 / 状态 / 复核人 |
| `AnswerRecord` | 逐题作答记录，是学情分析与错题复盘的最小事实单元 |
| `WrongQuestion` | 错题本，累计错误次数、最近错误时间、是否已掌握 |
| `Notification` | 站内通知（作业发布 / 批改完成 / 系统消息） |

**新应用 `audit/`**：`AuditLog` 记录操作人快照、分类、动作、对象、详情、请求方法 / 路径 / IP、结果。
登录登出由 Django 信号捕获，所有已认证写请求由中间件兜底，关键业务动作由视图写中文语义化条目（三者不重复）。

**`learning/algorithms.py`（可独立讲解、可单测的算法层）**

| 功能 | 数据结构 / 算法 | 复杂度 |
| --- | --- | --- |
| 模糊与精确查找 | Trie 前缀索引 + Levenshtein 编辑距离 DP | 建树 O(L)，查询 O(L + m·n) |
| 智能组卷 | 知识点覆盖贪心 + `bisect` 难度分档 | O(n log n) |
| 错题复习优先级 | 最小堆 Top-K + 简化艾宾浩斯遗忘曲线 | O(n log k) |
| 跨班学情合并 | 多路归并（`heapq.merge`） | O(N log k) |
| 班级学情排名 | 多关键字稳定排序 | O(n log n) |
| 知识点掌握度 | 哈希表线性聚合 | O(n) |

`learning/services.py` 把「提交 → 判分 → 错题 → 通知 → 学情」集中成可单测的服务函数。

### 新增：三端页面与权限

- **管理员端 `/manage/`**：工作台、课程列表 / 新建 / 详情、按课程配置 Dify（知识库 ID + 四个工作流槽位 + 环境变量名）、用户与角色（Trie 模糊搜索 / 新增 / 封禁解封）、任课与选课绑定、日志审计、系统状态。
- **教师端 `/teacher/`**：工作台、我的教学班与班级学情排名、知识点治理（拓扑序展示 + 新增时环检测并回滚）、题库录入、作业布置（手动选题 / 智能组卷）、作业详情与逐题正确率、发布通知、简答题批改复核。
- **学生端 `/student/`**：学习中心、我的作业、作答与逐题结果、错题复盘（优先队列 + 标记已掌握）、个人学情（完成率 / 正确率 / 掌握度 / 薄弱点 + 前置知识点推荐）、知识图谱分层浏览、通知中心。
- **公共能力**：`core/permissions.py` 的 `role_required` RBAC（未登录带 `?next=` 跳转，越权 403，超级用户不自动放行）；按角色分流首页；`?next=` 回跳做了开放重定向防护；14 个 `template/panel/` 模板 + `static/css/panel.css` 统一后台视觉；未登录落地页重写。

### 修复

1. **审计写入会把登录拖崩**：`django.test` / 信号里传入的 `HttpRequest()` 的 `method` 是 `None`，直接写库触发 `NOT NULL constraint failed: audit_auditlog.method`。`record()` 现在把 `method` / `path` 统一归一化为 `""`。
2. **知识点掌握度分母错误**：待教师复核的简答题（`is_correct=None`）原本被算进分母，拉低正确率。改为只统计已判分记录。
3. **`Question.check()` 与 Django `Model.check()` 冲突**（`models.E020`），更名为 `check_answer()`。
4. **`AssignmentAdmin.filter_horizontal` 与 through 模型冲突**（`admin.E013`），移除该配置。
5. `mastery_summary` 与 `fuzzy_search` 的单元测试同步校正，避免测试掩盖实现语义。

### 变更

- `ClassAgent/settings.py`：`INSTALLED_APPS` 增加 `learning`、`audit.apps.AuditConfig`；`MIDDLEWARE` 末尾增加审计中间件；新增 `LOGIN_URL` / `LOGIN_REDIRECT_URL`。
- `ClassAgent/urls.py`：引入 `include("core.urls")`；新增 `core/urls.py` 承载 34 条三端路由（路由名全局唯一）。
- `core/views.py` 改为 `core/views/` 包（`home` / `admin_views` / `teacher_views` / `student_views`），新增 `core/forms.py`、`core/presenters.py`、`core/permissions.py`。
- `user/views/login.py`、`template/login.html`：支持 `?next=` 回跳并校验目标主机。
- `template/index.html`：从空白页改为项目落地页。
- `scripts/seed_data.py`：追加题库、作业、作答、错题、通知与系统审计种子，仍可重复执行。
- `README.md`：补三端功能说明与演示路径。

### 数据库迁移（**必须随代码一起提交**）

| 文件 | 内容 |
| --- | --- |
| `learning/migrations/0001_initial.py` | 7 张业务表与 4 组唯一约束 |
| `audit/migrations/0001_initial.py` | 审计日志表与时间 / 分类索引 |

队友拉取后执行（本机 `python` 是 3.13 且未装 Django，**必须显式使用 `C:/Python314/python.exe`**）：

```bash
C:/Python314/python.exe manage.py migrate
C:/Python314/python.exe scripts/seed_data.py
```

### 演示路径（5 分钟走完闭环）

演示账号密码统一为 `ClassAgent@2026`，登录支持学号或邮箱。

1. `ADMIN001` 登录 → `/manage/` 看数据总览 → 「课程配置」编辑 `DSA2026` 的 Dify 占位配置 → 「用户与角色」试模糊搜索与封禁 → 「日志审计」看刚才的动作。
2. `T001` 登录 → `/teacher/` → 「知识点治理」看拓扑序 → 「题库管理」录入一题 → 「作业布置」选「智能组卷」→ 在作业详情点「发布并通知学生」→ 「班级学情」看完成率排名。
3. `S0001`（或 `S0020` 等未提交过的学生）登录 → `/student/` 看到待办 → 作答提交，客观题即时判分 → 「错题复盘」看优先级 → 「个人学情」看掌握度与前置推荐 → 「知识图谱」看分层路径。
4. 回到教师端「作业详情」→ 对含简答题的提交点「查看 / 复核」打分，学生端会收到批改通知。

### 验证结果

| 检查项 | 结果 |
| --- | --- |
| `manage.py check` | 通过，无告警 |
| `manage.py makemigrations --check --dry-run` | 无待生成迁移 |
| `manage.py test` | **24 个测试全部通过**：图谱 3 + 用户管理器 2 + 算法与服务 9 + 权限与端到端闭环 6 + 审计 4 |
| 三端页面冒烟 | 30+ 个 URL 全部 200；未登录 302 带 `?next=/teacher/`；跨角色访问 403 |
| 端到端测试 | 建课 → 配置 → 绑定 → 出题 → 组卷 → 发布 → 作答 → 复核 → 错题 → 审计，全链路自动跑通 |
| 种子脚本二次执行 | 新增用户 / 题目 / 作业 / 提交 / 审计日志全部为 0，幂等 ✓ |
| 演示数据规模 | 14 题、6 份作业、40 份提交、50 条错题、88 条通知 |

### 已知遗留 / 下一步

- **P3 Dify 接入**：目前 `CourseDifyConfig` 仍是占位（`is_ready=False`），智能答疑 / 出题 / 批改 / 学情四条工作流尚未接；密钥只存环境变量名的约定已在数据层落地。
- **P4 算法与性能实测**：需要补 20 / 200 / 2000 规模下的响应时间与 O(n log n) vs O(n²) 对比曲线、检索召回率@K、工作流延迟与 Token 消耗，直接对应报告「结果分析」章。
- **工程规范欠账（仍未处理）**：`SECRET_KEY` 硬编码在 git 中、`STATIC_ROOT = BASE_DIR` 与 `STATICFILES_DIRS` 重叠、`TIME_ZONE=UTC` / `LANGUAGE_CODE=en-us`、`requirements.txt` 未锁版本、`ALLOWED_HOSTS` 为空、`DEBUG=True`。系统状态页已把这些列为待办提示。
- `ClassRoom.course` 仍是可空过渡字段；`core/models.py` 仍是空壳；三端页面为服务端渲染，尚未做前端交互增强。
- 报告层面：本阶段可直接支撑附件二模板的「制作过程」与「功能实现方法、流程、关键代码」两节，调研来源需逐条补齐（Django 文档、Dify 官方文档、教材与 RAG / 知识图谱文献）。

---

## [未发布 · P1 数据底座] — 2026-11-15

**阶段定位：课程项目方案 P1「数据底座」第一步 + 登录/账户模块缺陷修复。**

本次变更对应 P1 阶段的独立提交。核心目标是把「课程」补成顶层聚合根，使后续每门课可以独立挂载知识库与 Dify 工作流，并让知识点图谱、角色、教学班之间形成可复用的数据结构。同时在补齐种子数据的过程中，发现并修复了两个会直接阻塞建号的真实缺陷。

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
