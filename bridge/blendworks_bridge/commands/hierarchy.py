import bpy

from ..errors import bad_args, not_found
from ..limits import MAX_SCALE_FACTOR
from ..registry import command
from ..schema import CREATES, EXISTS, boolean, length, names, ref, string, vector3
from ..util import get_object, get_objects, link_object, place, require_free_name, vec

DISPLAYS = ("plain_axes", "arrows", "single_arrow", "circle", "cube", "sphere", "cone")
MAX_COLLECTIONS = 1_000


def scene_collections(scene):
    found = {collection.name: collection for collection in scene.collection.children_recursive}
    found[scene.collection.name] = scene.collection
    return found


def get_collection(scene, name):
    collection = scene_collections(scene).get(name)
    if collection is None:
        raise not_found(f"no collection named {name} in the scene; collection_create makes one")
    return collection


def move_to(obj, collection):
    for other in list(obj.users_collection):
        other.objects.unlink(obj)
    collection.objects.link(obj)


@command(
    "add_empty",
    "Add an empty to group and place objects: a display type, a display size in metres and a transform, optionally under a parent or in a collection.",
    {
        "name": ref(string("Object name; must be unused."), "object", CREATES),
        "display": string("How the empty is drawn in Blender.", list(DISPLAYS), "plain_axes"),
        "size": length("Display size in metres.", 1.0),
        "location": vector3("Position in metres, relative to the parent when there is one.", [0.0, 0.0, 0.0]),
        "rotation": vector3("Euler XYZ rotation in degrees.", [0.0, 0.0, 0.0]),
        "scale": vector3("Scale per axis.", [1.0, 1.0, 1.0], -MAX_SCALE_FACTOR, MAX_SCALE_FACTOR),
        "parent": ref(string("Object to parent the empty to."), "object", EXISTS),
        "collection": ref(string("Collection to put the empty in. Default: the scene collection."), "collection", EXISTS),
    },
    ["name"],
    family="hierarchy",
    intents=("empty as a group root or pivot", "null object to group parts"),
    nearest=(("collection_create", "to group objects without a transform"),),
)
def add_empty(ctx, args):
    require_free_name(args["name"])
    parent = get_object(args["parent"]) if "parent" in args else None
    collection = get_collection(ctx.scene, args["collection"]) if "collection" in args else None
    obj = link_object(ctx, args["name"], None)
    obj.empty_display_type = args["display"].upper()
    obj.empty_display_size = args["size"]
    place(obj, args["location"], args["rotation"])
    obj.scale = args["scale"]
    if parent is not None:
        obj.parent = parent
    if collection is not None:
        move_to(obj, collection)
    return {
        "name": obj.name,
        "display": args["display"],
        "size": args["size"],
        "parent": parent.name if parent else None,
        "collections": sorted(item.name for item in obj.users_collection),
        "location": vec(obj.location),
    }


@command(
    "collection_create",
    "Create a collection under the scene collection or another collection, optionally putting objects in it.",
    {
        "name": ref(string("Collection name; must be unused."), "collection", CREATES),
        "parent": ref(string("Collection to nest it in. Default: the scene collection."), "collection", EXISTS),
        "objects": ref(names("Objects to link into the new collection.", min_items=0), "object", EXISTS),
    },
    ["name"],
    family="hierarchy",
    intents=("new collection for some objects", "group objects in a collection"),
    nearest=(("collection_link", "to put objects in an existing collection"),),
)
def collection_create(ctx, args):
    if args["name"] in bpy.data.collections or args["name"] == ctx.scene.collection.name:
        raise bad_args(f"a collection named {args['name']} already exists")
    if len(bpy.data.collections) >= MAX_COLLECTIONS:
        raise bad_args(f"the scene already has {MAX_COLLECTIONS} collections")
    holder = get_collection(ctx.scene, args["parent"]) if "parent" in args else ctx.scene.collection
    objects = get_objects(args.get("objects", []))
    collection = bpy.data.collections.new(args["name"])
    holder.children.link(collection)
    for obj in objects:
        collection.objects.link(obj)
    return {"name": collection.name, "parent": holder.name, "objects": sorted(obj.name for obj in objects)}


@command(
    "collection_link",
    "Link objects into a collection; with move they leave every other collection, so the collection holds them alone.",
    {
        "collection": ref(string("Collection to link the objects into."), "collection", EXISTS),
        "names": ref(names("Objects to link."), "object", EXISTS),
        "move": boolean("Unlink the objects from all their other collections.", False),
    },
    ["collection", "names"],
    family="hierarchy",
    intents=("put objects into an existing collection", "move objects to a collection"),
    nearest=(("collection_create", "when the collection does not exist yet"),),
)
def collection_link(ctx, args):
    collection = get_collection(ctx.scene, args["collection"])
    objects = get_objects(args["names"])
    already = [obj.name for obj in objects if obj.name in collection.objects]
    if already:
        raise bad_args(f"{', '.join(already)} already in {collection.name}")
    for obj in objects:
        if args["move"]:
            move_to(obj, collection)
        else:
            collection.objects.link(obj)
    return {"collection": collection.name, "linked": sorted(obj.name for obj in objects), "moved": args["move"]}


@command(
    "collection_unlink",
    "Unlink objects from a collection; an object must stay in at least one collection, so unlinking its last one is refused.",
    {"collection": ref(string("Collection to unlink the objects from."), "collection", EXISTS), "names": ref(names("Objects to unlink."), "object", EXISTS)},
    ["collection", "names"],
    family="hierarchy",
    intents=("take objects out of a collection", "remove an object from one collection and keep it in the others",),
    nearest=(("delete", "to remove the objects"),),
)
def collection_unlink(ctx, args):
    collection = get_collection(ctx.scene, args["collection"])
    objects = get_objects(args["names"])
    missing = [obj.name for obj in objects if obj.name not in collection.objects]
    if missing:
        raise bad_args(f"{', '.join(missing)} not in {collection.name}")
    last = [obj.name for obj in objects if len(obj.users_collection) == 1]
    if last:
        raise bad_args(f"{', '.join(last)} would be in no collection; link it to another one first, or delete it")
    for obj in objects:
        collection.objects.unlink(obj)
    return {"collection": collection.name, "unlinked": sorted(obj.name for obj in objects)}
