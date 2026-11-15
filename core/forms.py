"""三端业务表单。options 等 JSON 字段用可读的文本输入，保存时再解析。"""

from django import forms

from classroom.models import ClassRoom
from course.models import WORKFLOW_SLOTS, Course, KnowledgePoint
from learning.models import Assignment, Question
from user.models import User
from user.models.enum import UserRole


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ("code", "name", "description", "status")
        labels = {"code": "课程代码", "name": "课程名称", "description": "课程简介", "status": "状态"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class DifyConfigForm(forms.Form):
    """四个工作流槽位展开成独立字段，避免让用户直接编辑 JSON。"""
    base_url = forms.CharField(label="Dify API 地址", max_length=255)
    dataset_id = forms.CharField(label="知识库 ID", max_length=128, required=False)
    api_key_env = forms.CharField(label="API Key 环境变量名", max_length=64)
    prompt_version = forms.CharField(label="提示词版本", max_length=32)
    is_enabled = forms.BooleanField(label="启用该课程的智能体", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for slot in WORKFLOW_SLOTS:
            label = {"qa": "智能答疑", "quiz": "智能出题", "grading": "批改归因", "analytics": "学情摘要"}[slot]
            self.fields[f"wf_{slot}"] = forms.CharField(label=f"{label} 应用 ID", max_length=128, required=False)

    def workflows_dict(self) -> dict:
        return {slot: self.cleaned_data.get(f"wf_{slot}", "").strip() for slot in WORKFLOW_SLOTS}


class UserCreateForm(forms.Form):
    user_id = forms.CharField(label="账号（学号 / 工号）", max_length=10)
    email = forms.EmailField(label="邮箱")
    first_name = forms.CharField(label="姓名", max_length=64, required=False)
    role = forms.ChoiceField(label="角色", choices=[
        (UserRole.STUDENT, "学生"), (UserRole.TEACHER, "教师"), (UserRole.ADMIN, "管理员"),
    ])
    password = forms.CharField(label="初始密码", widget=forms.PasswordInput, min_length=8)

    def clean_user_id(self):
        uid = self.cleaned_data["user_id"].strip()
        if User.objects.filter(user_id=uid).exists():
            raise forms.ValidationError("该账号已存在。")
        return uid


class KnowledgePointForm(forms.Form):
    course = forms.ModelChoiceField(label="所属课程", queryset=Course.objects.all())
    code = forms.CharField(label="知识点编码", max_length=32)
    name = forms.CharField(label="名称", max_length=128)
    description = forms.CharField(label="说明", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    difficulty = forms.TypedChoiceField(
        label="难度", choices=KnowledgePoint.Difficulty.choices, coerce=int
    )
    order = forms.IntegerField(label="教学顺序", initial=0, min_value=0)
    prerequisites = forms.ModelMultipleChoiceField(
        label="前置知识点", queryset=KnowledgePoint.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, courses=None, **kwargs):
        super().__init__(*args, **kwargs)
        if courses is not None:
            self.fields["course"].queryset = courses
        course = None
        if self.is_bound:
            course_id = self.data.get("course")
            if course_id:
                course = Course.objects.filter(pk=course_id).first()
        elif self.initial.get("course"):
            course = self.initial["course"]
        if course is not None:
            self.fields["prerequisites"].queryset = KnowledgePoint.objects.filter(
                course=course
            ).order_by("order", "code")

    def clean(self):
        data = super().clean()
        course, code = data.get("course"), data.get("code")
        if course and code and KnowledgePoint.objects.filter(course=course, code=code).exists():
            self.add_error("code", "该课程下已存在此编码。")
        return data


class QuestionForm(forms.Form):
    course = forms.ModelChoiceField(label="所属课程", queryset=Course.objects.all())
    knowledge_point = forms.ModelChoiceField(
        label="关联知识点", queryset=KnowledgePoint.objects.all(), required=False
    )
    qtype = forms.ChoiceField(label="题型", choices=Question.QType.choices)
    title = forms.CharField(label="题干", widget=forms.Textarea(attrs={"rows": 3}))
    options_text = forms.CharField(
        label="选项（每行一条，如「A. 数组」）",
        widget=forms.Textarea(attrs={"rows": 4}), required=False,
        help_text="选择题必填；判断题自动使用「正确 / 错误」两个选项；简答题留空。",
    )
    answer = forms.CharField(
        label="参考答案", max_length=255,
        help_text="单选填 A/B/C/D，判断填 T/F，简答填参考要点。",
    )
    analysis = forms.CharField(label="解析", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    difficulty = forms.TypedChoiceField(label="难度", choices=Question.Difficulty.choices, coerce=int)
    score = forms.IntegerField(label="分值", initial=5, min_value=1, max_value=100)

    def __init__(self, *args, courses=None, **kwargs):
        super().__init__(*args, **kwargs)
        if courses is not None:
            self.fields["course"].queryset = courses
            self.fields["knowledge_point"].queryset = KnowledgePoint.objects.filter(
                course__in=courses
            )
        if self.is_bound and self.data.get("course"):
            self.fields["knowledge_point"].queryset = KnowledgePoint.objects.filter(
                course_id=self.data["course"]
            )

    def clean(self):
        data = super().clean()
        qtype, answer = data.get("qtype"), (data.get("answer") or "").strip().upper()
        if qtype == Question.QType.SINGLE and answer not in {"A", "B", "C", "D"}:
            self.add_error("answer", "单选题参考答案应为 A / B / C / D。")
        if qtype == Question.QType.JUDGE and answer not in {"T", "F"}:
            self.add_error("answer", "判断题参考答案应为 T（正确）或 F（错误）。")
        if qtype == Question.QType.SINGLE and not (data.get("options_text") or "").strip():
            self.add_error("options_text", "单选题必须填写选项。")
        return data

    @staticmethod
    def parse_options(text: str) -> list[dict]:
        result = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            if "." in line[:3] or "、" in line[:3] or ":" in line[:3]:
                key, _, value = line.partition(".")
                if not value:
                    key, _, value = line.partition("、")
                if not value:
                    key, _, value = line.partition(":")
                result.append({"key": key.strip().upper()[:2], "text": value.strip()})
            else:
                result.append({"key": chr(ord("A") + len(result)), "text": line})
        return result


class AssignmentForm(forms.Form):
    MODE_MANUAL = "manual"
    MODE_AUTO = "auto"
    classroom = forms.ModelChoiceField(label="教学班", queryset=ClassRoom.objects.none())
    title = forms.CharField(label="作业标题", max_length=128)
    description = forms.CharField(label="说明", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    due_at = forms.DateTimeField(
        label="截止时间（可空）", required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    mode = forms.ChoiceField(
        label="选题方式",
        choices=[(MODE_MANUAL, "手动勾选题目"), (MODE_AUTO, "智能组卷（知识点覆盖贪心）")],
        widget=forms.RadioSelect, initial=MODE_MANUAL,
    )
    questions = forms.ModelMultipleChoiceField(
        label="题目（手动模式）", queryset=Question.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    auto_count = forms.IntegerField(label="智能组卷题数", initial=5, min_value=1, max_value=30, required=False)

    def __init__(self, *args, classrooms=None, **kwargs):
        super().__init__(*args, **kwargs)
        if classrooms is not None:
            self.fields["classroom"].queryset = classrooms
        course_ids = []
        if self.is_bound and self.data.get("classroom"):
            course_ids = list(ClassRoom.objects.filter(
                pk=self.data["classroom"], course__isnull=False
            ).values_list("course_id", flat=True))
        elif classrooms is not None:
            course_ids = list(classrooms.exclude(course__isnull=True)
                              .values_list("course_id", flat=True).distinct())
        self.fields["questions"].queryset = Question.objects.filter(
            course_id__in=course_ids
        ).order_by("difficulty", "id")


class BindingForm(forms.Form):
    """管理员端的任课 / 选课绑定（两张表共用一个页面）。"""
    classroom = forms.ModelChoiceField(label="教学班", queryset=ClassRoom.objects.all())
    teacher = forms.ModelChoiceField(
        label="教师", queryset=User.objects.filter(role=UserRole.TEACHER), required=False
    )
    student = forms.ModelChoiceField(
        label="学生", queryset=User.objects.filter(role=UserRole.STUDENT), required=False
    )


def answer_form_for(assignment: Assignment):
    """按作业题目动态生成一份作答表单。"""
    fields = {}
    for index, question in enumerate(assignment.ordered_questions(), 1):
        label = f"第 {index} 题 · {question.title[:60]}"
        name = f"q_{question.pk}"
        if question.qtype == Question.QType.SHORT:
            fields[name] = forms.CharField(
                label=label, widget=forms.Textarea(attrs={"rows": 3}), required=False
            )
        else:
            fields[name] = forms.ChoiceField(
                label=label, choices=[("", "请选择")] + question.option_pairs(),
                widget=forms.RadioSelect, required=False,
            )
    return type("DynamicAnswerForm", (forms.Form,), fields)
