"""The headless Blender session: reads requests from the protocol stream and serves them."""

import argparse
import os
import sys


def take_protocol_stream():
    sys.stdout.flush()
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", newline="\n")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    return protocol


def parse_arguments(argv):
    own = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(prog="session.py", description="Blendworks headless bridge session")
    parser.add_argument("--workspace", default=os.path.join(os.getcwd(), "workspace"))
    parser.add_argument("--allow-python", action="store_true")
    return parser.parse_args(own)


def read_in_background(reader):
    import queue
    import threading

    from blendworks_bridge.transport import read_request

    lines = queue.Queue()

    def pump():
        while True:
            line = read_request(reader)
            lines.put(line)
            if line is None:
                return

    threading.Thread(target=pump, name="blendworks-requests", daemon=True).start()
    return lines


def next_request(handler, lines):
    import queue

    while True:
        wait = handler.idle_wait()
        try:
            return lines.get(timeout=wait) if wait is not None else lines.get()
        except queue.Empty:
            handler.idle()


def serve(handler, protocol, reader):
    from blendworks_bridge.transport import TOO_LONG, quit_reply, too_long_reply

    def send(text):
        protocol.write(text + "\n")
        protocol.flush()

    lines = read_in_background(reader)
    while True:
        line = next_request(handler, lines)
        if line is None:
            return
        if line is TOO_LONG:
            send(too_long_reply())
            continue
        goodbye = quit_reply(line)
        if goodbye is not None:
            send(goodbye)
            return
        send(handler.handle_line(line))


def main():
    protocol = take_protocol_stream()
    arguments = parse_arguments(sys.argv)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    import bpy
    from blendworks_bridge import Handler
    from blendworks_bridge.commands.scene import reset_scene

    handler = Handler(arguments.workspace, allow_python=arguments.allow_python, desktop=False)
    reset_scene(bpy.context.scene)
    print(f"blendworks session ready, workspace {handler.workspace.root}", file=sys.stderr, flush=True)
    try:
        serve(handler, protocol, sys.stdin.buffer)
    except KeyboardInterrupt:
        pass
    finally:
        protocol.close()


main()
