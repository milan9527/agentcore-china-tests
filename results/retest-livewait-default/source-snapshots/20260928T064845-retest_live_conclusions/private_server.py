"""Private-only HTTP/TLS/proxy fixture; no external network access is needed."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import json
import select
import socket
import ssl
import threading

CONFIG = json.load(open("/opt/cn-test/config.json"))
EVENTS = []


class Page(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/stats":
            data = json.dumps(EVENTS[-100:]).encode()
        else:
            EVENTS.append({"server": "page", "port": self.server.server_port, "path": self.path})
            data = b'<html><head><title>Private China test</title></head><body><h1>private-network-ok</h1><a id="download" download="persist.txt" href="data:text/plain,efs-persist-ok">Save</a></body></html>'
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def auth(self):
        expected = "Basic " + base64.b64encode(("cntest:" + CONFIG["password"]).encode()).decode()
        EVENTS.append({"server": "proxy", "port": self.server.server_port, "method": self.command, "path": self.path,
                       "credentialsPresent": "Proxy-Authorization" in self.headers,
                       "credentialsValid": self.headers.get("Proxy-Authorization") == expected})
        if self.headers.get("Proxy-Authorization") != expected:
            self.send_response(407)
            self.send_header("Proxy-Authenticate", 'Basic realm="cn-test"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        return True

    def do_GET(self):
        if not self.auth():
            return
        data = b"<html><title>Proxy test</title><h1>authenticated-proxy-ok</h1></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_CONNECT(self):
        if not self.auth():
            return
        host, port = self.path.rsplit(":", 1)
        # This fixture only tunnels to its own private TLS endpoint.
        if host != CONFIG["ip"] or port not in ["8443", "443"]:
            self.send_error(403)
            return
        upstream = socket.create_connection((host, int(port)), timeout=10)
        self.send_response(200, "Connection Established")
        self.end_headers()
        self.connection.settimeout(20)
        while True:
            readable, _, _ = select.select([self.connection, upstream], [], [], 20)
            if not readable:
                break
            for source in readable:
                data = source.recv(65536)
                if not data:
                    upstream.close()
                    return
                (upstream if source is self.connection else self.connection).sendall(data)


class NoAuthProxy(Proxy):
    def auth(self):
        EVENTS.append({"server": "proxy-no-auth", "port": self.server.server_port,
                       "method": self.command, "path": self.path})
        return True


def serve(port, handler, tls=False):
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain("/opt/cn-test/server.pem", "/opt/cn-test/server.key")
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


threading.Thread(target=serve, args=(8000, Page), daemon=True).start()
threading.Thread(target=serve, args=(80, Page), daemon=True).start()
threading.Thread(target=serve, args=(443, Page, True), daemon=True).start()
threading.Thread(target=serve, args=(3128, Proxy), daemon=True).start()
threading.Thread(target=serve, args=(3129, NoAuthProxy), daemon=True).start()
serve(8443, Page, True)
