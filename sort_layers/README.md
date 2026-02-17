# Sort Layers - QGIS Plugin

Created by **Australis Asset Advisory Group**

A QGIS plugin that adds a **Sort Layers** submenu under the **Layer** menu,
providing multiple options to reorder layers in the Layers panel.

## Features

| Sort Option | Description |
|---|---|
| **Sort by File Path** | Ascending by full data source path including directories |
| **Sort Alphabetically** | Ascending by layer display name (A-Z) |
| **Sort by File Date** | Newest file modification date first |
| **Sort by Geometry Type** | Groups layers: Point, Line, Polygon, then raster/other |
| **Sort by Feature Count** | Most features first (vector layers only) |
| **Sort by File Size** | Largest file first |
| **Restore Original Order** | Returns layers to the order before the first sort |

The original layer order is automatically saved before the first sort
operation and can be restored at any time. The saved order is cleared when
the project changes or after a successful restore.

## Requirements

- QGIS 3.0 or later

## Installation

Copy the `sort_layers` folder into your QGIS plugins directory:

- **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

Then enable the plugin in QGIS via **Plugins > Manage and Install Plugins**.

## Usage

After enabling, open the **Layer** menu in the QGIS menu bar. A new
**Sort Layers** submenu will be available at the bottom with all sorting
options.

## Notes

- Only top-level layers and groups are sorted; contents within groups are
  left unchanged.
- Non-file layers (WMS, PostGIS, memory layers) are handled gracefully and
  sort to the end for file-based sort options (date, size).
- Geometry sort uses a secondary alphabetical sort within each geometry
  type group.
