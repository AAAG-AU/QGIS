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

The script presents two options:

1. **Deploy to local QGIS profile** — Copies plugins into your local QGIS
   plugins directory. Automatically detects your operating system, locates
   the QGIS profiles directory, and lets you choose which profile and
   plugins to install. After deploying, restart QGIS and enable the
   plugin(s) via **Plugins > Manage and Install Plugins**.

2. **Upload to QGIS plugin repository** — Packages plugins as ZIP archives
   and uploads them to [plugins.qgis.org](https://plugins.qgis.org) for
   official repository approval. Requires an
   [OSGeo account](https://www.osgeo.org/community/getting-started-osgeo/).
   Validates that all required `metadata.txt` fields are populated before
   uploading. Credentials can be provided interactively or via
   `OSGEO_USERNAME` and `OSGEO_PASSWORD` environment variables.

### Supported Platforms

- Windows (`%APPDATA%\QGIS\QGIS3\profiles\`)
- Linux (`~/.local/share/QGIS/QGIS3/profiles/`)
- macOS (`~/Library/Application Support/QGIS/QGIS3/profiles/`)

## Requirements

- QGIS 3.0 or later
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
