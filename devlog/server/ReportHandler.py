from datetime import datetime
from http.server import BaseHTTPRequestHandler
import json
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from devlog.constants.DDevLog import DDevLog
from devlog.constants.DNetwork import DNetwork
from devlog.constants.DText import DText
from devlog.constants.DTracking import DTracking
from devlog.entity.ServiceUnavailable import ServiceUnavailable
from devlog.entity.TrackingError import TrackingError


BMFORGE_COMPONENT = {"id": "bmforge.visualization", "spec_version": "0.1.0"}
DIRECTORY = Path(__file__).parent
TEMPLATES = Environment(loader=FileSystemLoader(DIRECTORY / "templates"),
                        autoescape=select_autoescape(("html",)), undefined=StrictUndefined)
TEMPLATES.filters["history_date"] = lambda value: datetime.fromisoformat(value).strftime(DTracking.TASK_DATE_FORMAT)
# Recover database timestamp precision before dropping fractional seconds; float
# hours can otherwise turn an exact minute into 59.99999999999999 seconds.
TEMPLATES.filters["elapsed_seconds"] = lambda hours: int(round(hours * 3600, 6))
TEMPLATES.globals["task_seconds_limit"] = DTracking.TASK_TOTAL_SECONDS_LIMIT
STATIC = {"/static/style.css": ("style.css", "text/css; charset=utf-8"),
          "/static/report.js": ("report.js", "text/javascript; charset=utf-8"),
          "/static/timing.js": ("timing.js", "text/javascript; charset=utf-8")}


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
    def task_route(path, *, pause=False, timing=False):
        parts = path.split("/")
        action = "timing" if timing else "pause" if pause else None
        if (len(parts) == (4 if action else 3) and parts[1] == "tasks"
                and parts[2].isascii() and parts[2].isdecimal()
                and (not action or parts[3] == action)):
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
            elif path == "/daily":
                for key in ("repository", "start", "end"):
                    values.pop(key, None)
            return path + "?" + urlencode(values)
        return build

    def render(self, template, locale, *, status=200, **values):
        app = self.server.application
        body = TEMPLATES.get_template(template).render(
            t=lambda key, **fields: app.localizer.text(key, locale=locale, **fields),
            text=DText, locale=locale, languages=app.localizer.languages, version=DDevLog.VERSION,
            last_updated=datetime.now(app.config.zone).strftime(DTracking.HISTORY_TIME_FORMAT),
            **values,
        ).encode("utf-8")
        self.respond(status, body, "text/html; charset=utf-8")

    def do_POST(self):
        app = self.server.application
        locale = app.localizer.default_language
        timing = False
        try:
            parsed = urlsplit(self.path)
            timing_id = self.task_route(parsed.path, timing=True)
            timing = timing_id is not None
            task_id = timing_id if timing else self.task_route(parsed.path, pause=True)
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
            content_type = "application/json" if timing else "application/x-www-form-urlencoded"
            if (self.headers.get_content_type() != content_type
                    or self.headers.get("Transfer-Encoding")
                    or len(self.headers.get_all("Content-Length", [])) != 1):
                raise ValueError("Invalid form encoding")
            length = int(self.headers["Content-Length"])
            if not 0 < length <= (DNetwork.MAX_TIMING_BYTES if timing else DNetwork.MAX_FORM_BYTES):
                raise ValueError("Invalid form length")
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete form")
            if timing:
                def unique_object(pairs):
                    result = dict(pairs)
                    if len(result) != len(pairs):
                        raise ValueError("Repeated JSON field")
                    return result

                payload = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object)
                app.save_timing(task_id, payload)
                self.respond(200, json.dumps({"saved": True, "task": app.task_detail(task_id)}).encode("utf-8"),
                             "application/json; charset=utf-8")
                return
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
            status = (404 if error.key == DText.NOT_FOUND else 409 if error.key in {
                DText.PAUSE_CONFLICT, DText.TIMING_CONFLICT, DText.TIMING_OVERLAP} else 400)
            self.problem(status, error.key, locale, code=timing)
        except (ValueError, UnicodeError, TimeoutError, RecursionError):
            self.problem(400, DText.BAD_TIMING if timing else DText.BAD_EDIT, locale)
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
            elif parsed.path in ("/tasks", "/daily"):
                daily = parsed.path == "/daily"
                allowed = {"day", "repository", "lang"} if daily else {"repository", "start", "end", "day", "lang"}
                if set(query) - allowed:
                    raise ValueError("Unknown task filter")
                filters = {key: value for key, value in query.items() if key != "lang"}
                if daily:
                    filters["day"] = query.get("day") or datetime.now(app.config.zone).date().isoformat()
                    report = app.daily_task_list(**filters)
                    if report["repository"]:
                        filters["repository"] = report["repository"]
                    else:
                        filters.pop("repository", None)
                    link = self.link(filters, locale)
                else:
                    report = app.task_list(**filters)
                self.render("history.html", locale, report=report, task=None, link=link, saved=False, daily=daily)
            elif (task_id := self.task_route(parsed.path, timing=True)) is not None:
                if set(query) - {"repository", "start", "end", "day", "lang"}:
                    raise ValueError("Unknown task field")
                self.respond(200, json.dumps({"task": app.task_detail(task_id)}).encode("utf-8"),
                             "application/json; charset=utf-8")
            elif (task_id := self.task_route(parsed.path)) is not None:
                if set(query) - {"repository", "start", "end", "day", "lang", "saved"}:
                    raise ValueError("Unknown task field")
                self.render("history.html", locale, report=None, task=app.task_detail(task_id),
                            link=link, saved=query.get("saved", ""))
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

    def problem(self, status, key, locale, *, code=False):
        body = {"error": self.server.application.localizer.text(key, locale=locale)}
        if code:
            body["code"] = str(key)
        self.respond(status, json.dumps(body).encode(), "application/json")

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
