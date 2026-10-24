"""One systemd process owns the HTTP listener and ZMQ worker."""

import argparse
from http.server import ThreadingHTTPServer
import logging
import signal

from devlog.activity.Application import Application
from devlog.constants.DDevLog import DDevLog
from devlog.constants.DNetwork import DNetwork
from devlog.interface.Configuration import Configuration
from devlog.server.ReportHandler import ReportHandler
from devlog.zmq.ZMQServer import ZMQServer


BMFORGE_COMPONENT = {"id": "bmforge.http-server", "spec_version": "0.3.0"}


class ReportServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def service_actions(self):
        self.application.worker.check()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--version", action="version", version=DDevLog.VERSION)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Configuration(args.config)
    app = Application(config)

    def stop(signum, frame):
        raise KeyboardInterrupt

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    host, port = config.bindings["zmq"]
    try:
        with ZMQServer(f"tcp://{host}:{port}", app.handler, timeout_ms=config.timeout_ms) as worker:
            app.worker = worker
            with ReportServer(config.bindings["http"], ReportHandler) as server:
                server.application = app
                logging.info("DevLog %s ready: HTTP %s:%s, ZMQ %s", DDevLog.VERSION,
                             *config.bindings["http"], worker.endpoint)
                server.serve_forever(poll_interval=DNetwork.POLL_MS / 1000)
    except KeyboardInterrupt:
        logging.info("DevLog stopped")
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
