"""The workspace folder: resolves and checks every file path."""

import os

from .errors import bad_args, forbidden, not_found

IMPORT_EXTENSIONS = (".glb", ".gltf", ".fbx", ".obj")


class Workspace:
    def __init__(self, root):
        os.makedirs(root, exist_ok=True)
        self.root = os.path.realpath(os.path.abspath(root))

    def resolve(self, path, extensions=None):
        if not isinstance(path, str) or not path.strip():
            raise bad_args("the path is empty")
        if "\x00" in path:
            raise bad_args("the path contains a NUL character")
        candidate = path if os.path.isabs(path) else os.path.join(self.root, path)
        resolved = os.path.realpath(os.path.abspath(candidate))
        if not self.contains(resolved):
            raise forbidden(f"{path} is outside the workspace {self.root}")
        if resolved == self.root:
            raise bad_args("the path names the workspace folder itself, not a file")
        if extensions is not None:
            extension = os.path.splitext(resolved)[1].lower()
            if extension not in extensions:
                raise forbidden(f"{path}: only {', '.join(extensions)} files are allowed here")
        return resolved

    def contains(self, resolved):
        try:
            common = os.path.commonpath([os.path.normcase(self.root), os.path.normcase(resolved)])
        except ValueError:
            return False
        return common == os.path.normcase(self.root)

    def relative(self, resolved):
        return os.path.relpath(resolved, self.root).replace(os.sep, "/")

    def output(self, path, extensions):
        resolved = self.resolve(path, extensions)
        if os.path.isdir(resolved):
            raise bad_args(f"{path} is a folder")
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        return resolved

    def existing(self, path, extensions):
        resolved = self.resolve(path, extensions)
        if not os.path.isfile(resolved):
            raise not_found(f"{path} does not exist in the workspace")
        return resolved
