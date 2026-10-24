---
title: CMDB Compliance
lang: en
locale: en-US
language_name: English
translation_key: bmforge-cmdb-compliance
---

Make every new project discoverable by the CMDB. Establish its application name, constants file, and installation path during setup.

This process follows CMDB's [App Discovery Settings](https://github.com/NadimGhaznavi/cmdb/blob/main/pages/app-discovery.md) and individual setting guides, reviewed against `/opt/dev/cmdb/pages` on 2026-10-21. CMDB's scanner requires only a literal `VERSION`; BMForge additionally requires the release metadata and installation root below. Follow [Runtime Configuration]({{ site.baseurl }}{% link pages/runtime-configuration.md %}) to make deployment settings discoverable through constants and production JSON.

## Name the Application

Choose one canonical application name matching `[A-Za-z_][A-Za-z0-9_]*`. Spaces and hyphens are unsupported by application discovery. Preserve the name's capitalization in the constants filename and use its lowercase form for the package and installation directory.

| Item | Convention | Example |
| --- | --- | --- |
| CMDB registered name | Canonical application name | `MyCount` |
| New repository name | Lowercase application name | `mycount` |
| Python package | Lowercase application name | `mycount` |
| Development checkout | `/opt/dev/<lowercase-name>` | `/opt/dev/mycount` |
| Installation root | `/opt/prod/<lowercase-name>` | `/opt/prod/mycount` |
| Constants file in the project | `<lowercase-name>/constants/D<Name>.py` | `mycount/constants/DMyCount.py` |
| Constants class | `D<Name>` | `DMyCount` |

Discovery derives the installed constants path from the registered name. It does not scan development checkouts or infer application names from repository URLs. Register the exact canonical name through the CMDB's **Add Application** action.

## Declare the Metadata

Copy the [constants template]({{ '/templates/project/constants/DProject.py' | relative_url }}) to the project's constants path. Rename its class and replace its placeholders. Keep `VERSION` and `CMDB_CODENAME` as independent, single-line literal string assignments; the release script updates those values while preserving annotations and surrounding text.

| Constant | Requirement |
| --- | --- |
| `VERSION` | Semantic version without a leading `v`; initially `0.0.0` |
| `CMDB_TYPE` | Broad classification; use `"application"` for new applications. CMDB accepts other literal classifications without enforcing a vocabulary |
| `CMDB_SUBTYPE` | Short description of the application's function |
| `CMDB_SUPPLIER` | Supplier name; the template defaults to `Nadim-Daniel` |
| `CMDB_CODENAME` | Initial development label; replaced by the release message when releasing |
| `BASE_DIR` | Literal `/opt/prod/<lowercase-name>` installation root |

The five version and CMDB strings must be nonempty, at most 255 characters, and contain no control characters. CMDB parses literal values at module or class scope without importing the file. Computed expressions, imported values, and environment lookups are unsuitable for these fields. Annotated assignments are supported.

CMDB trims the four optional metadata strings. Missing or invalid optional values leave existing matching-release metadata intact. Compatible observations fill missing fields; conflicting metadata selects or creates a separate release definition, protecting other hosts. A new version contains only metadata supplied by that observation. Preserve an existing project's intentional classification, including `"Application"`, unless changing it is part of the task; capitalization is not a discovery requirement.

## Declare Persistent Data

`CMDB_COMPONENTS` identifies persistent filesystem data for CMDB inventory and backups. It is **not** the architectural component-to-specification metadata described in [specification traceability]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}).

Use empty tuples when the project has no filesystem data components or databases. Otherwise declare literal `(name, value)` pairs, as in MyCount:

```python
CMDB_COMPONENTS = (("Marketing Screenshots", "pages/marketing"),)
CMDB_DATABASES = (("MyCount", "mycount"),)
```

Component paths may be relative to the installation root or absolute. Names are limited to 255 characters and paths to 4096; parent traversal and the relative path `.` are unsupported. These declarations make filesystem components available for CMDB inventory and backup scheduling. Discovery records the declaration without checking that the path exists.

Declarations accept literal tuples or lists of pairs, including annotated assignments. CMDB trims names and values, normalizes component paths, and records duplicate pairs once. Repeat scans reuse deployments; version changes preserve deployment identities. Changed paths create additional deployments, while removed, omitted, or invalid declarations retain old deployments. Removing a declaration is not an inventory cleanup operation.

Database pairs identify an application connection label and the exact, case-sensitive MariaDB catalog name, limited to 64 characters. CMDB creates new connections only for catalogs observed on that same host. Missing catalogs and failed reads retain prior connections.

Application discovery refreshes that host's MariaDB inventory through its default local socket, including during Add Application and Re-Scan Applications. The declaration supplies discovery references, without creating a database or configuring runtime credentials, remote hosts, or ports.

Directory and matched database targets appear in the Backups page's Application panel. Directory backups run as `cmdbagent`, which needs source read access and backup-destination write access. Test a backup separately from discovery: archives capture live files and do not guarantee application consistency. Database references share the catalog's existing backup policy and history. See CMDB's [backup guide](https://github.com/NadimGhaznavi/cmdb/blob/main/pages/backups.md) for execution prerequisites.

## Declare Network Listeners

Follow [Network Configuration]({{ site.baseurl }}{% link pages/network-configuration.md %}) for `CMDB_NETWORK`, runtime defaults, production overrides, and lifecycle verification. Declare every owned or managed listener, including internal and proxy listeners. Use an empty tuple for applications without listeners, such as BMForge.

## Application Health Monitoring

Follow [Application Health Checks]({{ site.baseurl }}{% link pages/health-checks.md %}) for running applications. CMDB should ask the **application** via its existing health interface and display green for success or red for failures and timeouts. The DB Server check happens inside the application using its configured database connection. CMDB must **not** open a direct MariaDB connection for this health check. Polling and status dashboard support in CMDB are planned separately; these specifications do not imply it already exists.

## Verify Discovery

Copy the [metadata checker]({{ '/templates/project/scripts/check-cmdb.py' | relative_url }}) to `scripts/check-cmdb.py`. From the project root, run it with the project's actual name and path:

```sh
python3 -B scripts/check-cmdb.py --name MyCount mycount/constants/DMyCount.py
```

For an installation, use `--root /opt/prod/mycount` with the same relative constants path. The local check validates the metadata, declared path syntax, and any network declaration; it does not check filesystem existence, runtime wiring, production JSON, CMDB connectivity, or remote access.

Deploy the constants file as readable Python source at the derived path, even if the executable is bundled. The `cmdbagent` account needs directory traversal and file read access. Keep credentials in separate protected configuration files.

Provide the required [Installation Scripts]({{ site.baseurl }}{% link pages/installation-scripts.md %}) to deploy, update, and remove the local installation consistently.

After installation, register the exact application name through Add Application and verify the host, version, type, subtype, supplier, codename, component paths, and database connections. Add Application queues discovery across inventoried hosts. Use Re-Scan Applications after subsequent deployments; it checks inventoried hosts without network or OS discovery and refreshes same-host MariaDB inventory first.

Check per-host Status Messages and the saved deployment, rather than relying only on `Scan complete`: individual reads may fail while the scan completes. Missing files, invalid versions, and host access failures retain previous deployments. Undeployed definitions and unused components are pruned after workloads; a new registration with no detected installation can disappear after its discovery attempt. Resolve installation or access problems and register again if needed. `CMDB_CODENAME` is stored as the release's `VERSION_CODENAME` tag. A release publication and a verified installation are separate outcomes.

---

[Back]({{ site.baseurl }}{% link index.md %})
