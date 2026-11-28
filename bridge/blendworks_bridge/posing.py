"""Posing maths: two-bone solves, bend directions and rotation channels."""

import math

from mathutils import Matrix, Quaternion, Vector

UP = Vector((0.0, 0.0, 1.0))
FORWARD = Vector((0.0, -1.0, 0.0))
SIDEWAYS = Vector((1.0, 0.0, 0.0))


def rotation(axis, degrees):
    return Matrix.Rotation(math.radians(degrees), 4, Vector(axis))


def about(pivot, turn):
    return Matrix.Translation(pivot) @ turn @ Matrix.Translation(-Vector(pivot))


class Poser:
    def __init__(self, armature):
        self.rest = {bone.name: bone.matrix_local.copy() for bone in armature.data.bones}
        self.parents = {bone.name: bone.parent.name if bone.parent else None for bone in armature.data.bones}
        self.lengths = {bone.name: bone.length for bone in armature.data.bones}
        self.targets = {}

    def clear(self):
        self.targets = {}

    def follow(self, name):
        parent = self.parents[name]
        if parent is None:
            return self.rest[name].copy()
        return self.pose(parent) @ self.rest[parent].inverted() @ self.rest[name]

    def pose(self, name):
        if name in self.targets:
            return self.targets[name]
        matrix = self.follow(name)
        self.targets[name] = matrix
        return matrix

    def set(self, name, matrix):
        self.drop_descendants(name)
        self.targets[name] = matrix

    def drop_descendants(self, name):
        for child, parent in self.parents.items():
            if parent == name and child in self.targets:
                del self.targets[child]
                self.drop_descendants(child)

    def head(self, name):
        return self.pose(name).translation.copy()

    def tail(self, name):
        return self.pose(name) @ Vector((0.0, self.lengths[name], 0.0))

    def rest_head(self, name):
        return self.rest[name].translation.copy()

    def rest_tail(self, name):
        return self.rest[name] @ Vector((0.0, self.lengths[name], 0.0))

    def carried(self, name, point):
        return self.pose(name) @ (self.rest[name].inverted() @ Vector(point))

    def turn(self, name, turn, pivot=None):
        base = self.follow(name)
        centre = base.translation if pivot is None else Vector(pivot)
        self.set(name, about(centre, turn) @ base)

    def aim(self, name, direction, head=None):
        base = self.follow(name)
        direction = Vector(direction).normalized()
        current = base.col[1].to_3d().normalized()
        spin = current.rotation_difference(direction).to_matrix()
        matrix = (spin @ base.to_3x3()).to_4x4()
        matrix.translation = base.translation if head is None else Vector(head)
        self.set(name, matrix)

    def place(self, name, location, orientation):
        matrix = orientation.to_3x3().normalized().to_4x4()
        matrix.translation = Vector(location)
        self.set(name, matrix)

    def basis(self, name):
        parent = self.parents[name]
        target = self.pose(name)
        if parent is None:
            return self.rest[name].inverted() @ target
        local = self.rest[parent].inverted() @ self.rest[name]
        return local.inverted() @ self.pose(parent).inverted() @ target


def two_bone(root, target, upper, lower, pole):
    offset = Vector(target) - Vector(root)
    reach = offset.length
    if reach < 1e-9:
        offset = Vector((0.0, 0.0, -1.0))
        reach = 1e-9
    along = offset.normalized()
    distance = min(max(reach, abs(upper - lower) + 1e-6), (upper + lower) * (1.0 - 1e-6))
    side = Vector(pole) - along * Vector(pole).dot(along)
    if side.length < 1e-9:
        side = FORWARD - along * FORWARD.dot(along)
        if side.length < 1e-9:
            side = SIDEWAYS.copy()
    side.normalize()
    run = (upper * upper - lower * lower + distance * distance) / (2.0 * distance)
    rise = math.sqrt(max(upper * upper - run * run, 0.0))
    middle = Vector(root) + along * run + side * rise
    return middle, reach <= upper + lower


def bend_direction(root, middle, end):
    line = Vector(end) - Vector(root)
    offset = Vector(middle) - Vector(root)
    if line.length < 1e-9:
        return FORWARD.copy()
    along = line.normalized()
    side = offset - along * offset.dot(along)
    return side.normalized() if side.length > 1e-6 * line.length else FORWARD.copy()


def basis_channels(matrix, previous=None):
    location, quaternion, scale = matrix.decompose()
    quaternion.normalize()
    if previous is not None and quaternion.dot(previous) < 0:
        quaternion = Quaternion((-quaternion.w, -quaternion.x, -quaternion.y, -quaternion.z))
    return location, quaternion, scale


def leg_reach_height(hip, ankle, upper, lower, slack):
    horizontal = math.hypot(ankle.x - hip.x, ankle.y - hip.y)
    length = (upper + lower) * slack
    if horizontal >= length:
        return ankle.z
    return ankle.z + math.sqrt(length * length - horizontal * horizontal)
