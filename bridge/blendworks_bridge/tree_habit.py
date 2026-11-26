import numpy

from .tree_strands import coefficient_of_variation

WHORL_SIZE = 3
REACH = 1.0
LEVEL_ANGLE = 65.0
CONIFER = {"whorled_share": 0.7, "level_share": 0.6, "clear_bole": 0.35}


def first_order_branches(skeleton):
    """(attachment node, first node, direction a metre out) of every branch that leaves the trunk."""
    shoot = skeleton.kinds == 0
    children = [[] for _ in range(skeleton.count)]
    for node in range(1, skeleton.count):
        children[skeleton.parents[node]].append(node)
    found = []
    for node in range(1, skeleton.count):
        parent = skeleton.parents[node]
        if not (shoot[node] and skeleton.orders[node] == 1 and skeleton.orders[parent] == 0):
            continue
        walked, current = 0.0, node
        start = skeleton.positions[parent]
        while walked < REACH:
            walked += float(numpy.linalg.norm(skeleton.positions[current] - skeleton.positions[skeleton.parents[current]]))
            same = [child for child in children[current] if skeleton.orders[child] == 1]
            if walked >= REACH or not same:
                break
            current = same[0]
        step = skeleton.positions[current] - start
        found.append((int(parent), node, step / max(float(numpy.linalg.norm(step)), 1e-9)))
    return found


def habit_statistics(skeleton):
    """How a skeleton branches off its trunk: whorls, branch angles and the clear bole, the marks of a pine's habit (docs/DESIGN.md, Tree skeletons)."""
    branches = first_order_branches(skeleton)
    if not branches:
        return {"branches": 0, "conifer": False}
    shoot = skeleton.positions[skeleton.kinds == 0]
    base = float(skeleton.positions[0, 2])
    height = float(shoot[:, 2].max()) - base
    attach = numpy.array([parent for parent, _, _ in branches])
    nodes, counts = numpy.unique(attach, return_counts=True)
    whorl_nodes = nodes[counts >= WHORL_SIZE]
    whorled = float(numpy.isin(attach, whorl_nodes).mean())
    heights = numpy.sort(skeleton.positions[whorl_nodes, 2] - base)
    gaps = numpy.diff(heights)
    angles = numpy.degrees(numpy.arccos(numpy.clip([direction[2] for _, _, direction in branches], -1.0, 1.0)))
    lowest = float((skeleton.positions[attach, 2] - base).min())
    radial = numpy.linalg.norm(shoot[:, :2] - skeleton.positions[0, :2], axis=1)
    crown = height - lowest
    report = {
        "branches": len(branches),
        "whorls": int(len(whorl_nodes)),
        "whorled_share": round(whorled, 4),
        "whorl_spacing": round(float(gaps.mean()), 4) if len(gaps) else 0.0,
        "whorl_spacing_cv": round(coefficient_of_variation(gaps), 4) if len(gaps) > 1 else 0.0,
        "branch_angle": round(float(numpy.median(angles)), 2),
        "branch_angle_spread": round(float(angles.std()), 2),
        "level_share": round(float((angles >= LEVEL_ANGLE).mean()), 4),
        "clear_bole": round(lowest / height, 4) if height > 0.0 else 0.0,
        "crown_ratio": round(2.0 * float(numpy.percentile(radial, 95.0)) / crown, 4) if crown > 0.0 else 0.0,
    }
    report["conifer"] = all(report[key] >= limit for key, limit in CONIFER.items())
    return report

