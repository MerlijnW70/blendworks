import os
import time

import numpy
import scene
from blendworks_bridge import blendfile

SMALL = dict(scene.SIZES["check"], land_resolution=61, rings=(), rocks=20, budget=2000, river_trials=1)


def small_build(bench):
    bench.cmd("new_scene")
    scene.terrain(bench)
    heights = scene.land_points()
    report = scene.lake(bench, heights)
    flow = scene.river(bench, heights, report)
    mouth = numpy.array(flow["path"][-1])
    heights = scene.land_points()
    placed = scene.rocks(bench)
    shots = scene.cameras(bench, heights, report, mouth)
    obstacles = placed.get("objects") or [placed["name"]]
    bench.cmd("ground_cover", target="land", preset="meadow", cameras=shots, near=bench.size["near"], view_only=True, budget=bench.size["budget"],
              obstacles=obstacles, seed=5)
    bench.cmd("atmosphere", visibility=10000.0, height_falloff=300.0)


def folder_bytes(folder):
    if not os.path.isdir(folder):
        return 0
    return sum(os.path.getsize(os.path.join(folder, name)) for name in os.listdir(folder) if os.path.isfile(os.path.join(folder, name)))


class Driver:
    def __init__(self, out, size, **options):
        self.size = size if isinstance(size, dict) else scene.SIZES[size]
        self.handler = scene.Handler(out, allow_python=False, desktop=False, **options)
        self.folder = os.path.join(out, ".blendworks")
        self.calls = []
        self.folder_peak = 0
        self.legacy_seconds = 0.0
        self.watch_copies()
        self.snapshots = []
        if hasattr(self.handler.autosave, "snapshot"):
            self.log_snapshots()
        else:
            self.time_legacy_saves()

    def log_snapshots(self):
        autosave = self.handler.autosave
        taking = autosave.snapshot

        def logged(reason):
            started = time.perf_counter()
            saved = taking(reason)
            record = autosave.record or {}
            self.snapshots.append({"reason": reason, "ok": saved, "seconds": round(time.perf_counter() - started, 4), "bytes": record.get("bytes"), "call": len(self.calls)})
            return saved

        autosave.snapshot = logged

    def watch_copies(self):
        name = "write_blend" if hasattr(blendfile, "write_blend") else "write_copy"
        original = getattr(blendfile, name)

        def watched(*args, **kwargs):
            written = original(*args, **kwargs)
            self.folder_peak = max(self.folder_peak, folder_bytes(self.folder))
            return written

        setattr(blendfile, name, watched)

    def time_legacy_saves(self):
        saving = self.handler.autosave.save

        def timed(reason):
            started = time.perf_counter()
            try:
                return saving(reason)
            finally:
                self.legacy_seconds += time.perf_counter() - started

        self.handler.autosave.save = timed

    def autosave_seconds(self):
        autosave = self.handler.autosave
        return autosave.seconds if hasattr(autosave, "snapshot") else self.legacy_seconds

    def cmd(self, name, /, **args):
        return self.call(name, True, args)

    def attempt(self, name, /, **args):
        return self.call(name, False, args)

    def call(self, name, required, args):
        started = time.perf_counter()
        reply = self.handler.handle({"cmd": name, "args": args})
        self.calls.append({"cmd": name, "ok": reply["ok"], "wall": round(time.perf_counter() - started, 4)})
        self.folder_peak = max(self.folder_peak, folder_bytes(self.folder))
        if not reply["ok"]:
            if required:
                raise RuntimeError(f"{name}: {reply['error']['message']}")
            return None
        return reply["result"]
