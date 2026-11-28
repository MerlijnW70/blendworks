import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

from blendworks_bridge import terrain_bundle, terrain_core
from erode_helpers import make_tile

KEY = terrain_bundle.platform_key()
LIBRARY = terrain_core.library_name()


def write_bundle(root, content, listed=None, key=None):
    key = key or KEY or "linux-x64"
    (root / key).mkdir(parents=True, exist_ok=True)
    (root / key / LIBRARY).write_bytes(content)
    sha = hashlib.sha256(listed if listed is not None else content).hexdigest()
    (root / "manifest.json").write_text(json.dumps({"schema": 1, "commit": "0" * 40, "files": {key: {"file": LIBRARY, "sha256": sha, "size": len(content)}}}))
    return root / key / LIBRARY


@contextlib.contextmanager
def isolated(bundle_root, developer=None):
    saved = (dict(terrain_core.STATE), terrain_core.default_path, terrain_bundle.bundled_roots, os.environ.pop(terrain_core.LIBRARY_VARIABLE, None))
    terrain_core.STATE.clear()
    terrain_core.default_path = lambda: developer or bundle_root / "no-developer-build" / LIBRARY
    terrain_bundle.bundled_roots = lambda: [bundle_root]
    try:
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            yield errors
    finally:
        terrain_core.STATE.clear()
        terrain_core.STATE.update(saved[0])
        terrain_core.default_path, terrain_bundle.bundled_roots = saved[1], saved[2]
        if saved[3] is not None:
            os.environ[terrain_core.LIBRARY_VARIABLE] = saved[3]


def test_the_core_for_each_platform_string_is_picked_by_system_and_architecture(bridge):
    expected = {("win32", "AMD64"): "win32-x64", ("linux", "x86_64"): "linux-x64", ("darwin", "arm64"): "darwin-arm64", ("darwin", "x86_64"): "darwin-x64", ("linux", "aarch64"): None, ("win32", "ARM64"): None, ("freebsd13", "amd64"): None}
    for (system, machine), key in expected.items():
        assert terrain_bundle.platform_key(system, machine) == key, (system, machine)
    assert set(terrain_bundle.PLATFORMS) == {"win32-x64", "linux-x64", "darwin-arm64", "darwin-x64"}


def test_a_bundled_core_is_loaded_only_when_its_sha256_matches_the_manifest(bridge):
    root = Path(tempfile.mkdtemp())
    content = b"core bytes"
    path = write_bundle(root, content)
    chosen = terrain_bundle.select(KEY or "linux-x64", [root])
    assert chosen["check"] == "loaded" and chosen["path"] == str(path) and chosen["data"] == content
    path.write_bytes(b"tampered core")
    chosen = terrain_bundle.select(KEY or "linux-x64", [root])
    assert chosen["check"] == "mismatched" and chosen["data"] is None and "refusing" in chosen["reason"]
    assert chosen["expected"] == hashlib.sha256(content).hexdigest() and chosen["actual"] == hashlib.sha256(b"tampered core").hexdigest()
    other = "darwin-arm64" if KEY != "darwin-arm64" else "linux-x64"
    assert terrain_bundle.select(other, [root])["check"] == "missing"


def test_a_mismatched_bundled_core_is_refused_and_the_python_reference_runs(bridge):
    if KEY is None:
        return
    root = Path(tempfile.mkdtemp())
    write_bundle(root, b"not the listed library", listed=b"the listed library")
    with isolated(root) as errors:
        assert terrain_core.core() is None
        report = terrain_core.report()
        assert report["engine"] == "python" and report["check"] == "mismatched" and "refusing" in report["reason"]
        assert terrain_core.status()["check"] == "mismatched" and terrain_core.status()["loaded"] is False
    assert "Python reference" in errors.getvalue()


def test_a_developer_build_takes_precedence_over_the_bundled_core_and_is_reported_as_such(bridge):
    root = Path(tempfile.mkdtemp())
    write_bundle(root, b"bundled")
    developer = root / "developer" / LIBRARY
    developer.parent.mkdir()
    developer.write_bytes(b"developer")
    with isolated(root, developer):
        source, chosen = terrain_core.locate({})
        assert source == "developer" and chosen["path"] == str(developer)
        developer.unlink()
        source, chosen = terrain_core.locate({})
        assert source == "bundled" or KEY is None
        assert terrain_core.locate({terrain_core.LIBRARY_VARIABLE: "/x/core.so"})[0] == "environment"
    built = terrain_core.default_path()
    if built.is_file():
        assert terrain_core.core() is not None
        assert terrain_core.report()["source"] == "developer" and terrain_core.report()["engine"] == "native"


def test_a_missing_core_states_its_reason_and_the_slowdown_once_and_in_the_results(bridge):
    root = Path(tempfile.mkdtemp())
    with isolated(root) as errors:
        assert terrain_core.core() is None and terrain_core.core() is None
        report = terrain_core.report()
        assert report["engine"] == "python" and report["check"] == "missing" and report["reason"]
        assert "100 times slower" in report["slowdown"]
        lines = [line for line in errors.getvalue().splitlines() if line.startswith("blendworks:")]
        assert len(lines) == 1 and "100 times slower" in lines[0] and report["reason"] in lines[0]
        info = bridge.ok("scene_info", detail="summary")
        assert info["native_core"] == report
        make_tile(bridge, "t")
        eroded = bridge.ok("erode", name="t", mode="thermal", iterations=1)
        assert eroded["native_core"] == report


run(globals())
