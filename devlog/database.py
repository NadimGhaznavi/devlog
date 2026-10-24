"""Explicit, idempotent schema initialization; never performed by the server."""

import argparse
from pathlib import Path

from devlog.constants.DText import DText
from devlog.interface.Configuration import Configuration
from devlog.interface.DbMgr import DbMgr
from devlog.interface.Localizer import Localizer
from devlog.interface.TaskDb import TaskDb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    args = parser.parse_args()
    settings = Configuration(args.config)
    with DbMgr(**settings.database()) as manager:
        TaskDb(manager).initialize()
    print(Localizer(Path(__file__).parent / "locales").text(DText.SCHEMA_INITIALIZED))


if __name__ == "__main__":
    main()
