import json

from .errors import bad_args
from .handler import encode, error_reply
from .limits import MAX_REQUEST_BYTES

TOO_LONG = object()


def read_request(reader, limit=MAX_REQUEST_BYTES):
    while True:
        raw = reader.readline(limit + 1)
        if not raw:
            return None
        if len(raw) > limit and not raw.endswith(b"\n"):
            while raw and not raw.endswith(b"\n"):
                raw = reader.readline(limit + 1)
            return TOO_LONG
        line = raw.strip()
        if line:
            return line


def too_long_reply(limit=MAX_REQUEST_BYTES):
    return encode(error_reply(None, bad_args(f"the request is longer than {limit} bytes")))


def quit_reply(line):
    try:
        request = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(request, dict) or request.get("cmd") != "quit":
        return None
    request_id = request.get("id")
    if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
        request_id = None
    return encode({"id": request_id, "ok": True, "result": {"quit": True}})
