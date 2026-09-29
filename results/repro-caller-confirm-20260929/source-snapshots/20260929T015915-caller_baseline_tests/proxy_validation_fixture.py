"""Private test origin/proxy with real forwarding and credential-free audit logs."""
import base64
import datetime as dt
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import select
import socket
import ssl
import threading
from urllib.parse import urlsplit

CONFIG = json.loads(Path("/opt/proxy-validation/config.json").read_text())
EVENTS = []
LOCK = threading.Lock()
HTTP_PORTS = [80, 8000, 8081]
TLS_PORTS = [443, 8443]
PROXY_PORTS = [3128, 3129, 8080]


def event(**fields):
    with LOCK:
        row = {"seq": len(EVENTS) + 1, "time": dt.datetime.now(dt.timezone.utc).isoformat(),
               "role": CONFIG["role"], **fields}
        EVENTS.append(row)
        with Path("/var/log/proxy-validation-events.jsonl").open("a") as stream:
            stream.write(json.dumps(row) + "\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_GET(self):
        if self.path == "/stats":
            with LOCK:
                snapshot = list(EVENTS)
            self.respond(snapshot)
            return
        if self.path == "/health":
            self.respond({"role": CONFIG["role"], "ready": True})
            return
        value = {"marker": "proxy-validation-origin", "path": self.path,
                 "port": self.server.server_port, "peerIp": self.client_address[0],
                 "host": self.headers.get("Host"), "forwardedBy": self.headers.get("X-Test-Proxy")}
        event(event="origin_request", **value)
        self.respond(value)


class Proxy(Handler):
    def authenticate(self):
        actual = self.headers.get("Proxy-Authorization", "")
        expected = "Basic " + base64.b64encode(("cntest:" + CONFIG["password"]).encode()).decode()
        valid = actual == expected
        required = self.server.server_port != 3129
        event(event="proxy_request", listener=self.server.server_port, method=self.command,
              path=self.path, credentialsPresent=bool(actual), credentialsValid=valid,
              authRequired=required, authAccepted=valid or not required)
        if required and not valid:
            self.send_response(407)
            self.send_header("Proxy-Authenticate", 'Basic realm="proxy-validation"')
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            return False
        return True

    def allowed(self, host, port):
        return host in CONFIG["targetHosts"] and port in HTTP_PORTS + TLS_PORTS

    def do_GET(self):
        if not self.authenticate():
            return
        parsed = urlsplit(self.path)
        port = parsed.port or 80
        if parsed.scheme != "http" or not self.allowed(parsed.hostname, port):
            self.respond({"error": "fixture_destination_denied"}, 403)
            return
        connection = http.client.HTTPConnection(CONFIG["targetIp"], port, timeout=10)
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("GET", path, headers={"Host": parsed.netloc,
                "X-Test-Proxy": str(self.server.server_port), "Connection": "close"})
            response = connection.getresponse()
            value = json.loads(response.read())
            event(event="proxy_forwarded", listener=self.server.server_port, path=self.path,
                  targetIp=CONFIG["targetIp"], targetPort=port, upstreamStatus=response.status)
            self.respond(value, response.status)
        except Exception as error:
            event(event="proxy_upstream_error", errorType=type(error).__name__, path=self.path)
            self.respond({"error": type(error).__name__}, 502)
        finally:
            connection.close()

    def do_CONNECT(self):
        if not self.authenticate():
            return
        host, port_text = self.path.rsplit(":", 1)
        port = int(port_text)
        if not self.allowed(host, port):
            self.respond({"error": "fixture_destination_denied"}, 403)
            return
        upstream = socket.create_connection((CONFIG["targetIp"], port), timeout=10)
        event(event="connect_established", listener=self.server.server_port,
              destination=self.path, targetIp=CONFIG["targetIp"], targetPort=port)
        self.send_response(200, "Connection Established")
        self.end_headers()
        self.close_connection = True
        try:
            while True:
                ready, _, _ = select.select([self.connection, upstream], [], [], 20)
                if not ready:
                    break
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.connection else self.connection).sendall(data)
        finally:
            upstream.close()


def serve(port, handler, tls=False):
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain("/opt/proxy-validation/server.pem", "/opt/proxy-validation/server.key")
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    ports = ([(p, Handler, False) for p in HTTP_PORTS] +
             [(p, Handler, True) for p in TLS_PORTS] if CONFIG["role"] == "origin"
             else [(80, Handler, False)] + [(p, Proxy, False) for p in PROXY_PORTS])
    for args in ports[:-1]:
        threading.Thread(target=serve, args=args, daemon=True).start()
    serve(*ports[-1])
