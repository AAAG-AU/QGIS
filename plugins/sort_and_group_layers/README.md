# Sort and Group Layers - QGIS Plugin

Created by **Australis Asset Advisory Group**

A QGIS plugin that adds **Sort Layers** and **Group Layers** submenus under
the **Layer** menu, providing multiple options to reorder and organise layers
in the Layers panel.

## Sort Layers

| Sort Option | Description |
|---|---|
| **Sort by File Path** | Ascending by full data source path including directories |
| **Sort Alphabetically** | Ascending by layer display name (A-Z) |
| **Sort by File Date** | Newest file modification date first |
| **Sort by Geometry Type** | Orders layers: Point, Line, Polygon, Raster, then other |
| **Sort by Feature Count** | Most features first (vector layers only) |
| **Sort by File Size** | Largest file first |
| **Restore Original Order** | Returns layers to the order before the first sort or group |

When layers are already inside groups, sorting operates **within each
group** and also **reorders the groups** themselves based on the selected
sort criterion.

## Group Layers

| Group Option | Description |
|---|---|
| **Group by Geometry Type** | Creates groups: Point Layers, Line Layers, Polygon Layers, Raster Layers, etc. |
| **Group by Folder Path** | Creates one group per unique source directory |
| **Restore Original Order** | Returns layers to the order before the first sort or group |

Grouping flattens any existing groups first, so every layer is
re-categorised.  Group names are representative of the categorisation
(geometry type name or folder name).  Non-file layers (WMS, PostGIS,
memory layers) are placed in an "Other Sources" group when grouping by
folder.

## Requirements

- QGIS 3.0 or later

## Installation

### Via deploy script

From the repository root, run:

```bash
python deploy_plugins.py
```

### Manual

Copy the `plugins/sort_and_group_layers` folder into your QGIS plugins
directory:

- **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

Then enable the plugin in QGIS via **Plugins > Manage and Install Plugins**.

## Usage

After enabling, open the **Layer** menu in the QGIS menu bar.  Two new
submenus appear at the bottom:

1. **Sort Layers** -- sorting options and restore
2. **Group Layers** -- grouping options and restore

## Notes

- Only top-level nodes are sorted; contents within nested sub-groups are
  left unchanged.
- When grouping, existing groups are flattened first so every layer is
  re-categorised.
- Folder grouping uses short unique names (directory basename), adding
  parent directory components only when needed to disambiguate.
- Non-file layers sort to the end for file-based criteria (date, size).
- Geometry sort applies a secondary alphabetical sort within each type.
