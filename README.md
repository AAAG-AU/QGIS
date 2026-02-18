# QGIS Python Plugins

Created by **Australis Asset Advisory Group**

A collection of QGIS plugins and utilities for GIS workflows.

## Plugins

| Plugin | Description |
|---|---|
| [Sort and Group Layers](plugins/sort_and_group_layers/) | Sort and group layers in the Layers panel by file path, name, file date, geometry type, feature count, file size, or source folder |

## Deploying Plugins

Run the deployment script to deploy plugins locally or upload them to the
official QGIS plugin repository:

```bash
python deploy_plugins.py
```

The script presents three options:

1. **Deploy to local QGIS profile** — Copies plugins into your local QGIS
   plugins directory. Automatically detects your operating system, locates
   the QGIS profiles directory, and lets you choose which profile and
   plugins to install. After deploying, restart QGIS and enable the
   plugin(s) via **Plugins > Manage and Install Plugins**.

2. **Upload to QGIS plugin repository** — Packages plugins as ZIP archives
   and uploads them to [plugins.qgis.org](https://plugins.qgis.org) via the
   REST API. Only works for plugins that have already been registered on the
   repository (see option 3 for new plugins). Requires an
   [OSGeo account](https://www.osgeo.org/community/getting-started-osgeo/).
   Validates that all required `metadata.txt` fields are populated before
   uploading. Credentials can be provided interactively or via
   `OSGEO_USERNAME` and `OSGEO_PASSWORD` environment variables.

3. **Prepare ZIP for first-time upload** — Creates a ready-to-upload ZIP
   file in the `dist/` folder at the repository root. New plugins must be
   uploaded manually through the web interface at
   [plugins.qgis.org/plugins/add/](https://plugins.qgis.org/plugins/add/)
   because the API returns 403 Forbidden for unregistered plugins. Once
   approved, future updates can use option 2.

### Supported Platforms

- Windows (`%APPDATA%\QGIS\QGIS3\profiles\`)
- Linux (`~/.local/share/QGIS/QGIS3/profiles/`)
- macOS (`~/Library/Application Support/QGIS/QGIS3/profiles/`)

## Requirements

- QGIS 3.0 or later (including QGIS 4.x with Qt6/PyQt6)
- Python 3 (bundled with QGIS)

## Repository Structure

```
├── deploy_plugins.py                       # Plugin deployment script
├── plugins/                                # All QGIS plugins
│   └── sort_and_group_layers/              # Sort and Group Layers plugin
│       ├── __init__.py
│       ├── sort_and_group_layers.py
│       ├── metadata.txt
│       └── README.md
└── .claude/                                # Claude Code configuration
    ├── CLAUDE.md
    ├── codebase-knowledge.md
    └── project-skills/
        ├── australis-author.md
        └── qgis-python-reference.md
```
