import bpy

from . import view_materials, view_surfaces, wire_edges
from .errors import bad_args

VIEWS = ("shaded", "clay", "wireframe", "normals")
SURFACE_VIEWS = ("clay", "wireframe", "normals")
FLAT_VIEWS = ("normals",)
UNDENOISED_VIEWS = ("wireframe", "normals")


def rendered_objects(scene, view_layer):
    """The objects whose surfaces a render can show: the scene's objects that render, and every object instanced into it
    (collection instances, particle and geometry node instances of objects), also from outside the scene."""
    found = {obj.name_full: obj for obj in scene.objects if not obj.hide_render}
    view_layer.update()
    for instance in view_layer.depsgraph.object_instances:
        if instance.is_instance:
            original = instance.object.original
            if original is not None and original.name_full not in found:
                found[original.name_full] = original
    return list(found.values())


def run_all(steps):
    """Runs every step, also after one fails, and raises the first failure at the end."""
    failure = None
    for step in steps:
        try:
            step()
        except Exception as error:
            failure = failure or error
    if failure is not None:
        raise failure


class RenderView:
    """Clay, wireframe or normals for one render. Every material in use is swapped for a copy whose light-scattering
    closures are the view's shader, so opacity, alpha masks and ray visibility stay as they are; volumes, the world, sky,
    clouds and haze are untouched. Everything is put back on exit, one step at a time, also when a step fails."""

    def __init__(self, scene, view_layer, mode, camera=None, wire_width=view_materials.DEFAULT_WIRE_WIDTH, wire_triangles=False):
        if mode not in VIEWS:
            raise bad_args(f"shading must be one of {', '.join(VIEWS)}")
        self.scene = scene
        self.view_layer = view_layer
        self.mode = mode
        self.camera = camera
        self.wire_width = wire_width
        self.wire_triangles = wire_triangles
        self.group = None
        self.surfaces = None
        self.edges = wire_edges.PolygonEdges()
        self.view = None
        self.report = {}

    def __enter__(self):
        try:
            self.apply()
        except BaseException:
            self.restore(quiet=True)
            raise
        return self

    def __exit__(self, kind, error, trace):
        self.restore(quiet=kind is not None)
        return False

    def apply(self, counted=None):
        """counted: the objects whose mesh edges `wire_edges` reports; by default every rendered object of the scene."""
        if self.mode not in SURFACE_VIEWS:
            return
        if self.mode in FLAT_VIEWS:
            view = self.scene.view_settings
            self.view = (view.view_transform, view.look, view.exposure, view.gamma)
            view.view_transform = "Standard"
            view.look = "None"
            view.exposure = 0.0
            view.gamma = 1.0
        objects = rendered_objects(self.scene, self.view_layer)
        polygon_edges = self.mode == "wireframe" and not self.wire_triangles and self.camera is not None and self.camera.data.type in ("PERSP", "ORTHO")
        if self.mode == "clay":
            self.group = view_materials.clay_group()
        elif self.mode == "normals":
            self.group = view_materials.normals_group()
        else:
            footprint = view_materials.pixel_footprint(self.camera, self.scene) if polygon_edges else None
            self.group = view_materials.wire_group(self.wire_width, footprint)
        self.surfaces = view_surfaces.SurfaceSwap(self.group, self.mode)
        self.report["view_materials"] = self.surfaces.apply(objects)
        if self.mode != "wireframe":
            return
        if counted is None:
            counted = [obj for obj in self.scene.objects if not obj.hide_render]
        self.report["wire_edges"] = sum(len(obj.data.edges) for obj in counted if obj.type == "MESH")
        if polygon_edges:
            self.report["wire_polygon_objects"] = self.edges.attach(objects, self.scene, self.view_layer)
        self.report["wire_width"] = self.wire_width
        self.report["wire_edges_drawn"] = "polygon" if polygon_edges else "triangle"

    def restore(self, quiet=False):
        """Puts everything back. Each step runs even when an earlier one fails; the first failure is raised unless quiet
        (the render already failed and that error is the one to report)."""
        steps = self.edges.restore_steps()
        if self.surfaces is not None:
            steps += self.surfaces.restore_steps()
            self.surfaces = None
        steps.append(self.remove_group)
        steps.append(self.restore_view)
        try:
            run_all(steps)
        except Exception:
            if not quiet:
                raise

    def remove_group(self):
        if self.group is not None:
            bpy.data.node_groups.remove(self.group)
            self.group = None

    def restore_view(self):
        if self.view is not None:
            view = self.scene.view_settings
            view.view_transform, view.look, view.exposure, view.gamma = self.view
            self.view = None
