"""
Sort and Group Layers Plugin for QGIS

Created by Australis Asset Advisory Group

A QGIS plugin that provides layer sorting and grouping functionality via
two submenus under the Layer menu:

- **Sort Layers** -- Sort by file path, alphabetical order, file
  modification date, geometry type, feature count, or file size.  When
  layers are already inside groups, sorting operates within each group
  and also reorders the groups themselves.

- **Group Layers** -- Automatically group layers by geometry type or by
  source folder path.  Group names are derived from the categorisation
  (e.g. "Point Layers", "Raster Layers", or the folder name).

Both submenus include a *Restore Original Order* action that returns
the layer tree to the state it was in before the first sort or group
operation.

Script created by Australis Asset Advisory Group.
"""

import os

# QGIS 4 / Qt6 compatibility: QAction moved from QtWidgets to QtGui.
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from qgis.PyQt.QtWidgets import QMenu, QMessageBox
from qgis.core import (
    Qgis,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsWkbTypes,
)


# Geometry type constants compatible with both QGIS 3.x and 4.x.
# Qgis.GeometryType was introduced in QGIS 3.30; QGIS 4.x removes the
# deprecated QgsWkbTypes.*Geometry aliases.
try:
    _GEOM_POINT = Qgis.GeometryType.Point
    _GEOM_LINE = Qgis.GeometryType.Line
    _GEOM_POLYGON = Qgis.GeometryType.Polygon
    _GEOM_NULL = Qgis.GeometryType.Null
    _GEOM_UNKNOWN = Qgis.GeometryType.Unknown
except AttributeError:
    _GEOM_POINT = QgsWkbTypes.PointGeometry
    _GEOM_LINE = QgsWkbTypes.LineGeometry
    _GEOM_POLYGON = QgsWkbTypes.PolygonGeometry
    _GEOM_NULL = QgsWkbTypes.NullGeometry
    _GEOM_UNKNOWN = QgsWkbTypes.UnknownGeometry


# Geometry type display order and human-readable names.
_GEOMETRY_SORT_ORDER = {
    _GEOM_POINT: 0,
    _GEOM_LINE: 1,
    _GEOM_POLYGON: 2,
    _GEOM_NULL: 3,
    _GEOM_UNKNOWN: 4,
}

_GEOMETRY_GROUP_NAMES = {
    _GEOM_POINT: "Point Layers",
    _GEOM_LINE: "Line Layers",
    _GEOM_POLYGON: "Polygon Layers",
    _GEOM_NULL: "No Geometry",
    _GEOM_UNKNOWN: "Unknown Geometry",
}


class SortAndGroupLayersPlugin:
    """QGIS plugin to sort and group layers in the Layers panel.

    Adds two submenus under the Layer menu:

    - *Sort Layers* with options to sort by various criteria.
    - *Group Layers* with options to group by geometry or folder.

    Script created by Australis Asset Advisory Group.
    """

    def __init__(self, iface):
        """Initialise the plugin.

        Args:
            iface: QgisInterface instance providing access to the QGIS GUI.
        """
        self.iface = iface
        self.sort_menu = None
        self.group_menu = None
        self.sort_menu_action = None
        self.group_menu_action = None
        self.actions = []
        self.original_order_nodes = None
        self._saved_layers = None

    # ------------------------------------------------------------------
    # Plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self):
        """Create the Sort Layers and Group Layers submenus."""
        layer_menu = self._find_layer_menu()
        if layer_menu is None:
            return

        # --- Sort Layers submenu ---
        self.sort_menu = QMenu("Sort Layers", self.iface.mainWindow())

        sort_options = [
            (
                "Sort by File Path",
                "Sort layers by full file source path",
                self.sort_by_file_path,
            ),
            (
                "Sort Alphabetically",
                "Sort layers alphabetically by name",
                self.sort_alphabetically,
            ),
            (
                "Sort by File Date (Newest First)",
                "Sort layers by file modification date",
                self.sort_by_file_date,
            ),
            (
                "Sort by Geometry Type",
                "Order layers: Point, Line, Polygon, Raster, then others",
                self.sort_by_geometry,
            ),
            (
                "Sort by Feature Count (Most First)",
                "Sort vector layers by number of features",
                self.sort_by_feature_count,
            ),
            (
                "Sort by File Size (Largest First)",
                "Sort layers by file size on disk",
                self.sort_by_file_size,
            ),
        ]

        for label, tooltip, slot in sort_options:
            action = QAction(label, self.iface.mainWindow())
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.sort_menu.addAction(action)
            self.actions.append(action)

        self.sort_menu.addSeparator()
        self._add_restore_action(self.sort_menu)
        self.sort_menu_action = layer_menu.addMenu(self.sort_menu)

        # --- Group Layers submenu (below Sort Layers) ---
        self.group_menu = QMenu("Group Layers", self.iface.mainWindow())

        group_options = [
            (
                "Group by Geometry Type",
                "Create groups for Point, Line, Polygon, Raster layers",
                self.group_by_geometry,
            ),
            (
                "Group by Folder Path",
                "Create groups based on each layer's source directory",
                self.group_by_folder,
            ),
        ]

        for label, tooltip, slot in group_options:
            action = QAction(label, self.iface.mainWindow())
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.group_menu.addAction(action)
            self.actions.append(action)

        self.group_menu.addSeparator()
        self._add_restore_action(self.group_menu)
        self.group_menu_action = layer_menu.addMenu(self.group_menu)

        # Clear saved order when the project is cleared or a new one loaded.
        QgsProject.instance().cleared.connect(self._clear_saved_order)

    def _add_restore_action(self, menu):
        """Append a Restore Original Order action to *menu*."""
        action = QAction("Restore Original Order", self.iface.mainWindow())
        action.setToolTip(
            "Restore the layer order from before the first sort or group"
        )
        action.triggered.connect(self.restore_original_order)
        menu.addAction(action)
        self.actions.append(action)

    def unload(self):
        """Remove the plugin menu entries and clean up."""
        layer_menu = self._find_layer_menu()
        if layer_menu:
            for menu_action in (self.sort_menu_action, self.group_menu_action):
                if menu_action:
                    layer_menu.removeAction(menu_action)

        for menu in (self.sort_menu, self.group_menu):
            if menu:
                menu.deleteLater()

        self.sort_menu = None
        self.group_menu = None
        self.sort_menu_action = None
        self.group_menu_action = None
        self.actions.clear()
        self.original_order_nodes = None
        self._saved_layers = None

        try:
            QgsProject.instance().cleared.disconnect(self._clear_saved_order)
        except TypeError:
            pass  # Signal was not connected

    # ------------------------------------------------------------------
    # Menu helpers
    # ------------------------------------------------------------------

    def _find_layer_menu(self):
        """Locate the Layer menu in the QGIS menu bar.

        Returns:
            QMenu or None if the Layer menu cannot be found.
        """
        menu_bar = self.iface.mainWindow().menuBar()
        for action in menu_bar.actions():
            # Strip the '&' keyboard-accelerator prefix.
            if action.text().replace("&", "") == "Layer":
                return action.menu()
        return None

    # ------------------------------------------------------------------
    # Original order management
    # ------------------------------------------------------------------

    def _save_original_order(self):
        """Save the current layer tree order (once, before the first sort/group).

        Stores both tree node copies (using direct layer references) and
        a dict of all QgsMapLayer objects to prevent garbage collection.
        """
        if self.original_order_nodes is not None:
            return
        root = QgsProject.instance().layerTreeRoot()
        self.original_order_nodes = [
            self._copy_node(child) for child in root.children()
        ]
        self._saved_layers = dict(QgsProject.instance().mapLayers())

    def _clear_saved_order(self):
        """Clear the saved original order (called when the project changes)."""
        self.original_order_nodes = None
        self._saved_layers = None

    # ------------------------------------------------------------------
    # Tree node copy helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_layer_node(original):
        """Create a new QgsLayerTreeLayer with a direct QgsMapLayer reference.

        Using the QgsLayerTreeLayer(QgsMapLayer) constructor keeps a live
        reference to the layer object, which is more robust than clone()
        that only stores the layer ID string.
        """
        layer = original.layer()
        if layer is None:
            return original.clone()
        node = QgsLayerTreeLayer(layer)
        node.setItemVisibilityChecked(original.itemVisibilityChecked())
        node.setExpanded(original.isExpanded())
        return node

    @staticmethod
    def _copy_node(node):
        """Recursively copy a tree node, using direct layer references.

        For QgsLayerTreeLayer nodes, creates a new node via the
        QgsLayerTreeLayer(QgsMapLayer) constructor so the layer
        reference is maintained directly rather than by ID lookup.
        For QgsLayerTreeGroup nodes, rebuilds the group and copies
        all children recursively.
        """
        if isinstance(node, QgsLayerTreeLayer):
            return SortAndGroupLayersPlugin._make_layer_node(node)
        if isinstance(node, QgsLayerTreeGroup):
            group = QgsLayerTreeGroup(node.name())
            group.setItemVisibilityChecked(node.itemVisibilityChecked())
            group.setExpanded(node.isExpanded())
            if node.isMutuallyExclusive():
                group.setIsMutuallyExclusive(True)
            for child in node.children():
                group.addChildNode(
                    SortAndGroupLayersPlugin._copy_node(child)
                )
            return group
        return node.clone()

    # ------------------------------------------------------------------
    # Tree manipulation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_layer_nodes(parent):
        """Recursively collect all QgsLayerTreeLayer nodes from *parent*."""
        nodes = []
        for child in parent.children():
            if isinstance(child, QgsLayerTreeLayer):
                nodes.append(child)
            elif isinstance(child, QgsLayerTreeGroup):
                nodes.extend(
                    SortAndGroupLayersPlugin._flatten_layer_nodes(child)
                )
        return nodes

    @staticmethod
    def _rebuild_tree(root, new_children):
        """Replace all children of *root* with *new_children*.

        Uses a safe two-phase approach:
          Phase 1 -- Append all new children to the tree (originals
                     are still present, so every layer keeps at least
                     one tree-node reference at all times).
          Phase 2 -- Remove the original children with the
                     layer-tree-registry bridge disabled, then re-add
                     any layers that were inadvertently de-registered.
        """
        project = QgsProject.instance()
        bridge = project.layerTreeRegistryBridge()

        # Keep Python references to every registered layer so that even
        # if they are briefly removed from the registry, the C++ objects
        # stay alive and can be re-registered.
        saved_layers = dict(project.mapLayers())

        original_count = len(root.children())

        # Phase 1: append new children at the end of the tree.
        # No nodes are removed yet, so every layer still has its
        # original tree node and the bridge has nothing to react to.
        for child in new_children:
            root.addChildNode(child)

        # Phase 2: remove the *original* children (they are the first
        # ``original_count`` items, since new children were appended).
        bridge.setEnabled(False)
        try:
            for _ in range(original_count):
                root.removeChildNode(root.children()[0])

            # Safety net: re-register any layers that were lost.
            for lid, layer in saved_layers.items():
                if project.mapLayer(lid) is None:
                    project.addMapLayer(layer, False)
        finally:
            bridge.setEnabled(True)

        # Resolve layer references on all (new) tree nodes so that
        # node.layer() returns the correct QgsMapLayer object.
        root.resolveReferences(project)

    # ------------------------------------------------------------------
    # Sorting engine
    # ------------------------------------------------------------------

    def _reorder_layers(self, key_func, reverse=False):
        """Reorder top-level layer tree nodes using *key_func*.

        If the tree already contains groups, sorting is applied *within*
        each group and the groups themselves are also reordered.

        Args:
            key_func: Callable accepting a QgsLayerTreeNode and returning
                      a sortable key.
            reverse:  If True sort in descending order.
        """
        root = QgsProject.instance().layerTreeRoot()
        children = root.children()
        if not children:
            return

        self._save_original_order()

        has_groups = any(
            isinstance(c, QgsLayerTreeGroup) for c in children
        )

        if has_groups:
            new_nodes = self._sort_with_groups(children, key_func, reverse)
        else:
            new_nodes = [
                self._copy_node(child)
                for child in sorted(
                    children, key=key_func, reverse=reverse,
                )
            ]

        self._rebuild_tree(root, new_nodes)

    def _sort_with_groups(self, children, key_func, reverse):
        """Sort within each group and sort the top-level items.

        Returns a list of new top-level nodes in sorted order.
        """
        keyed_nodes = []

        for child in children:
            if isinstance(child, QgsLayerTreeGroup):
                # Sort the group's children by key_func.
                sorted_kids = sorted(
                    child.children(), key=key_func, reverse=reverse,
                )

                # Build a new group with copies in sorted order.
                new_group = QgsLayerTreeGroup(child.name())
                new_group.setItemVisibilityChecked(
                    child.itemVisibilityChecked()
                )
                new_group.setExpanded(child.isExpanded())
                if child.isMutuallyExclusive():
                    new_group.setIsMutuallyExclusive(True)
                for kid in sorted_kids:
                    new_group.addChildNode(self._copy_node(kid))

                # Group sort key: derived from its first child.
                if sorted_kids:
                    group_key = key_func(sorted_kids[0])
                else:
                    group_key = key_func(child)

                keyed_nodes.append((group_key, new_group))
            else:
                keyed_nodes.append(
                    (key_func(child), self._copy_node(child))
                )

        keyed_nodes.sort(key=lambda x: x[0], reverse=reverse)
        return [node for _, node in keyed_nodes]

    # ------------------------------------------------------------------
    # File path extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _get_file_path(layer):
        """Extract the on-disk file path from a layer's data source.

        Uses QgsProviderRegistry.decodeUri() for robust extraction that
        handles GeoPackage, SpatiaLite, shapefiles, file geodatabases,
        and other provider-specific source strings.

        Different providers store the file path under different keys:
          - ogr, gdal, delimitedtext, virtual: 'path'
          - spatialite: 'dbname'

        Returns:
            The file path string, or empty string if the source is not
            file-based (e.g. WMS, PostGIS, memory layers).
        """
        # --- Attempt 1: decodeUri (most reliable) ---
        try:
            uri_parts = QgsProviderRegistry.instance().decodeUri(
                layer.providerType(), layer.source()
            )
            # Check every key that providers commonly use for file paths.
            for key in ("path", "dbname", "filename", "url"):
                val = uri_parts.get(key) or ""
                if not val:
                    continue
                # Strip file:// prefix if present (delimitedtext provider).
                if val.startswith("file://"):
                    val = val[7:]
                    # On Windows file:// URLs may look like file:///C:/...
                    if len(val) > 2 and val[0] == "/" and val[2] == ":":
                        val = val[1:]
                # Ignore pure URLs (WMS/WFS).
                if val.startswith(("http://", "https://")):
                    continue
                if val:
                    return val
        except Exception:
            pass

        # --- Attempt 2: parse the raw source string ---
        source = layer.source()

        # GeoPackage / OGR style: "path|layername=..."
        candidate = source.split("|")[0].strip()
        if candidate and not candidate.startswith(("http://", "https://")):
            return candidate

        # SpatiaLite style: "dbname='path' table=..."
        if "dbname=" in source:
            start = source.find("dbname=")
            rest = source[start + 7:].strip()
            if rest.startswith("'"):
                end = rest.find("'", 1)
                if end > 0:
                    return rest[1:end]

        return ""

    # ------------------------------------------------------------------
    # Sort key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _key_file_path(node):
        """File path, lower-cased.  Falls back to source URI for
        non-file layers so they still sort consistently."""
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            fp = SortAndGroupLayersPlugin._get_file_path(node.layer())
            return (fp or node.layer().source()).lower()
        if isinstance(node, QgsLayerTreeGroup):
            return node.name().lower()
        return ""

    @staticmethod
    def _key_alphabetical(node):
        """Display name, lower-cased."""
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            return node.layer().name().lower()
        if isinstance(node, QgsLayerTreeGroup):
            return node.name().lower()
        return ""

    @classmethod
    def _key_file_date(cls, node):
        """File modification timestamp (float seconds since epoch).

        Non-file layers (WMS, PostGIS, memory layers, etc.) and groups
        return 0.0 so they sort to the end in descending mode.
        """
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            file_path = cls._get_file_path(node.layer())
            if file_path and os.path.isfile(file_path):
                try:
                    return os.path.getmtime(file_path)
                except OSError:
                    pass
        return 0.0

    @staticmethod
    def _key_geometry(node):
        """Geometry sort order: Point < Line < Polygon < Raster < Other.

        A secondary alphabetical sort is applied within each type.
        """
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            layer = node.layer()
            if isinstance(layer, QgsVectorLayer):
                return (
                    _GEOMETRY_SORT_ORDER.get(layer.geometryType(), 99),
                    layer.name().lower(),
                )
            if isinstance(layer, QgsRasterLayer):
                return (90, layer.name().lower())
            return (95, layer.name().lower())
        if isinstance(node, QgsLayerTreeGroup):
            return (100, node.name().lower())
        return (999, "")

    @staticmethod
    def _key_feature_count(node):
        """Feature count for vector layers (int).

        Raster layers return -1 and groups return -2 so they sort to the
        end in descending mode.
        """
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            layer = node.layer()
            if isinstance(layer, QgsVectorLayer):
                return layer.featureCount()
            return -1
        return -2

    @classmethod
    def _key_file_size(cls, node):
        """File size in bytes (int).

        Non-file layers and groups return -1 so they sort to the end in
        descending mode.
        """
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            file_path = cls._get_file_path(node.layer())
            if file_path and os.path.isfile(file_path):
                try:
                    return os.path.getsize(file_path)
                except OSError:
                    pass
        return -1

    # ------------------------------------------------------------------
    # Sort actions (connected to menu items)
    # ------------------------------------------------------------------

    def sort_by_file_path(self):
        """Sort layers by their full file source path (ascending A-Z)."""
        self._reorder_layers(self._key_file_path)

    def sort_alphabetically(self):
        """Sort layers alphabetically by display name (ascending A-Z)."""
        self._reorder_layers(self._key_alphabetical)

    def sort_by_file_date(self):
        """Sort layers by file modification date (newest first)."""
        self._reorder_layers(self._key_file_date, reverse=True)

    def sort_by_geometry(self):
        """Sort layers grouped by geometry type (Point, Line, Polygon)."""
        self._reorder_layers(self._key_geometry)

    def sort_by_feature_count(self):
        """Sort layers by feature count (most features first)."""
        self._reorder_layers(self._key_feature_count, reverse=True)

    def sort_by_file_size(self):
        """Sort layers by file size on disk (largest first)."""
        self._reorder_layers(self._key_file_size, reverse=True)

    # ------------------------------------------------------------------
    # Grouping engine
    # ------------------------------------------------------------------

    def group_by_geometry(self):
        """Group all layers by geometry type.

        Creates groups named "Point Layers", "Line Layers",
        "Polygon Layers", "Raster Layers", etc.  Existing groups are
        flattened first so every layer is re-categorised.
        """
        root = QgsProject.instance().layerTreeRoot()
        all_layers = self._flatten_layer_nodes(root)
        if not all_layers:
            return

        self._save_original_order()

        # Categorise each layer node.
        categories = {}  # {(sort_order, display_name): [nodes]}

        for node in all_layers:
            layer = node.layer()
            if layer is None:
                key = (99, "Other Layers")
            elif isinstance(layer, QgsVectorLayer):
                geom = layer.geometryType()
                order = _GEOMETRY_SORT_ORDER.get(geom, 99)
                name = _GEOMETRY_GROUP_NAMES.get(geom, "Other Layers")
                key = (order, name)
            elif isinstance(layer, QgsRasterLayer):
                key = (90, "Raster Layers")
            else:
                key = (99, "Other Layers")

            categories.setdefault(key, []).append(node)

        # Build the new tree with one group per category.
        new_children = []
        for (order, name) in sorted(categories):
            group = QgsLayerTreeGroup(name)
            for node in categories[(order, name)]:
                group.addChildNode(self._copy_node(node))
            new_children.append(group)

        self._rebuild_tree(root, new_children)

    def group_by_folder(self):
        """Group all layers by their source folder path.

        Creates one group per unique directory.  Layers within each
        group are sorted by filename.  Layers whose source cannot be
        resolved to a folder (WMS, PostGIS, memory, etc.) are placed
        in an "Other Sources" group.  Existing groups are flattened
        first.
        """
        root = QgsProject.instance().layerTreeRoot()
        all_layers = self._flatten_layer_nodes(root)
        if not all_layers:
            return

        self._save_original_order()

        # Categorise by source folder.
        folders = {}   # {folder_path: [(sort_key, node)]}
        other = []

        for node in all_layers:
            layer = node.layer()
            if layer is None:
                other.append(node)
                continue
            file_path = self._get_file_path(layer)
            # Accept any path that has a directory component.  We do
            # NOT require os.path.isfile() because the path may use a
            # provider-specific format that Python cannot stat, yet it
            # still represents a valid on-disk location.
            if file_path and os.path.dirname(file_path):
                folder = os.path.dirname(file_path)
                filename = os.path.basename(file_path).lower()
                folders.setdefault(folder, []).append((filename, node))
            else:
                other.append(node)

        # Generate short, unique display names for each folder.
        display_names = self._unique_folder_names(list(folders.keys()))

        # Build the new tree, sorted alphabetically by display name.
        # Within each group, layers are sorted by filename.
        new_children = []
        for folder_path in sorted(
            folders, key=lambda fp: display_names[fp].lower(),
        ):
            group = QgsLayerTreeGroup(display_names[folder_path])
            for _filename, node in sorted(
                folders[folder_path], key=lambda x: x[0],
            ):
                group.addChildNode(self._copy_node(node))
            new_children.append(group)

        if other:
            group = QgsLayerTreeGroup("Other Sources")
            for node in other:
                group.addChildNode(self._copy_node(node))
            new_children.append(group)

        self._rebuild_tree(root, new_children)

    @staticmethod
    def _unique_folder_names(folder_paths):
        """Return a dict mapping each folder path to a short unique name.

        Uses the directory basename; if duplicates exist, prepends the
        parent directory for disambiguation.  Falls back to the full
        normalised path if still ambiguous.
        """
        if not folder_paths:
            return {}

        norm = {fp: os.path.normpath(fp) for fp in folder_paths}

        # Group by basename.
        base_groups = {}
        for fp in folder_paths:
            base = os.path.basename(norm[fp]) or norm[fp]
            base_groups.setdefault(base, []).append(fp)

        result = {}
        for base, paths in base_groups.items():
            if len(paths) == 1:
                result[paths[0]] = base
            else:
                # Try parent/base to disambiguate.
                seen = {}
                for fp in paths:
                    parent = os.path.basename(os.path.dirname(norm[fp]))
                    combo = (
                        os.path.join(parent, base) if parent else norm[fp]
                    )
                    seen.setdefault(combo, []).append(fp)

                for combo, sub_paths in seen.items():
                    if len(sub_paths) == 1:
                        result[sub_paths[0]] = combo
                    else:
                        # Still ambiguous -- use full path.
                        for fp in sub_paths:
                            result[fp] = norm[fp]

        return result

    # ------------------------------------------------------------------
    # Restore original order
    # ------------------------------------------------------------------

    def restore_original_order(self):
        """Restore the layer order saved before the first sort or group."""
        if self.original_order_nodes is None:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Sort and Group Layers",
                "No original order has been saved yet.\n"
                "Use a sort or group option first.",
            )
            return

        project = QgsProject.instance()
        root = project.layerTreeRoot()

        # Re-register any layers that were lost since the snapshot.
        if self._saved_layers:
            for lid, layer in self._saved_layers.items():
                if project.mapLayer(lid) is None:
                    project.addMapLayer(layer, False)

        # Copy the saved nodes (so the snapshot can be used again).
        copies = [self._copy_node(node) for node in self.original_order_nodes]
        self._rebuild_tree(root, copies)

        # Clear saved order after a successful restore.
        self.original_order_nodes = None
        self._saved_layers = None
