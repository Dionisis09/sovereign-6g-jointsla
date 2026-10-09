"""Small JSON HTTP boundary with bounded bodies and explicit failures."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    application = None

    def setup(self):
        super().setup()
        self.connection.settimeout(15)  # bound headers, bodies and response writes

    def handle_request(self):
        tracked = self.command == 'POST' and self.path == '/infer'
        if tracked: self.server.track(1)
        try:
            body = None
            if self.command == 'POST':
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1_500_000:
                    raise ValueError('JSON body must be 1–1500000 bytes')
                self.connection.settimeout(15)
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Expected a JSON object')
            status, payload = self.application.dispatch(self.command, self.path, body)
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; version=0.0.4' if isinstance(payload, bytes) else 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()
        except (ValueError, TypeError, KeyError) as error:
            self.send_error(400, str(error))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self.send_error(500, 'Internal inference/control error; inspect server log')
            import traceback
            traceback.print_exc()
        finally:
            if tracked: self.server.track(-1)

    do_GET = handle_request
    do_POST = handle_request

    def log_message(self, *_):
        pass

class RejectionHandler(BaseHTTPRequestHandler):
    """Consume a bounded request before 503, avoiding unread-body TCP resets."""
    def setup(self):
        super().setup()
        self.connection.settimeout(1)

    def reject(self):
        try:
            app=self.server.RequestHandlerClass.application
            if self.command=='GET' and self.path in ('/ready','/live','/metrics','/state'):
                status,payload=app.dispatch('GET',self.path)
                raw=payload if isinstance(payload,bytes) else json.dumps(payload).encode()
                content_type='text/plain; version=0.0.4' if isinstance(payload,bytes) else 'application/json'
            else:
                app.metrics.http_rejections.inc()
                if self.command=='POST':
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<=length<=1_500_000: return
                    self.rfile.read(length)
                status,raw,content_type=503,b'{"error":"HTTP handler capacity exceeded"}','application/json'
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Connection','close')
            self.end_headers();self.wfile.write(raw);self.wfile.flush()
        except (OSError,ValueError): pass
        finally: self.close_connection=True

    do_GET=reject
    do_POST=reject
    def log_message(self,*_): pass


class ServingHTTPServer(ThreadingHTTPServer):
    """Bound handlers and retain in-flight HTTP writes during shutdown."""
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(128)
        self.rejection_slots = threading.BoundedSemaphore(8)
        self.connections = 0
        self.connection_lock = threading.Lock()
        self.terminating = threading.Event()
        super().__init__(*args, **kwargs)

    def track(self, delta):
        with self.connection_lock:
            self.connections += delta
            self.RequestHandlerClass.application.metrics.http_inflight.set(self.connections)

    def pending(self):
        with self.connection_lock: return self.connections

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            if not self.rejection_slots.acquire(blocking=False):
                self.RequestHandlerClass.application.metrics.http_rejections.inc()
                self.shutdown_request(request)
                return
            def reject():
                try: RejectionHandler(request,address,self)
                finally:
                    self.shutdown_request(request)
                    self.rejection_slots.release()
            threading.Thread(target=reject,daemon=True).start()
            return
        try: super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.slots.release()


def serve(application, host, port):
    handler = type('BoundHandler', (Handler,), {'application': application})
    return ServingHTTPServer((host, port), handler)


def shutdown_gracefully(server, application, grace=60):
    """Withdraw admission, then finish admitted work AND HTTP response writes."""
    with server.connection_lock:
        if server.terminating.is_set(): return
        server.terminating.set()
    cutoff = time.monotonic() + grace
    application.begin_drain()
    application.metrics.draining.set(1)
    while time.monotonic() < cutoff and (application.active_requests() or server.pending()):
        time.sleep(.02)
    server.shutdown()


def run_server(application, host, port):
    import signal
    server = serve(application, host, port)
    def terminate(*_):
        # Do not acquire locks in a signal handler: it can interrupt their holder.
        threading.Thread(target=shutdown_gracefully, args=(server, application), daemon=True).start()
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try: server.serve_forever()
    finally: server.server_close()


def request_parameters(body):
    import math
    tier = body.get('tier', 'Gold')
    deadline = float(body.get('deadline_ms', 200))
    if tier not in ('Gold', 'Silver', 'Bronze') or not math.isfinite(deadline) or not 1 <= deadline <= 60000:
        raise ValueError('Use Gold/Silver/Bronze and deadline_ms between 1 and 60000')
    return tier, deadline
