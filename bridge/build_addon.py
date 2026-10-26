import os
import sys
import zipfile

BRIDGE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(BRIDGE, "addon")
PACKAGE = os.path.join(BRIDGE, "blendworks_bridge")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def addon_files():
    files = []
    for folder, prefix in ((ADDON, ""), (PACKAGE, "blendworks_bridge/")):
        for root, directories, names in os.walk(folder):
            directories[:] = sorted(name for name in directories if name != "__pycache__")
            for name in sorted(names):
                if name.endswith((".pyc", ".pyo")):
                    continue
                path = os.path.join(root, name)
                relative = os.path.relpath(path, folder).replace(os.sep, "/")
                files.append((prefix + relative, path))
    return sorted(files)


def build(output):
    folder = os.path.dirname(os.path.abspath(output))
    os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, path in addon_files():
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as handle:
                archive.writestr(info, handle.read().replace(b"\r\n", b"\n"))
    return output


def main(argv):
    own = argv[argv.index("--") + 1 :] if "--" in argv else argv[1:]
    if len(own) != 1:
        print("usage: build_addon.py -- <output.zip>", file=sys.stderr)
        raise SystemExit(2)
    output = build(own[0])
    print(f"wrote {output}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
