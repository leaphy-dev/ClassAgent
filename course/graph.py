"""知识点图谱上的基础算法。

存储：邻接表（prerequisites 多对多表）。
- topological_order：Kahn 拓扑排序，O(V + E)，同时承担环检测。
- prerequisite_closure：反向 BFS，O(V + E)，给出某知识点的全部前置。
两者都供后续「学习路径推荐 / 智能出题 / 错题复盘」复用。
"""

from collections import defaultdict, deque

from .models import KnowledgePoint


class CycleError(ValueError):
    """知识点前置关系存在环，无法给出线性学习顺序。"""


def _load(course):
    nodes = list(
        KnowledgePoint.objects.filter(course=course)
        .prefetch_related("prerequisites")
        .order_by("order", "code")
    )
    return nodes


def topological_order(course) -> list[KnowledgePoint]:
    """返回该课程知识点的合法学习顺序；存在环时抛 CycleError。"""
    nodes = _load(course)
    by_id = {node.pk: node for node in nodes}
    indegree = {node.pk: 0 for node in nodes}
    successors = defaultdict(list)

    for node in nodes:
        for pre in node.prerequisites.all():
            if pre.pk not in by_id:
                continue  # 跨课程的前置关系不计入本课程图谱
            indegree[node.pk] += 1
            successors[pre.pk].append(node.pk)

    # 用 (order, code) 排序保证同层结果稳定可复现
    ready = deque(
        sorted(
            (pk for pk, deg in indegree.items() if deg == 0),
            key=lambda pk: (by_id[pk].order, by_id[pk].code),
        )
    )
    result = []
    while ready:
        pk = ready.popleft()
        result.append(by_id[pk])
        for nxt in successors[pk]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)

    if len(result) != len(nodes):
        blocked = [by_id[pk].code for pk, deg in indegree.items() if deg > 0]
        raise CycleError(f"知识点前置关系存在环，涉及：{', '.join(blocked)}")
    return result


def prerequisite_closure(course, point: KnowledgePoint) -> list[KnowledgePoint]:
    """返回学习某知识点前必须掌握的全部知识点，按拓扑序排列。"""
    order = topological_order(course)
    position = {node.pk: idx for idx, node in enumerate(order)}
    nodes = {node.pk: node for node in order}

    seen = set()
    queue = deque([point.pk])
    while queue:
        pk = queue.popleft()
        for pre in nodes[pk].prerequisites.all():
            if pre.pk in nodes and pre.pk not in seen:
                seen.add(pre.pk)
                queue.append(pre.pk)

    return sorted((nodes[pk] for pk in seen), key=lambda node: position[node.pk])
