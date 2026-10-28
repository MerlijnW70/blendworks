import re
from urllib.parse import unquote_to_bytes

MAX_REFERENCE_LENGTH = 1024
MAX_SEGMENT_LENGTH = 255

REFUSAL_REASONS = {
    "empty": "the reference names no file",
    "encoding": "the reference is not valid percent-encoding",
    "control": "the reference holds a control character",
    "scheme": "the reference has a scheme, a drive or a stream name",
    "absolute": "the reference is an absolute or UNC path",
    "escape": "the reference leaves the asset folder",
    "device": "the reference names a Windows device",
    "trailing": "a part of the reference ends in a dot or a space",
    "long": f"the reference is longer than {MAX_REFERENCE_LENGTH} characters or has a part longer than {MAX_SEGMENT_LENGTH}",
}

DEVICE_NAMES = re.compile(r"^(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³]|conin\$|conout\$|clock\$)$", re.IGNORECASE)
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SEPARATORS = re.compile(r"[/\\]")
PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")


def code_units(text):
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def decode_uri(raw):
    if PERCENT.search(raw):
        return None
    try:
        return unquote_to_bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        return None


def decoded(raw, style):
    if style == "uri":
        text = decode_uri(raw)
        return (text, None) if text is not None else (None, "encoding")
    if style == "blend":
        if raw.startswith("//"):
            return raw[2:], None
        return None, "empty" if raw == "" else "absolute"
    return raw, None


def segment_problem(segment):
    if code_units(segment) > MAX_SEGMENT_LENGTH:
        return "long"
    if DEVICE_NAMES.match(segment.split(".")[0].rstrip(" ")):
        return "device"
    if segment.endswith(".") or segment.endswith(" "):
        return "trailing"
    return None


def refused(code):
    return None, (code, REFUSAL_REASONS[code])


def check_reference(raw, style):
    path, problem = decoded(raw, style)
    if problem is not None:
        return refused(problem)
    if path == "":
        return refused("empty")
    if code_units(path) > MAX_REFERENCE_LENGTH:
        return refused("long")
    if CONTROL.search(path):
        return refused("control")
    if path.startswith("/") or path.startswith("\\"):
        return refused("absolute")
    if ":" in path:
        return refused("scheme")
    kept = []
    for segment in SEPARATORS.split(path):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not kept:
                return refused("escape")
            kept.pop()
            continue
        problem = segment_problem(segment)
        if problem is not None:
            return refused(problem)
        kept.append(segment)
    if not kept:
        return refused("empty")
    return "/".join(kept), None
