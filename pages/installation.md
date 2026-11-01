---
title: "Installation"
lang: en
locale: en-US
language_name: English
translation_key: devlog-installation
---

DevLog has a command-line client for each machine where you work and a server
that stores tasks and serves reports. Both can run on the same machine.

## Requirements

Requires Python 3.11+ and Git. The server also needs Linux/systemd and local
MariaDB with administrator socket access. Use a release checkout and run the
commands below from its root directory.

## Install

On the server machine:

```bash
sudo ./scripts/install-server.sh
```

The server installation includes the client. On each additional client machine,
replace `SERVER_HOST` with the server's hostname or IP address:

```bash
sudo ./scripts/install.sh -server SERVER_HOST
```

Add `/opt/prod/devlog/bin` to your PATH. For example, add this line to your shell
profile and open a new shell:

```bash
export PATH="/opt/prod/devlog/bin:$PATH"
```

## Configuration

Configuration is in `/opt/prod/devlog/conf/devlog.json`. The client connects to
the server on port **19701**; reports are available on port **19700**. Keep both
listeners on your trusted network.

The supplied report timezone is `America/Toronto`. Set `timezone` in the server
configuration to your IANA timezone and restart `devlog.service` after changing
server settings. Database credentials are stored separately in
`/opt/prod/devlog/conf/database.env`.

## Check and upgrade

Append `--check` to an installation, upgrade or uninstall command to check its
prerequisites without changing the host. For example:

```bash
sudo ./scripts/upgrade.sh --check
```

From the new release checkout, upgrade either role with:

```bash
sudo ./scripts/upgrade.sh
```

Upgrades preserve the installed role, configuration and recorded data.

## Uninstall

```bash
sudo ./scripts/uninstall.sh
```

Server uninstall deletes tracked data. Saved database credentials are retained
in `conf/database.env` for a later installation.

---

[Documentation index]({{ site.baseurl }}{% link index.md %})
