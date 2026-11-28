"""The bridge's error class and the constructors for bad arguments, not found, failed and forbidden."""

BAD_ARGS = "bad_args"
NOT_FOUND = "not_found"
FAILED = "failed"
FORBIDDEN = "forbidden"

ERROR_CODES = (BAD_ARGS, NOT_FOUND, FAILED, FORBIDDEN)


class BridgeError(Exception):
    def __init__(self, code, message):
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code}")
        super().__init__(message)
        self.code = code
        self.message = message


def bad_args(message):
    return BridgeError(BAD_ARGS, message)


def not_found(message):
    return BridgeError(NOT_FOUND, message)


def failed(message):
    return BridgeError(FAILED, message)


def forbidden(message):
    return BridgeError(FORBIDDEN, message)
