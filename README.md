# QGIS Python Plugins

Created by **Australis Asset Advisory Group**

A collection of QGIS plugins and utilities for GIS workflows.

## Plugins

| Plugin | Description |
|---|---|
| [Sort and Group Layers](plugins/sort_and_group_layers/) | Sort and group layers in the Layers panel by file path, name, file date, geometry type, feature count, file size, or source folder |

## Deploying Plugins

Run the deployment script to copy plugins into your local QGIS plugins
directory:

```bash
python deploy_plugins.py
```

The script automatically detects your operating system, locates the QGIS
profiles directory, scans the `plugins/` folder for valid plugins, and lets
you choose which ones to install. After deploying, restart QGIS and enable
the plugin(s) via **Plugins > Manage and Install Plugins**.

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
