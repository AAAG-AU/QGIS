# QGIS Python Plugins

Created by **Australis Asset Advisory Group**

A collection of QGIS plugins and utilities for GIS workflows.

## Plugins

| Plugin | Description |
|---|---|
| [sort_layers](sort_layers/) | Sort layers in the Layers panel by file path, name, file date, geometry type, feature count, or file size |

## Deploying Plugins

Run the deployment script to copy plugins into your local QGIS plugins
directory:

```bash
python deploy_plugins.py
```

The script automatically detects your operating system, locates the QGIS
profiles directory, and lets you choose which plugins to install. After
deploying, restart QGIS and enable the plugin(s) via **Plugins > Manage and
Install Plugins**.

### Supported Platforms

- Windows (`%APPDATA%\QGIS\QGIS3\profiles\`)
- Linux (`~/.local/share/QGIS/QGIS3/profiles/`)
- macOS (`~/Library/Application Support/QGIS/QGIS3/profiles/`)

## Requirements

- QGIS 3.0 or later
- Python 3 (bundled with QGIS)

## Repository Structure

```
├── deploy_plugins.py          # Plugin deployment script
├── sort_layers/               # Sort Layers plugin
│   ├── __init__.py
│   ├── sort_layers.py
│   ├── metadata.txt
│   └── README.md
└── .claude/                   # Claude Code configuration
    ├── CLAUDE.md
    ├── codebase-knowledge.md
    └── project-skills/
        ├── australis-author.md
        └── qgis-python-reference.md
```
