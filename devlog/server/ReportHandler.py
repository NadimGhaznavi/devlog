from http.server import BaseHTTPRequestHandler
import json
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from devlog.constants.DDevLog import DDevLog
from devlog.constants.DNetwork import DNetwork
from devlog.constants.DText import DText
from devlog.entity.ServiceUnavailable import ServiceUnavailable
from devlog.entity.TrackingError import TrackingError


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

    def query(self, raw):
        query = parse_qs(raw, keep_blank_values=True, max_num_fields=DNetwork.MAX_QUERY_FIELDS)
        if any(len(values) != 1 for values in query.values()):
            raise ValueError("Repeated query field")
        return {key: values[0] for key, values in query.items()}

    def locale(self, query):
        return self.server.application.localizer.select(
            explicit=query.get("lang"), accept_language=self.headers.get("Accept-Language", ""))

    @staticmethod
    def task_route(path, *, pause=False):
        parts = path.split("/")
        if (len(parts) == (4 if pause else 3) and parts[1] == "tasks"
                and parts[2].isascii() and parts[2].isdecimal()
                and (not pause or parts[3] == "pause")):
            task_id = int(parts[2])
            if 0 < task_id < 2 ** 64:
                return task_id
        return None

    def link(self, query, locale):
        def build(path, **updates):
            values = {key: value for key, value in query.items()
                      if key in {"repository", "start", "end", "day"}}
            values.update(lang=locale, **updates)
            if path == "/":
                values.pop("day", None)
                values.pop("repository", None)
            return path + "?" + urlencode(values)
        return build

    def render(self, template, locale, *, status=200, **values):
        app = self.server.application
        body = TEMPLATES.get_template(template).render(
            t=lambda key, **fields: app.localizer.text(key, locale=locale, **fields),
            text=DText, locale=locale, languages=app.localizer.languages, version=DDevLog.VERSION,
            **values,
        ).encode("utf-8")
        self.respond(status, body, "text/html; charset=utf-8")

    def do_POST(self):
        app = self.server.application
        locale = app.localizer.default_language
        try:
            parsed = urlsplit(self.path)
            task_id = self.task_route(parsed.path, pause=True)
            if task_id is None:
                self.send_error(501, "Unsupported method")
                return
            query = self.query(parsed.query)
            locale = self.locale(query)
            if set(query) - {"repository", "start", "end", "day", "lang"}:
                raise ValueError("Unknown navigation field")
            source = self.headers.get("Origin") or self.headers.get("Referer", "")
            origin = urlsplit(source)
            if (origin.scheme not in ("http", "https") or origin.netloc != self.headers.get("Host")
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"):
                self.problem(403, DText.EDIT_ORIGIN, locale)
                return
            if (self.headers.get_content_type() != "application/x-www-form-urlencoded"
                    or self.headers.get("Transfer-Encoding")
                    or len(self.headers.get_all("Content-Length", [])) != 1):
                raise ValueError("Invalid form encoding")
            length = int(self.headers["Content-Length"])
            if not 0 < length <= DNetwork.MAX_FORM_BYTES:
                raise ValueError("Invalid form length")
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete form")
            payload = self.query(body.decode("utf-8"))
            try:
                app.insert_pause(task_id, payload)
            except TrackingError as error:
                self.render("history.html", locale, status=409 if error.key == DText.PAUSE_CONFLICT else 400,
                            report=None, task=app.task_detail(task_id), link=self.link(query, locale),
                            saved=False, form_error=error.key, form_values=payload)
                return
            self.send_response(303)
            self.send_header("Location", self.link(query, locale)(f"/tasks/{task_id}", saved="1"))
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
        except TrackingError as error:
            self.problem(409 if error.key == DText.PAUSE_CONFLICT else 400, error.key, locale)
        except (ValueError, UnicodeError, TimeoutError):
            self.problem(400, DText.BAD_EDIT, locale)
        except ServiceUnavailable:
            self.problem(503, DText.UNAVAILABLE, locale)
        except Exception:
            logging.exception("DevLog task correction failed")
            self.problem(500, DText.UNAVAILABLE, locale)

    def serve(self):
        app = self.server.application
        locale = app.localizer.default_language
        try:
            parsed = urlsplit(self.path)
            query = self.query(parsed.query)
            locale = self.locale(query)
            link = self.link(query, locale)
            if parsed.path == "/health":
                health = app.health()
                self.respond(200 if health["status"] == "ok" else 503, json.dumps(health).encode(), "application/json")
            elif parsed.path in ("/", "/api/report"):
                if set(query) - {"repository", "start", "end", "lang"}:
                    raise ValueError("Unknown report field")
                report = app.report(**{key: query[key] for key in ("repository", "start", "end") if key in query})
                if parsed.path == "/api/report":
                    self.respond(200, json.dumps(report, allow_nan=False).encode(), "application/json")
                else:
                    self.render("report.html", locale, report=report, link=link)
            elif parsed.path == "/tasks":
                if set(query) - {"repository", "start", "end", "day", "lang"}:
                    raise ValueError("Unknown task filter")
                report = app.task_list(**{key: value for key, value in query.items() if key != "lang"})
                self.render("history.html", locale, report=report, task=None, link=link, saved=False)
            elif (task_id := self.task_route(parsed.path)) is not None:
                if set(query) - {"repository", "start", "end", "day", "lang", "saved"}:
                    raise ValueError("Unknown task field")
                self.render("history.html", locale, report=None, task=app.task_detail(task_id),
                            link=link, saved=query.get("saved") == "1")
            elif parsed.path in STATIC:
                filename, content_type = STATIC[parsed.path]
                self.respond(200, (DIRECTORY / "static" / filename).read_bytes(), content_type)
            else:
                self.problem(404, DText.NOT_FOUND, locale)
        except TrackingError as error:
            self.problem(404 if error.key == DText.NOT_FOUND else 400, error.key, locale)
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
