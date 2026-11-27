"""Camera-relative rendering for worlds far larger than float32 keeps precise.

Cycles and EEVEE flatten every mesh into world space in float32, so a camera at 150 km sees geometry next to it
rounded to 15.6 mm. Every render the bridge starts goes through render(): when the camera that render uses
(scene.camera at that moment) stands farther than safe_camera_distance from the origin, horizontally, the whole world
is moved by minus the camera's position rounded to whole metres, in x and y, so the camera renders from near the
origin; heights stay, so height falloff in haze and shaders that read world z keep their meaning.

How the world moves (WorldShift):
- every root object of the scene, and of every collection an object instances, is parented to one temporary empty
  placed at minus the offset, with an identity parent inverse. Animation, drivers, parents and constraints that work
  in local or relative spaces then evaluate exactly as before, inside the moved frame;
- constraints whose numbers are world positions follow: the bounds of Limit Location in world space, and the inverse
  matrix of Child Of with x and y location on (else the target's offset would be applied twice);
- the instance offset of every instanced collection moves with its objects, so an instance shows them once;
- shaders read world positions as without the move (floating_shaders.ShaderShift).
Before the render the result is measured: every object's evaluated world matrix and every bone's pose matrix must
equal the unmoved one moved by the offset, and every evaluated mesh's bounds must be unchanged. Settings no frame can
follow (emitter particles simulated in world space, modifiers whose texture reads global coordinates, drivers that read
world positions) or a failed measurement keep the world where it is: the render runs unmoved, as precise as float32
allows there, and the reply says why under camera_relative. Afterwards every changed value gets its exact old value
back. With motion blur the measurement covers the frame itself; the moved frame is exact at every subframe for the
settings listed above."""
import math
from contextlib import contextmanager

import bpy
from mathutils import Matrix, Vector

from .floating_shaders import ShaderShift
from .limits import SAFE_CAMERA_DISTANCE
from .rig import TEMPORARY_PREFIX

SHIFT_NAME = TEMPORARY_PREFIX + "world_shift"
MOVE_SHARE = 2.0 ** -10
AXIS_TOLERANCE = 2.0 ** -6
GEOMETRY = ("MESH", "CURVE", "FONT", "SURFACE", "META", "VOLUME", "POINTCLOUD", "CURVES", "GREASEPENCIL")
WORLD_LOCATIONS = ("LOC_X", "LOC_Y")
DRIVEN = ("objects", "materials", "node_groups", "worlds", "meshes", "curves", "lights", "cameras", "scenes",
          "shape_keys", "armatures", "textures", "particles")

notes = []


def begin():
    notes.clear()


def report():
    return list(notes) or None


def note(entry):
    if entry not in notes:
        notes.append(entry)


def shift_for(point):
    if point is None or math.hypot(point.x, point.y) <= SAFE_CAMERA_DISTANCE:
        return None
    return Vector((float(round(point.x)), float(round(point.y)), 0.0))


def render(scene, view_layer=None, **options):
    """bpy.ops.render.render(**options), camera-relative when scene.camera stands far out."""
    with camera_relative(scene, view_layer or bpy.context.view_layer):
        bpy.ops.render.render(**options)


@contextmanager
def camera_relative(scene, view_layer):
    camera = scene.camera
    if camera is None:
        yield None
        return
    view_layer.update()
    shift = shift_for(camera.matrix_world.translation)
    if shift is None:
        yield None
        return
    world = WorldShift(scene, view_layer, shift)
    reason = world.apply()
    if reason is not None:
        note({"camera": camera.name, "kept_origin": reason})
        yield None
        return
    note({"camera": camera.name, "shift": [shift.x, shift.y, 0.0]})
    try:
        yield shift
    finally:
        world.restore()


def root_of(obj):
    while obj.parent is not None:
        obj = obj.parent
    return obj


def gathered(scene):
    """Objects the render can see: the scene's, and those of every collection an object instances, with ancestors."""
    found = {}
    pending = list(scene.objects)
    collections = {}
    while pending:
        obj = pending.pop()
        if obj.name_full in found:
            continue
        found[obj.name_full] = obj
        if obj.parent is not None:
            pending.append(obj.parent)
        if obj.instance_type == "COLLECTION" and obj.instance_collection is not None:
            collection = obj.instance_collection
            if collection.name_full not in collections:
                collections[collection.name_full] = collection
                pending.extend(collection.all_objects)
    return list(found.values()), list(collections.values())


def world_drivers():
    """Drivers whose variables read world positions, which a moved frame changes."""
    found = []
    for kind in DRIVEN:
        for owner in getattr(bpy.data, kind, ()):
            animation = getattr(owner, "animation_data", None)
            for curve in (animation.drivers if animation is not None else ()):
                for variable in curve.driver.variables:
                    for target in variable.targets:
                        world_channel = (variable.type == "TRANSFORMS" and target.transform_space == "WORLD_SPACE"
                                         and target.transform_type in WORLD_LOCATIONS)
                        world_matrix = variable.type == "SINGLE_PROP" and "matrix_world" in (target.data_path or "")
                        if world_channel or world_matrix:
                            found.append(f"the driver on {owner.name}.{curve.data_path} reads world positions")
    return found


def unfollowable(objects):
    """Settings a moved frame cannot reproduce, as reasons."""
    reasons = []
    for obj in objects:
        for system in getattr(obj, "particle_systems", ()):
            if system.settings.type == "EMITTER":
                reasons.append(f"the particles of {obj.name} are simulated in world space")
        for modifier in obj.modifiers:
            if getattr(modifier, "texture_coords", None) == "GLOBAL":
                reasons.append(f"modifier {modifier.name} of {obj.name} reads global coordinates")
    return reasons + world_drivers()


def constraint_owners(objects):
    for obj in objects:
        yield obj, obj.constraints
        if obj.type == "ARMATURE" and obj.pose is not None:
            for bone in obj.pose.bones:
                yield obj, bone.constraints


class WorldShift:
    def __init__(self, scene, view_layer, shift):
        self.scene = scene
        self.view_layer = view_layer
        self.shift = shift
        self.objects, self.collections = gathered(scene)
        self.empty = None
        self.parents = []
        self.values = []
        self.shaders = ShaderShift(shift)

    def apply(self):
        reasons = unfollowable(self.objects)
        if reasons:
            return "; ".join(reasons)
        before = self.measure()
        try:
            self.move()
            self.view_layer.update()
            problem = self.compare(before, self.measure())
        except Exception:
            self.restore()
            raise
        if problem is not None:
            self.restore()
        return problem

    def keep(self, owner, name, value):
        old = getattr(owner, name)
        self.values.append((owner, name, old.copy() if hasattr(old, "copy") else old))
        setattr(owner, name, value)

    def move(self):
        shift = self.shift
        self.empty = bpy.data.objects.new(SHIFT_NAME, None)
        self.scene.collection.objects.link(self.empty)
        self.empty.location = -shift
        roots = {root_of(obj).name_full: root_of(obj) for obj in self.objects}
        for obj in roots.values():
            self.parents.append((obj, obj.parent_type, obj.parent_bone, obj.matrix_parent_inverse.copy()))
            obj.parent = self.empty
            obj.parent_type = "OBJECT"
            obj.matrix_parent_inverse = Matrix.Identity(4)
        for _, constraints in constraint_owners(self.objects):
            for constraint in constraints:
                self.follow(constraint)
        for collection in self.collections:
            self.keep(collection, "instance_offset", Vector(collection.instance_offset) - shift)
        self.shaders.apply()

    def follow(self, constraint):
        shift = self.shift
        if constraint.type == "LIMIT_LOCATION" and constraint.owner_space == "WORLD":
            for axis, offset in (("x", shift.x), ("y", shift.y)):
                for bound in ("min_", "max_"):
                    self.keep(constraint, bound + axis, getattr(constraint, bound + axis) - offset)
        elif constraint.type == "CHILD_OF" and constraint.use_location_x and constraint.use_location_y:
            self.keep(constraint, "inverse_matrix", constraint.inverse_matrix @ Matrix.Translation(shift))

    def measure(self):
        depsgraph = self.view_layer.depsgraph
        found = {}
        for obj in self.objects:
            evaluated = obj.evaluated_get(depsgraph)
            bones = {}
            if obj.type == "ARMATURE" and evaluated.pose is not None:
                bones = {bone.name: bone.matrix.copy() for bone in evaluated.pose.bones}
            bounds = [Vector(corner) for corner in evaluated.bound_box] if obj.type in GEOMETRY else []
            found[obj.name_full] = (evaluated.matrix_world.copy(), bones, bounds)
        return found

    def compare(self, before, after):
        reach = MOVE_SHARE * self.shift.length
        moved = Matrix.Translation(-self.shift)
        for name, (matrix, bones, bounds) in before.items():
            now, now_bones, now_bounds = after[name]
            if off(moved @ matrix, now, reach):
                return f"{name} does not follow a move of the world (a constraint or driver places it in world space)"
            for bone, pose in bones.items():
                if off(pose, now_bones[bone], reach):
                    return f"bone {bone} of {name} does not follow a move of the world"
            if any((a - b).length > reach for a, b in zip(bounds, now_bounds)):
                return f"the evaluated geometry of {name} changes when the world moves (it reads world positions)"
        return None

    def restore(self):
        self.shaders.restore()
        for owner, name, value in reversed(self.values):
            setattr(owner, name, value)
        self.values = []
        for obj, parent_type, parent_bone, inverse in reversed(self.parents):
            obj.parent = None
            obj.parent_type = parent_type
            obj.parent_bone = parent_bone
            obj.matrix_parent_inverse = inverse
        self.parents = []
        if self.empty is not None:
            bpy.data.objects.remove(self.empty)
            self.empty = None
        self.view_layer.update()


def off(expected, actual, reach):
    if (expected.translation - actual.translation).length > reach:
        return True
    for column in range(3):
        axis = expected.col[column].xyz
        if (axis - actual.col[column].xyz).length > AXIS_TOLERANCE * axis.length:
            return True
    return False
