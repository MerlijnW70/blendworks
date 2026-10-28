import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bridge"))

from blendworks_bridge import Handler


def arguments():
    return sys.argv[sys.argv.index("--") + 1 :][0]


def plain(value):
    if hasattr(value, "to_dict"):
        return {key: plain(item) for key, item in value.to_dict().items()}
    if hasattr(value, "to_list"):
        return value.to_list()
    return value


def main():
    import bpy

    folder = arguments()
    handler = Handler(folder, allow_python=False, desktop=False)

    def cmd(name, /, **args):
        reply = handler.handle({"cmd": name, "args": args})
        if not reply["ok"]:
            raise RuntimeError(f"{name}: {reply['error']['message']}")
        return reply["result"]

    cmd("new_scene")
    cmd("grow_tree", name="broadleaf", height=6.0, trunk_height=1.5, crown_radius=2.0, points=700, influence=0.9, kill=0.2, step=0.12, seed=4, exponent=2.2, roots={"points": 300, "depth": 0.8, "radius": 1.4, "influence": 0.6, "kill": 0.18, "step": 0.1}, limit=0)
    cmd("grow_tree", name="conifer", method="levels", envelope="conical", location=[4.0, 0.0, 0.0], height=7.0, trunk_height=1.0, branches=[20, 5], limit=0)
    cmd("export", path="trees.glb")
    expected = {name: plain(bpy.data.objects[name]["blendworks_skeleton"]) for name in ("broadleaf", "conifer")}
    with open(os.path.join(folder, "trees.expected.json"), "w", encoding="utf-8") as handle:
        json.dump(expected, handle)
    shutil.rmtree(os.path.join(folder, ".blendworks"), ignore_errors=True)


main()
