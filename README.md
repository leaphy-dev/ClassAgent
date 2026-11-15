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
- `core/` — 首页占位
- `template/`、`static/` — 页面与样式
- `scripts/seed_data.py` — 可重复执行的种子数据
- `CHANGELOG.md` — 更新日志（各阶段变更、迁移清单与验证结果）

课程 Dify 配置默认 `is_enabled=False`，密钥只存环境变量名（`DIFY_API_KEY`），不落库；部署 Dify 后填入 `dataset_id` 与工作流应用 ID 再启用。
