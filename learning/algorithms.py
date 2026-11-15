"""课程项目中可独立讲解、可单测的数据结构与算法实现。

模块内全部是纯函数 / 无 Django 依赖的工具类，方便在报告里给出复杂度分析与
20 / 200 / 2000 规模的实测曲线。视图层只负责把 ORM 数据喂进来。

| 功能 | 数据结构 / 算法 | 复杂度 |
| --- | --- | --- |
| 模糊与精确查找 | Trie 前缀索引 + 编辑距离 DP | 建树 O(L)，查询 O(L + m·n) |
| 智能组卷 | 知识点覆盖贪心 + bisect 难度分档 | O(n log n) |
| 错题复习优先级 | 最小堆（优先队列）+ 遗忘曲线 | O(n log k) |
| 跨班学情合并 | 多路归并 | O(N log k) |
| 多关键字排名 | 稳定排序（Python Timsort） | O(n log n) |
"""

from __future__ import annotations

import bisect
import heapq
import math
from collections import defaultdict
from datetime import timedelta
from typing import Any, Callable, Iterable, Sequence

# 遗忘曲线时间常数（小时）：间隔越久，复习优先级越高
FORGETTING_TAU_HOURS = 72.0


class Trie:
    """前缀树，用于课程 / 知识点 / 用户的精确前缀检索。"""

    def __init__(self) -> None:
        self.children: dict[str, "Trie"] = {}
        self.terminal_ids: set[int] = set()

    def insert(self, word: str, item_id: int) -> None:
        node = self
        for char in word.lower():
            node = node.children.setdefault(char, Trie())
        node.terminal_ids.add(item_id)

    def prefix_ids(self, prefix: str) -> set[int]:
        """收集以 prefix 开头的所有词对应的 id 集合，O(L + 结果规模)。"""
        node = self
        for char in prefix.lower():
            node = node.children.get(char)
            if node is None:
                return set()
        found: set[int] = set(node.terminal_ids)
        stack = [node]
        while stack:
            current = stack.pop()
            for child in current.children.values():
                found.update(child.terminal_ids)
                stack.append(child)
        return found

    def build(self, items: Iterable[tuple[str, int]]) -> "Trie":
        for text, item_id in items:
            self.insert(text, item_id)
        return self


def edit_distance(a: str, b: str) -> int:
    """Levenshtein 距离，标准动态规划，O(|a|·|b|) 时间 / O(min) 空间。"""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                previous[j] + 1,          # 删除
                current[j - 1] + 1,       # 插入
                previous[j - 1] + (ca != cb),  # 替换
            ))
        previous = current
    return previous[-1]


def fuzzy_search(
    items: Sequence[Any],
    query: str,
    text_of: Callable[[Any], str],
    limit: int = 20,
    max_distance: int = 2,
) -> list[Any]:
    """精确包含 > Trie 前缀 > 编辑距离模糊，三级召回后按得分排序。

    返回原对象列表；得分 = 精确匹配加权 + 编辑距离惩罚，越小越靠前。
    """
    query = (query or "").strip()
    if not query:
        return list(items[:limit])

    lowered = query.lower()
    trie = Trie().build((text_of(item).lower(), idx) for idx, item in enumerate(items))
    exact: list[tuple[int, int, Any]] = []
    for idx, item in enumerate(items):
        text = text_of(item).lower()
        if lowered in text:
            exact.append((0 if text.startswith(lowered) else 1, text.find(lowered), item))
    exact.sort(key=lambda row: (row[0], row[1], text_of(row[2])))
    result = [row[2] for row in exact]

    if len(result) < limit:
        seen = {id(item) for item in result}
        prefix_ids = trie.prefix_ids(lowered)
        candidates = [items[i] for i in sorted(prefix_ids) if id(items[i]) not in seen]
        fuzzy: list[tuple[int, int, Any]] = []
        for item in candidates + [x for x in items if id(x) not in seen]:
            if id(item) in seen:
                continue
            dist = edit_distance(lowered, text_of(item).lower()[:64])
            if dist <= max_distance:
                fuzzy.append((dist, len(text_of(item)), item))
                seen.add(id(item))
        fuzzy.sort(key=lambda row: (row[0], row[1]))
        result.extend(row[2] for row in fuzzy)

    return result[:limit]


DIFFICULTY_BANDS = (1, 2, 3, 4, 5)


def difficulty_band(value: int) -> int:
    """用 bisect 在有序档位里定位难度档，O(log 5)，比链式 if 更易扩展。"""
    idx = bisect.bisect_left(DIFFICULTY_BANDS, value)
    return DIFFICULTY_BANDS[min(idx, len(DIFFICULTY_BANDS) - 1)]


def select_questions(pool: Sequence[Any], count: int,
                     difficulty_of: Callable[[Any], int] | None = None,
                     point_of: Callable[[Any], Any] | None = None) -> list[Any]:
    """知识点覆盖优先的贪心组卷：先保证覆盖不同知识点，再补齐难度分布。

    复杂度 O(n log n)。难度用 bisect 分档，知识点用集合判重 O(1)。
    这是「智能出题」在 P2 阶段的本地可解释实现，P3 再叠加 Dify 生成题目。
    """
    if count <= 0:
        return []
    difficulty_of = difficulty_of or (lambda q: getattr(q, "difficulty", 3))
    point_of = point_of or (lambda q: getattr(q, "knowledge_point_id", None))

    ranked = sorted(
        pool,
        key=lambda q: (difficulty_band(difficulty_of(q)), -len(str(point_of(q) or ""))),
    )
    chosen: list[Any] = []
    covered: set[Any] = set()
    for question in ranked:
        point = point_of(question)
        if point is not None and point not in covered:
            chosen.append(question)
            covered.add(point)
    for question in ranked:
        if len(chosen) >= count:
            break
        if question not in chosen:
            chosen.append(question)
    return chosen[:count]


def review_priority(wrong: Any, now) -> float:
    """错题复习优先级：错误次数 × 遗忘残留 × 难度权重；已掌握直接归零。

    间隔越久遗忘越多 → 优先级越高，用 1 - exp(-Δt/τ) 近似艾宾浩斯曲线。
    """
    if getattr(wrong, "mastered", False):
        return 0.0
    last = getattr(wrong, "last_wrong_at", None)
    hours = (now - last).total_seconds() / 3600.0 if last else FORGETTING_TAU_HOURS
    hours = max(0.0, hours)
    forgetting = 1.0 - math.exp(-hours / FORGETTING_TAU_HOURS)
    question = getattr(wrong, "question", None)
    difficulty = getattr(question, "difficulty", 3) or 3
    return round(getattr(wrong, "wrong_count", 1) * forgetting * (1 + 0.15 * (difficulty - 1)), 4)


def build_review_queue(wrongs: Iterable[Any], now, limit: int = 10) -> list[tuple[float, Any]]:
    """最小堆维护 Top-K 复习队列：O(n log k)，比全量排序 O(n log n) 更省。

    返回 [(优先级, 错题对象)]，按优先级从高到低。
    """
    heap: list[tuple[float, int, Any]] = []
    for idx, wrong in enumerate(wrongs):
        priority = review_priority(wrong, now)
        if priority <= 0:
            continue
        item = (priority, idx, wrong)
        if len(heap) < limit:
            heapq.heappush(heap, item)
        elif priority > heap[0][0]:
            heapq.heapreplace(heap, item)
    return [(p, wrong) for p, _, wrong in sorted(heap, reverse=True)]


def multi_key_rank(rows: Sequence[dict], keys: Sequence[str]) -> list[dict]:
    """多关键字排序：按 keys 顺序依次比较，数值型降序、字符串升序。"""
    def sort_key(row: dict):
        parts = []
        for key in keys:
            value = row.get(key)
            if isinstance(value, (int, float)):
                parts.append((0, -value, ""))
            else:
                parts.append((1, 0, str(value or "")))
        return tuple(parts)
    return sorted(rows, key=sort_key)


def merge_sorted_runs(runs: Sequence[Sequence[dict]], key: str = "score") -> list[dict]:
    """多路归并：k 个已按 key 降序排好的班级学情表合成一张总表，O(N log k)。

    用 heapq.merge（惰性最小堆）实现，避免把各班数据拼起来再全量排序。
    """
    keyed = [[(-float(row.get(key) or 0), idx, row) for row in run] for idx, run in enumerate(runs)]
    for run in keyed:
        run.sort()
    return [row for _, _, row in heapq.merge(*keyed)]


def mastery_summary(answers: Iterable[Any]) -> dict[str, dict]:
    """按知识点聚合正确率：一次线性扫描 O(n)，哈希表累计。"""
    stats: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "graded": 0, "correct": 0, "label": ""}
    )
    for answer in answers:
        point = getattr(getattr(answer, "question", None), "knowledge_point", None)
        label = getattr(point, "name", None) or "未分类"
        row = stats[label]
        row["label"] = label
        row["total"] += 1
        verdict = getattr(answer, "is_correct", None)
        if verdict is not None:  # 待复核的简答题不参与正确率分母
            row["graded"] += 1
            if verdict is True:
                row["correct"] += 1
    for row in stats.values():
        row["rate"] = round(row["correct"] / row["graded"], 4) if row["graded"] else 0.0
    return dict(stats)


def review_due(hours_elapsed: float) -> timedelta:
    """复习间隔的简易排程，供错题本展示「建议复习时间」。"""
    return timedelta(hours=max(1.0, FORGETTING_TAU_HOURS * (1 + math.log1p(max(0.0, hours_elapsed)) / 10)))
