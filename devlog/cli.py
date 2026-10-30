"""The installed dl command; local Git work stays on the client."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from devlog.activity.CommitTask import CommitRecordingError, CommitTask
from devlog.activity.ReleaseSync import ReleaseSync
from devlog.constants.DDevLog import DDevLog
from devlog.constants.DRelease import DRelease
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
    commands.add_parser(Method.STATUS, help=t(DText.STATUS_HELP))
    commands.add_parser("start", help=t(DText.START_HELP))
    commands.add_parser("pause", help=t(DText.PAUSE_HELP))
    commit = commands.add_parser("commit", help=t(DText.COMMIT_HELP))
    commit.add_argument("message", nargs="?", help=t(DText.MESSAGE_HELP))
    commit.add_argument("--record", metavar="SHA", help=t(DText.RECORD_HELP))
    publish = commands.add_parser("publish", help=t(DText.PUBLISH_HELP))
    publish.add_argument("arguments", nargs=argparse.REMAINDER)
    releases = commands.add_parser(DRelease.RELEASES, help=t(DText.RELEASES_HELP))
    release_commands = releases.add_subparsers(dest="release_command", required=True)
    sync = release_commands.add_parser("sync", help=t(DText.RELEASE_SYNC_HELP))
    sync.add_argument("--dry-run", action="store_true", help=t(DText.RELEASE_DRY_RUN_HELP))
    args = parser.parse_args(argv)
    if args.command == "commit" and bool(args.message) == bool(args.record):
        parser.error(t(DText.COMMIT_ARGUMENTS))
    try:
        local = LocalRepository() if args.command != Method.STATUS else None
        if args.command == "publish":
            script = local.release_script()
            if script is None:
                print(t(DText.PUBLISH_MISSING), file=sys.stderr)
                return 1
            arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            before = {release[DRelease.TAG_NAME] for release in local.release_tags()}
            status = subprocess.run(["bash", str(script), *arguments], cwd=local.root).returncode
            if status:
                return status
            try:
                releases = local.release_tags(exclude=before)
                if not releases:
                    return 0
                config = Configuration(args.config)
                client = ZMQClient(args.server or config.endpoint, timeout_ms=config.timeout_ms)
                inserted = ReleaseSync(local, client).run(releases)
                print(t(DText.RELEASE_SYNCED, inserted=inserted, checked=len(releases)))
                return 0
            except (TrackingError, OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                print(t(DText.RELEASE_RECOVERY), file=sys.stderr)
                raise
        if args.command == DRelease.RELEASES:
            releases = local.release_tags()
            if args.dry_run:
                print(json.dumps(releases, ensure_ascii=False, indent=2))
                return 0
        config = Configuration(args.config)
        client = ZMQClient(args.server or config.endpoint, timeout_ms=config.timeout_ms)
        if args.command == DRelease.RELEASES:
            inserted = ReleaseSync(local, client).run(releases)
            print(t(DText.RELEASE_SYNCED, inserted=inserted, checked=len(releases)))
            return 0
        if args.command == Method.STATUS:
            result = client.call(Method.STATUS, {})
            if result[DTracking.TASK_ID] is None:
                print(t(DText.NO_RUNNING_TASK))
            else:
                hours, minutes = divmod(int(result[DTracking.ACTIVE_SECONDS]) // 60, 60)
                print(t(DText.TASK_RUNNING, repository=result[DTracking.REPOSITORY].rsplit("/", 1)[-1],
                        task_id=result[DTracking.TASK_ID], duration=f"{hours:02}:{minutes:02}"))
            return 0
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
            values = dict(repository=local.repository.name, task_id=result[DTracking.TASK_ID])
            if args.command == Method.PAUSE and result[DTracking.PAUSED_AT] is not None:
                key = DText.PAUSED_ON
                values[DTracking.PAUSED_AT] = datetime.fromisoformat(result[DTracking.PAUSED_AT]).astimezone(
                    config.zone).strftime(DTracking.HISTORY_TIME_FORMAT)
            print(t(key, **values))
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
