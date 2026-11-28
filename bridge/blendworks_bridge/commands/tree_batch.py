"""The grow_trees command: many trees (skeleton, mesh, leaves) built in parallel workers."""

import time

import bpy

from .. import blendfile, workers
from ..errors import BridgeError, bad_args
from ..registry import COMMANDS, command
from ..schema import array, boolean, described, integer, obj, validate
from .tree_leaves import FIELDS as LEAF_FIELDS
from .tree_mesh import FIELDS as MESH_FIELDS
from .trees import FIELDS as GROW_FIELDS

LEAF_EXCLUDED = ("name", "measure")

TREE = obj(
    {
        "grow": described(obj(GROW_FIELDS), "grow_tree fields of this tree; name, preset, seed and location as there."),
        "mesh": described(obj({key: field for key, field in MESH_FIELDS.items() if key != "name"}), "tree_mesh fields for the bark, built from the skeleton; give {} for the defaults, leave out to keep the skeleton only."),
        "leaves": described(obj({key: field for key, field in LEAF_FIELDS.items() if key not in LEAF_EXCLUDED}), "tree_leaves fields for the foliage on the bark (or on the skeleton without mesh); give {} for the defaults, leave out for none."),
    },
    ["grow"],
)


def tree_steps(tree):
    grow = dict(tree["grow"])
    name = grow.get("name", GROW_FIELDS["name"]["default"])
    grow["name"] = name
    steps = [["grow_tree", grow]]
    carrier = name
    if "mesh" in tree:
        steps.append(["tree_mesh", {"name": name, **tree["mesh"]}])
        carrier = tree["mesh"].get("mesh_name") or f"{name}_bark"
    if "leaves" in tree:
        steps.append(["tree_leaves", {"name": carrier, **tree["leaves"]}])
    return steps


def made_names(steps):
    """The objects a tree's commands make under fixed names, so a batch can refuse a clash before it starts, as building
    the trees one after another would refuse it at the clashing tree."""
    found = []
    for name, args in steps:
        cleaned = validate(COMMANDS[name].schema, args)
        if name == "grow_tree":
            found.append(cleaned["name"])
        elif name == "tree_mesh":
            bark = cleaned.get("mesh_name") or f"{cleaned['name']}_bark"
            found.append(bark)
            if cleaned["twigs"] == "cards":
                found.append(f"{bark}_twigs")
        elif cleaned["realize"] or cleaned["group"]:
            found.append(cleaned.get("leaves_name") or f"{cleaned['name']}_leaves")
    return found


def check_names(batch):
    seen = {}
    for index, steps in enumerate(batch):
        for name in made_names(steps):
            if name in bpy.data.objects:
                raise bad_args(f"trees[{index}]: an object named {name} already exists")
            if name in seen:
                raise bad_args(f"trees[{index}] and trees[{seen[name]}] both make an object named {name}")
            seen[name] = index


def seed_blocks(batch):
    """Existing data-blocks the commands must find by name in a worker: named leaf and twig materials, a leaf source mesh
    and a crown envelope object."""
    found = set()
    for steps in batch:
        for name, args in steps:
            for key, kind in (("material", "materials"), ("twig_material", "materials"), ("source", "objects"), ("envelope", "objects")):
                block = getattr(bpy.data, kind).get(args.get(key, "")) if isinstance(args.get(key), str) else None
                if block is not None:
                    found.add(block)
    return found


def run_serial(ctx, steps):
    return workers.run_steps(ctx.handler, ctx.txn, steps)


def tree_entry(steps, results, built):
    return {"name": steps[0][1]["name"], "built": built, "results": {name: result for (name, _), result in zip(steps, results)}}


def build_parallel(ctx, batch, layout, report):
    trees = []
    with workers.Pool(batch, ctx.workspace.root, layout["threads"], seed_blocks(batch)) as pool:
        pool.start(layout["workers"])
        for index, steps in enumerate(batch):
            record = pool.wait(index)
            if record is None or "error" in record:
                reason = record["error"]["message"] if record else "its worker stopped before delivering it"
                report["fallbacks"].append({"tree": index, "reason": reason})
                trees.append(tree_entry(steps, run_serial(ctx, steps), "serial"))
                continue
            started = time.perf_counter()
            _, merged = blendfile.merge_objects(pool.blend(index), record, ctx.scene, ctx.view_layer)
            merge = time.perf_counter() - started
            report["merge_seconds"] += merge
            for key in ("materials_reused", "images_merged", "node_groups_merged"):
                report[key] += merged[key]
            report["materials_differing"].extend(name for name in merged["materials_differing"] if name not in report["materials_differing"])
            trees.append(tree_entry(steps, record["results"], "worker"))
            report["tasks"].append({"tree": index, "worker": record["worker"], **record["seconds"], "merge": round(merge, 3)})
            report["worker_peak_memory"] = max(report["worker_peak_memory"] or 0, record["peak_memory"] or 0) or None
        report["worker_startup_seconds"] = pool.startup_seconds()
    return trees


@command(
    "grow_trees",
    "Build many trees (grow_tree, tree_mesh, tree_leaves) in parallel child Blender sessions and merge them: the same result as building them one by one.",
    {
        "trees": array(TREE, "The trees, in the order building them one by one would take.", 1, workers.MAX_BATCH_TASKS),
        "workers": integer(f"Most child sessions. Default: as many as the CPUs and the memory allow at about {workers.WORKER_MEMORY_BYTES / 1e9:.1f} GB each, one per tree at most, and serial when fewer than two fit.", 1, workers.MAX_WORKERS),
        "parallel": boolean("false builds every tree in this session, one after another.", True),
    },
    ["trees"],
    slow=True,
    family="natural",
    intents=("grow a whole forest of trees in parallel", "many trees with bark and leaves at once", "batch of trees built on several CPU cores"),
    nearest=(("grow_tree", "for one tree skeleton"), ("scatter", "to place copies of finished trees")),
)
def grow_trees(ctx, args):
    batch = [tree_steps(tree) for tree in args["trees"]]
    check_names(batch)
    layout = workers.plan(len(batch), args.get("workers")) if args["parallel"] else {**workers.plan(len(batch)), "workers": 0, "limited_by": "parallel"}
    report = {"workers": layout["workers"], "threads_per_worker": layout["threads"] if layout["workers"] else None, "cpus": layout["cpus"],
              "memory_available": layout["memory_available"], "worker_memory_estimate": layout["worker_memory_estimate"], "limited_by": layout["limited_by"],
              "fallbacks": [], "tasks": [], "worker_startup_seconds": [], "worker_peak_memory": None, "merge_seconds": 0.0, "materials_reused": 0, "materials_differing": [], "images_merged": 0, "node_groups_merged": 0}
    started = time.perf_counter()
    try:
        if layout["workers"]:
            trees = build_parallel(ctx, batch, layout, report)
        else:
            trees = [tree_entry(steps, run_serial(ctx, steps), "serial") for steps in batch]
    except BridgeError as error:
        raise BridgeError(error.code, f"grow_trees: {error.message}") from error
    ctx.view_layer.update()
    report["seconds"] = round(time.perf_counter() - started, 3)
    report["merge_seconds"] = round(report["merge_seconds"], 3)
    return {"trees": trees, "count": len(trees), **report}
