# DevLog

Track time spent working in GitHub repositories, from the command line to daily reports.

[Project website and documentation](https://devlog.osoyalce.com/)

## Development

Create a persistent development environment with the client, server and test
dependencies, then run tests from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[server,dev]'
.venv/bin/python -m pytest
```

The `.venv` directory is ignored by Git. Database integration tests require
`DEVLOG_TEST_DB_SOCKET` pointing to an explicitly disposable MariaDB instance;
otherwise those tests are skipped. Never point it at a production database.
