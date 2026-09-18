import json
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DOCKER_SOCKET = "/var/run/docker.sock"
DIST_DIR = Path("/app/dist")
DOMAIN_SUFFIX = ".doudou.house"
HOST_PATTERN = re.compile(r"Host\(\s*`([^`]+)`\s*\)")
PATH_PATTERN = re.compile(r"PathPrefix\(\s*`([^`]+)`\s*\)")
ROUTER_LABEL = re.compile(r"^traefik\.http\.routers\.([^.]+)\.rule$")
ROUTER_MIDDLEWARES_LABEL = re.compile(
    r"^traefik\.http\.routers\.([^.]+)\.middlewares$"
)
PORTAL_AUTH_LABEL = re.compile(
    r"^doudou\.portal\.routers\.([^.]+)\.auth$"
)
PORTAL_DESCRIPTION_LABEL = re.compile(
    r"^doudou\.portal\.routers\.([^.]+)\.description$"
)
BASICAUTH_MIDDLEWARE_LABEL = re.compile(
    r"^traefik\.http\.middlewares\.([^.]+)\.basicauth\."
)


def docker_get(path):
    request = (
        f"GET {path} HTTP/1.0\r\n"
        "Host: docker\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(DOCKER_SOCKET)
        client.sendall(request)
        response = b""
        while chunk := client.recv(65536):
            response += chunk
    finally:
        client.close()
    _, body = response.split(b"\r\n\r\n", 1)
    return json.loads(body)


def display_name(container_name, router_name):
    name = router_name.replace("-", " ").replace("_", " ").strip()
    if name in {"home", "dashboard"} and container_name:
        name = container_name.replace("-", " ").replace("_", " ").title()
    return name.title()


def routes():
    routes = []
    basic_auth_middlewares = set()
    try:
        containers = docker_get("/containers/json?all=0")
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    for container in containers:
        labels = container.get("Labels", {})
        for label in labels:
            match = BASICAUTH_MIDDLEWARE_LABEL.match(label)
            if match:
                basic_auth_middlewares.add(match.group(1))

    for container in containers:
        labels = container.get("Labels", {})
        container_name = container.get("Names", [""])[0].lstrip("/")
        router_middlewares = {
            match.group(1): value
            for label, value in labels.items()
            if (match := ROUTER_MIDDLEWARES_LABEL.match(label))
        }
        router_auth = {
            match.group(1): value.strip().lower()
            for label, value in labels.items()
            if (match := PORTAL_AUTH_LABEL.match(label))
        }
        router_descriptions = {
            match.group(1): value.strip()
            for label, value in labels.items()
            if (match := PORTAL_DESCRIPTION_LABEL.match(label))
        }
        for label, rule in labels.items():
            match = ROUTER_LABEL.match(label)
            if not match or match.group(1) == "traefik-home":
                continue
            hosts = HOST_PATTERN.findall(rule)
            hosts = [
                host
                for host in hosts
                if host.lower().endswith(DOMAIN_SUFFIX)
                and host.lower() != DOMAIN_SUFFIX[1:]
            ]
            if not hosts:
                continue
            if match.group(1) == "home" and "doudou.house" in hosts:
                continue
            paths = PATH_PATTERN.findall(rule)
            path = next((value for value in paths if value.startswith("/")), "/")
            middlewares = router_middlewares.get(match.group(1), "").split(",")
            has_basic_auth = any(
                middleware.split("@", 1)[0].strip() in basic_auth_middlewares
                for middleware in middlewares
            )
            auth_methods = set()
            if router_auth.get(match.group(1)) == "integrated":
                auth_methods.add("integrated")
            if has_basic_auth:
                auth_methods.add("basic")
            if not auth_methods:
                auth_methods.add("public")
            for host in hosts:
                routes.append(
                    (
                        host,
                        display_name(container_name, match.group(1)),
                        router_descriptions.get(match.group(1), ""),
                        path,
                        tuple(sorted(auth_methods)),
                    )
                )
    unique_routes = sorted(set(routes), key=lambda route: (route[1], route[0]))
    return [
        {
            "host": host,
            "name": name,
            "description": description,
            "path": path,
            "auth": list(auth_methods),
            "url": f"https://{host}{path}",
        }
        for host, name, description, path, auth_methods in unique_routes
    ]


class PortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/routes":
            self.send_json(routes())
            return
        if self.path == "/":
            self.path = "/index.html"
        requested = (DIST_DIR / self.path.lstrip("/")).resolve()
        if DIST_DIR not in requested.parents or not requested.is_file():
            self.send_error(404)
            return
        payload = requested.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type(requested))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, value):
        payload = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string, *args):
        return


def content_type(path):
    return {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
    }.get(path.suffix, "text/html; charset=utf-8")


ThreadingHTTPServer(("0.0.0.0", 8080), PortalHandler).serve_forever()