import http.client
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote


OAUTH2_PROXY_HOST = os.environ["OAUTH2_PROXY_HOST"]


class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/auth":
            self.send_error(404)
            return

        headers = {
            "Host": "oauth2-proxy",
            "X-Forwarded-Proto": self.headers.get("X-Forwarded-Proto", "https"),
            "X-Forwarded-Host": self.headers.get("X-Forwarded-Host", ""),
            "X-Forwarded-Uri": self.headers.get("X-Forwarded-Uri", "/"),
        }
        if cookie := self.headers.get("Cookie"):
            headers["Cookie"] = cookie

        client = http.client.HTTPConnection("oauth2-proxy", 4180, timeout=5)
        try:
            client.request("GET", "/oauth2/auth", headers=headers)
            response = client.getresponse()
            response_headers = dict(response.getheaders())
            response.read()
        except OSError:
            self.send_error(503)
            return
        finally:
            client.close()

        if 200 <= response.status < 300:
            self.send_response(200)
            for name in ("X-Auth-Request-User", "X-Auth-Request-Email", "X-Auth-Request-Access-Token"):
                value = next(
                    (header_value for header_name, header_value in response_headers.items()
                     if header_name.lower() == name.lower()),
                    None,
                )
                if value:
                    self.send_header(name, value)
            self.end_headers()
            return

        proto = self.headers.get("X-Forwarded-Proto", "https")
        host = self.headers.get("X-Forwarded-Host", "")
        uri = self.headers.get("X-Forwarded-Uri", "/")
        destination = f"{proto}://{host}{uri}"
        location = f"https://{OAUTH2_PROXY_HOST}/oauth2/start?rd={quote(destination, safe='')}"
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, format_string, *args):
        return


ThreadingHTTPServer(("0.0.0.0", 8080), AuthHandler).serve_forever()