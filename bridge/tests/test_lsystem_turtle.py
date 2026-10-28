import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from lsystem_helpers import assert_frame, positions_of, tree_data, turtle
from blendworks_bridge.tree_skeleton import FORMAT, VERSION
from tree_helpers import tree_of

HEADING = (0.0, 0.0, 1.0)
LEFT = (-1.0, 0.0, 0.0)
UP = (0.0, -1.0, 0.0)


def neg(vector):
    return tuple(-value for value in vector)


def frame_after(symbols, angle=90.0):
    plant = turtle("F" + symbols + "A", angle=angle, organs={"A"})
    return plant.organs[0]


def test_f_plus_f_at_ninety_degrees_ends_where_the_hand_worked_turtle_does(bridge):
    assert positions_of(turtle("F+F")) == [[0, 0, 0], [0, 0, 1], [-1, 0, 1]]
    assert positions_of(turtle("F-F")) == [[0, 0, 0], [0, 0, 1], [1, 0, 1]]
    assert positions_of(turtle("F+F+F+F")) == [[0, 0, 0], [0, 0, 1], [-1, 0, 1], [-1, 0, 0], [0, 0, 0]]
    flat = turtle("F(2)+(90)F(0.5)-(45)F", step=3.0).skeleton.positions
    assert numpy.allclose(flat, [[0, 0, 0], [0, 0, 6], [-1.5, 0, 6], [-1.5 - 3 * math.sqrt(0.5), 0, 6 + 3 * math.sqrt(0.5)]], atol=1e-12)
    plant = turtle("F+(60)F", step=1.0)
    assert numpy.allclose(plant.skeleton.positions[2], [-math.sin(math.radians(60)), 0, 1 + math.cos(math.radians(60))], atol=1e-12)
    assert numpy.allclose(turtle("F|F").skeleton.positions[2], [0, 0, 0])
    assert positions_of(turtle("FfF")) == [[0, 0, 0], [0, 0, 1], [0, 0, 2], [0, 0, 3]]
    assert turtle("FfF").stats["moves"] == 1


def test_brackets_restore_the_position_and_the_frame_exactly(bridge):
    plant = turtle("F[+F]F")
    assert positions_of(plant) == [[0, 0, 0], [0, 0, 1], [-1, 0, 1], [0, 0, 2]]
    assert plant.skeleton.parents.tolist() == [-1, 0, 1, 1]
    assert plant.skeleton.orders.tolist() == [0, 0, 1, 0]
    messy = "F&(37.3)+(81.9)\\(12.5)F"
    plant = turtle(f"{messy}A[F+(23)&(11)\\(5)F[|-(7)^(3)/(9)F]F]A", angle=33.0, organs={"A"})
    before, after = plant.organs
    assert before.position == after.position and before.colour == after.colour
    assert_frame(after, before.heading, before.left, before.up)
    assert plant.stats["branch_depth"] == 2


def test_the_rotations_turn_about_the_axes_of_the_book(bridge):
    cases = {
        "+": (LEFT, neg(HEADING), UP),
        "-": (neg(LEFT), HEADING, UP),
        "&": (neg(UP), LEFT, HEADING),
        "^": (UP, LEFT, neg(HEADING)),
        "\\": (HEADING, neg(UP), LEFT),
        "/": (HEADING, UP, neg(LEFT)),
        "|": (neg(HEADING), neg(LEFT), UP),
    }
    for symbol, (heading, left, up) in cases.items():
        assert_frame(frame_after(symbol), heading, left, up)
    start = frame_after("")
    assert_frame(start, HEADING, LEFT, UP)
    for symbol, fixed in (("+", "up"), ("&", "left"), ("\\", "heading")):
        for angle in (10.0, 77.0, 133.0):
            frame = frame_after(symbol, angle)
            assert getattr(frame, fixed) == getattr(start, fixed), (symbol, angle)
            heading, left, up = (numpy.array(vector) for vector in (frame.heading, frame.left, frame.up))
            assert numpy.allclose(numpy.cross(heading, left), up, atol=1e-12)
            assert abs(numpy.dot(heading, left)) < 1e-12 and abs(numpy.linalg.norm(heading) - 1.0) < 1e-12
    assert numpy.allclose(frame_after("+", 30.0).heading, [-0.5, 0.0, math.sqrt(3) / 2], atol=1e-12)
    assert numpy.allclose(frame_after("&", 30.0).heading, [0.0, 0.5, math.sqrt(3) / 2], atol=1e-12)
    assert numpy.allclose(frame_after("\\", 30.0).left, [-math.sqrt(3) / 2, 0.5, 0.0], atol=1e-12)
    rolled = frame_after("&(90)$")
    assert_frame(rolled, (0.0, 1.0, 0.0), LEFT, (0.0, 0.0, 1.0))


def test_the_tropism_bends_the_heading_towards_the_vector_after_each_segment(bridge):
    plant = turtle("FA", step=1.0, tropism=(1.0, 0.0, 0.0), strength=0.5, organs={"A"})
    assert numpy.allclose(plant.organs[0].heading, [math.sin(0.5), 0.0, math.cos(0.5)], atol=1e-12)
    plant = turtle("FFA", step=1.0, tropism=(1.0, 0.0, 0.0), strength=0.5, organs={"A"})
    assert numpy.allclose(plant.skeleton.positions[2], [math.sin(0.5), 0.0, 1.0 + math.cos(0.5)], atol=1e-12)
    still = turtle("FFA", tropism=(0.0, 0.0, -1.0), strength=2.0, organs={"A"})
    assert still.organs[0].heading == HEADING


def test_widths_follow_the_width_ratio_at_each_branching(bridge):
    plant = turtle("F[F[F]F]F", width=0.02, width_ratio=0.5)
    radii = plant.skeleton.radii
    assert numpy.allclose(radii, [0.01, 0.01, 0.005, 0.0025, 0.005, 0.01])
    wr = 1.0 / math.sqrt(2.0)
    plant = turtle("F[+F[+F]F]F", width=0.02, width_ratio=wr)
    radii = plant.skeleton.radii
    assert numpy.allclose(radii[[2, 3, 4]] / radii[1], [wr, wr * wr, wr])
    assert abs(plant.skeleton.exponent - 2.0) < 1e-9
    assert abs(radii[2] ** 2 * 2 - radii[1] ** 2) < 1e-12
    explicit = turtle("F!F!F!(4)F", width=0.01, width_ratio=0.5, branch_taper=False)
    assert numpy.allclose(explicit.skeleton.radii, [0.005, 0.005, 0.0025, 0.00125, 0.02])
    no_taper = turtle("F[F]F", width=0.02, width_ratio=0.5, branch_taper=False)
    assert numpy.allclose(no_taper.skeleton.radii, 0.01)


def test_the_colour_index_picks_the_organ_variant_and_organs_keep_their_parameters(bridge):
    plant = turtle("FA'A'A'(0)A(2.5)", organs={"A"})
    assert [organ.colour for organ in plant.organs] == [0, 1, 2, 0]
    assert [organ.scale for organ in plant.organs] == [1.0, 1.0, 1.0, 2.5]


def test_the_lsystem_skeleton_is_valid_version_1_with_one_root(bridge):
    result = bridge.ok("lsystem", name="Herb", preset="bracketed_1_24b", iterations=3, limit=5, location=[1.0, 2.0, 3.0])
    data = tree_data("Herb")
    assert data["format"] == FORMAT == "blendworks.skeleton" and data["version"] == VERSION == 1
    assert data["method"] == "lsystem" and data["units"] == "metre" and data["space"] == "object" and data["up"] == "z"
    count = data["count"]
    assert count == result["nodes"] == 5**3 + 1
    assert len(data["position"]) == 3 * count and all(len(data[key]) == count for key in ("parent", "radius", "order", "kind"))
    tree = tree_of("Herb")
    assert numpy.flatnonzero(tree.parents < 0).tolist() == [0]
    assert numpy.all(tree.parents[1:] < numpy.arange(1, count))
    assert numpy.all(tree.kinds == 0) and numpy.all(tree.radii > 0) and tree.radii[0] == tree.radii[1]
    assert numpy.allclose(bpy.data.objects["Herb"].location, [1.0, 2.0, 3.0])
    assert result["method"] == "lsystem" and result["max_order"] == tree.orders.max() == 3
    page = bridge.ok("tree_skeleton", name="Herb", offset=0, limit=3)
    assert page["method"] == "lsystem" and page["nodes"] == count and len(page["page"]["nodes"]) == 3
    exported = bridge.ok("export", path="herb.glb")
    assert exported["skeletons"] == ["Herb"]


def test_the_same_seed_gives_the_same_skeleton_and_other_seeds_differ(bridge):
    def grow(name, seed):
        bridge.ok("lsystem", name=name, preset="stochastic_1_27", seed=seed, limit=0)
        return tree_data(name)

    first, again, other = grow("A", 4), grow("B", 4), grow("C", 5)
    assert first == again and first != other
    bridge.ok("delete", names=["A", "B", "C"])
    species = [grow(f"S{seed}", seed) for seed in range(6)]
    assert len({tuple(plant["parent"]) for plant in species}) > 3
    assert all(plant["tip_radius"] == min(plant["radius"]) for plant in species)


def test_the_preview_is_a_curve_beveled_by_the_node_radii(bridge):
    bridge.ok("lsystem", name="Weed", preset="bracketed_1_24a", iterations=3, limit=0)
    obj = bpy.data.objects["Weed"]
    assert obj.type == "CURVE" and obj.data.bevel_depth == 1.0
    tree = tree_of("Weed")
    starts = [node for node in range(1, len(tree.parents)) if tree.orders[node] != tree.orders[tree.parents[node]]]
    assert len(obj.data.splines) == len(starts) + 1


def test_organs_sit_at_the_turtle_frame_and_are_grouped_under_the_plant(bridge):
    bridge.ok("add_primitive", type="cube", name="Leaf", size=0.1)
    bridge.ok("add_primitive", type="cube", name="Old", size=0.1)
    bridge.ok("add_primitive", type="cube", name="Bloom", size=0.1)
    result = bridge.ok(
        "lsystem",
        name="Bush",
        axiom="F[+(40)FL]F'[-(40)FL]FKM(3)",
        rules=[],
        step=1.0,
        location=[5.0, 0.0, 0.0],
        organs=[{"symbol": "L", "objects": ["Leaf", "Old"], "scale": 2.0}, {"symbol": "K", "objects": ["Bloom"]}, {"symbol": "M", "objects": ["Bloom"], "scale": 0.5, "scale_by_parameter": True}],
        limit=0,
    )
    assert result["lsystem"]["organ_symbols"] == {"K": 1, "L": 2, "M": 1}
    assert result["lsystem"]["organ_groups"] == {"Bush_L0": 1, "Bush_L1": 1, "Bush_K": 1, "Bush_M": 1}
    assert numpy.allclose(bpy.data.objects["Bush_M"].children[0].matrix_world.to_scale(), [1.5, 1.5, 1.5], atol=1e-6)
    assert numpy.allclose(bpy.data.objects["Bush_K"].children[0].matrix_world.to_scale(), [1.0, 1.0, 1.0], atol=1e-6)
    flower = [child for child in bpy.data.objects["Bush_K"].children][0]
    assert flower.data is bpy.data.objects["Bloom"].data
    assert bpy.data.objects["Bush_K"].parent is bpy.data.objects["Bush"]
    assert numpy.allclose(flower.matrix_world.translation, [5.0, 0.0, 3.0], atol=1e-6)
    assert numpy.allclose(numpy.array(flower.matrix_world)[:3, :3], [[0, -1, 0], [0, 0, -1], [1, 0, 0]], atol=1e-6)
    first = bpy.data.objects["Bush_L0"].children[0]
    second = bpy.data.objects["Bush_L1"].children[0]
    turned = math.radians(40)
    assert numpy.allclose(first.matrix_world.translation, [5.0 - math.sin(turned), 0.0, 1.0 + math.cos(turned)], atol=1e-6)
    assert numpy.allclose(second.matrix_world.translation, [5.0 + math.sin(turned), 0.0, 2.0 + math.cos(turned)], atol=1e-6)
    sine, cosine = math.sin(turned), math.cos(turned)
    assert numpy.allclose(numpy.array(first.matrix_world)[:3, :3] / 2.0, [[-sine, -cosine, 0], [0, 0, -1], [cosine, -sine, 0]], atol=1e-6)
    assert numpy.allclose(first.matrix_world.to_scale(), [2.0, 2.0, 2.0], atol=1e-6)
    assert second.data is bpy.data.objects["Old"].data
    bpy.data.objects["Bush"].location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    assert numpy.allclose(flower.matrix_world.translation, [0.0, 0.0, 3.0], atol=1e-6)


def test_organ_symbols_are_checked(bridge):
    bridge.ok("add_primitive", type="cube", name="Leaf")
    for symbol in ("F", "f", "+", "1"):
        message = bridge.refuse("lsystem", "bad_args", name="P", axiom="F", organs=[{"symbol": symbol, "objects": ["Leaf"]}])
        assert "must be one letter other than F and f" in message, message
    assert "longer than 1" in bridge.refuse("lsystem", "bad_args", name="P", axiom="F", organs=[{"symbol": "LL", "objects": ["Leaf"]}])
    message = bridge.refuse("lsystem", "bad_args", name="P", axiom="F", organs=[{"symbol": "L", "objects": ["Leaf"]}, {"symbol": "L", "objects": ["Leaf"]}])
    assert "given twice" in message
    bridge.refuse("lsystem", "not_found", name="P", axiom="F", organs=[{"symbol": "L", "objects": ["Missing"]}])
    message = bridge.refuse("lsystem", "bad_args", name="P", axiom="FL", rules=["L -> LL"], iterations=15, max_length=1_000_000, organs=[{"symbol": "L", "objects": ["Leaf"]}])
    assert "organs, past the cap of 20000" in message, message
    assert [entry["name"] for entry in bridge.ok("scene_info")["objects"]] == ["Leaf"]


def test_unbalanced_brackets_and_empty_drawings_are_refused(bridge):
    assert "']' without a '['" in bridge.refuse("lsystem", "bad_args", name="P", axiom="F]F")
    assert "leaves 1 '[' open" in bridge.refuse("lsystem", "bad_args", name="P", axiom="F[F")
    assert "draws no segment" in bridge.refuse("lsystem", "bad_args", name="P", axiom="+-&")
    assert "negative length" in bridge.refuse("lsystem", "bad_args", name="P", axiom="F(-1)")


run(globals())
