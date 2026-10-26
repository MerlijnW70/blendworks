import queue
import socket
import threading
import time

from .blendworks_bridge.errors import BridgeError
from .blendworks_bridge.handler import encode, error_reply
from .blendworks_bridge.transport import TOO_LONG, quit_reply, read_request, too_long_reply

WAIT_STEP = 0.25


def stopped_reply():
    return encode(error_reply(None, BridgeError("failed", "the bridge stopped")))


class Job:
    def __init__(self, line):
        self.line = line
        self.reply = None
        self.done = threading.Event()


class BridgeServer:
    def __init__(self, handler, port, host="127.0.0.1"):
        self.handler = handler
        self.host = host
        self.port = port
        self.jobs = queue.Queue()
        self.listener = None
        self.clients = set()
        self.lock = threading.Lock()
        self.running = False
        self.main_thread = threading.get_ident()

    def start(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind((self.host, self.port))
            listener.listen(4)
        except OSError:
            listener.close()
            raise
        self.port = listener.getsockname()[1]
        self.listener = listener
        self.running = True
        threading.Thread(target=self.accept_loop, args=(listener,), name="blendworks-accept", daemon=True).start()

    def stop(self):
        self.running = False
        if self.listener is not None:
            close_quietly(self.listener)
            self.listener = None
        with self.lock:
            clients = list(self.clients)
            self.clients.clear()
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            close_quietly(client)
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                break
            job.reply = stopped_reply()
            job.done.set()

    def pump(self, budget=0.05):
        if threading.get_ident() != self.main_thread:
            raise RuntimeError("the bridge queue must be pumped on Blender's main thread")
        deadline = time.monotonic() + budget
        handled = 0
        while time.monotonic() <= deadline or handled == 0:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                break
            try:
                job.reply = self.handler.handle_line(job.line)
            except Exception as error:
                job.reply = encode(error_reply(None, BridgeError("failed", f"{type(error).__name__}: {error}")))
            job.done.set()
            handled += 1
        return handled

    def accept_loop(self, listener):
        while self.running:
            try:
                client, _ = listener.accept()
            except OSError:
                return
            with self.lock:
                if not self.running:
                    close_quietly(client)
                    return
                self.clients.add(client)
            threading.Thread(target=self.serve_client, args=(client,), name="blendworks-client", daemon=True).start()

    def serve_client(self, client):
        try:
            with client.makefile("rb") as reader:
                while self.running:
                    line = read_request(reader)
                    if line is None:
                        return
                    if line is TOO_LONG:
                        send(client, too_long_reply())
                        continue
                    goodbye = quit_reply(line)
                    if goodbye is not None:
                        send(client, goodbye)
                        return
                    send(client, self.run_on_main_thread(line))
        except OSError:
            return
        finally:
            with self.lock:
                self.clients.discard(client)
            close_quietly(client)

    def run_on_main_thread(self, line):
        job = Job(line)
        self.jobs.put(job)
        while not job.done.wait(WAIT_STEP):
            if not self.running:
                return stopped_reply()
        return job.reply


def send(client, reply):
    client.sendall(reply.encode("utf-8") + b"\n")


def close_quietly(connection):
    try:
        connection.close()
    except OSError:
        pass
