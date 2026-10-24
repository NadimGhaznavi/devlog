"""The installed dl command; local Git work stays on the client."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from devlog.activity.CommitTask import CommitRecordingError, CommitTask
from devlog.constants.DDevLog import DDevLog
from devlog.constants.DText import DText
from devlog.constants.DTracking import DTracking, Method
from devlog.entity.TrackingError import TrackingError
from devlog.interface.Configuration import Configuration
from devlog.interface.Localizer import Localizer
from devlog.interface.LocalRepository import LocalRepository
from devlog.interface.ZMQClient import ZMQClient


def main(argv=None):
    localizer = Localizer(Path(__file__).parent / "locales")
    language_parser = argparse.ArgumentParser(add_help=False)
    language_parser.add_argument("--lang")
    early, _ = language_parser.parse_known_args(argv)
    preference = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "en")
    language = localizer.select(explicit=early.lang or preference.split(".")[0])
    t = lambda key, **values: localizer.text(key, locale=language, **values)
    parser = argparse.ArgumentParser(prog="dl", description=t(DText.CLI_DESCRIPTION))
    parser.add_argument("--lang", help=t(DText.LANG_HELP))
    parser.add_argument("--version", action="version", version=DDevLog.VERSION)
    parser.add_argument("--config", help=t(DText.CONFIG_HELP))
    parser.add_argument("--server", help=t(DText.SERVER_HELP))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("start", help=t(DText.START_HELP))
    commands.add_parser("pause", help=t(DText.PAUSE_HELP))
    commit = commands.add_parser("commit", help=t(DText.COMMIT_HELP))
    commit.add_argument("message", nargs="?", help=t(DText.MESSAGE_HELP))
    commit.add_argument("--record", metavar="SHA", help=t(DText.RECORD_HELP))
    publish = commands.add_parser("publish", help=t(DText.PUBLISH_HELP))
    publish.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "commit" and bool(args.message) == bool(args.record):
        parser.error(t(DText.COMMIT_ARGUMENTS))
    try:
        local = LocalRepository()
        if args.command == "publish":
            script = local.release_script()
            if script is None:
                print(t(DText.PUBLISH_MISSING), file=sys.stderr)
                return 1
            arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            return subprocess.run(["bash", str(script), *arguments], cwd=local.root).returncode
        config = Configuration(args.config)
        client = ZMQClient(args.server or config.endpoint, timeout_ms=config.timeout_ms)
        repository = local.repository.identity
        if args.command == "commit":
            def show_completed(result):
                print(t(DText.COMMITTED, repository=local.repository.name,
                        task_id=result["task_id"], commit_sha=result["commit_sha"]), flush=True)
            outputs = CommitTask(local, client).run(args.message, record=args.record, completed=show_completed)
            for output in outputs:
                if output:
                    print(output, end="" if output.endswith("\n") else "\n")
        else:
            result = client.call(Method(args.command), {DTracking.REPOSITORY: repository})
            key = DText.STARTED if args.command == "start" else DText.PAUSED
            print(t(key, repository=local.repository.name, task_id=result["task_id"]))
        return 0
    except CommitRecordingError as error:
        print(t(error.key, commit_sha=error.commit_sha), file=sys.stderr)
    except TrackingError as error:
        print(t(error.key), file=sys.stderr)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(t(DText.ERROR, detail=str(error)), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
