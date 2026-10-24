from http.server import BaseHTTPRequestHandler
import json
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from devlog.constants.DDevLog import DDevLog
from devlog.constants.DNetwork import DNetwork
from devlog.constants.DText import DText
from devlog.entity.ServiceUnavailable import ServiceUnavailable


BMFORGE_COMPONENT = {"id": "bmforge.visualization", "spec_version": "0.1.0"}
DIRECTORY = Path(__file__).parent
TEMPLATES = Environment(loader=FileSystemLoader(DIRECTORY / "templates"),
                        autoescape=select_autoescape(("html",)), undefined=StrictUndefined)
STATIC = {"/static/style.css": ("style.css", "text/css; charset=utf-8"),
          "/static/report.js": ("report.js", "text/javascript; charset=utf-8")}


class ReportHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(DNetwork.HTTP_TIMEOUT)

    def do_GET(self):
        self.serve()

    def do_HEAD(self):
        self.serve()

    def serve(self):
        app = self.server.application
        locale = app.localizer.default_language
        try:
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=DNetwork.MAX_QUERY_FIELDS)
            if any(len(values) != 1 for values in query.values()):
                raise ValueError("Repeated query field")
            locale = app.localizer.select(explicit=query.get("lang", [None])[0],
                                          accept_language=self.headers.get("Accept-Language", ""))
            t = lambda key, **values: app.localizer.text(key, locale=locale, **values)
            if parsed.path == "/health":
                health = app.health()
                self.respond(200 if health["status"] == "ok" else 503, json.dumps(health).encode(), "application/json")
            elif parsed.path in ("/", "/api/report"):
                if set(query) - {"repository", "start", "end", "lang"}:
                    raise ValueError("Unknown report field")
                report = app.report(**{key: query[key][0] for key in ("repository", "start", "end") if key in query})
                if parsed.path == "/api/report":
                    self.respond(200, json.dumps(report, allow_nan=False).encode(), "application/json")
                else:
                    body = TEMPLATES.get_template("report.html").render(
                        report=report, t=t, text=DText, locale=locale,
                        languages=app.localizer.languages, version=DDevLog.VERSION,
                    ).encode("utf-8")
                    self.respond(200, body, "text/html; charset=utf-8")
            elif parsed.path in STATIC:
                filename, content_type = STATIC[parsed.path]
                self.respond(200, (DIRECTORY / "static" / filename).read_bytes(), content_type)
            else:
                self.problem(404, DText.NOT_FOUND, locale)
        except ValueError:
            self.problem(400, DText.BAD_REPORT, locale)
        except ServiceUnavailable:
            self.problem(503, DText.UNAVAILABLE, locale)
        except Exception:
            # Unexpected defects are logged and returned as failure, never as an empty report.
            logging.exception("DevLog HTTP request failed")
            self.problem(500, DText.UNAVAILABLE, locale)

    def problem(self, status, key, locale):
        self.respond(status, json.dumps({"error": self.server.application.localizer.text(key, locale=locale)}).encode(), "application/json")

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
