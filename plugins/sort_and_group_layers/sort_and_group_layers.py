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

from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox
from qgis.core import (
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsWkbTypes,
)


# Geometry type display order and human-readable names.
_GEOMETRY_SORT_ORDER = {
    QgsWkbTypes.PointGeometry: 0,
    QgsWkbTypes.LineGeometry: 1,
    QgsWkbTypes.PolygonGeometry: 2,
    QgsWkbTypes.NullGeometry: 3,
    QgsWkbTypes.UnknownGeometry: 4,
}

_GEOMETRY_GROUP_NAMES = {
    QgsWkbTypes.PointGeometry: "Point Layers",
    QgsWkbTypes.LineGeometry: "Line Layers",
    QgsWkbTypes.PolygonGeometry: "Polygon Layers",
    QgsWkbTypes.NullGeometry: "No Geometry",
    QgsWkbTypes.UnknownGeometry: "Unknown Geometry",
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
        self.original_order_clones = None

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
        self.original_order_clones = None

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
        """Save the current layer tree order (once, before the first sort/group)."""
        if self.original_order_clones is not None:
            return
        root = QgsProject.instance().layerTreeRoot()
        self.original_order_clones = [
            child.clone() for child in root.children()
        ]

    def _clear_saved_order(self):
        """Clear the saved original order (called when the project changes)."""
        self.original_order_clones = None

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

        Temporarily disables the layer-tree-registry bridge so that
        removing tree nodes does not de-register map layers from the
        project.
        """
        project = QgsProject.instance()
        bridge = project.layerTreeRegistryBridge()
        bridge.setEnabled(False)
        try:
            root.removeAllChildren()
            for child in new_children:
                root.addChildNode(child)
        finally:
            bridge.setEnabled(True)

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
                child.clone()
                for child in sorted(
                    children, key=key_func, reverse=reverse,
                )
            ]

        self._rebuild_tree(root, new_nodes)

    def _sort_with_groups(self, children, key_func, reverse):
        """Sort within each group and sort the top-level items.

        Returns a list of cloned / rebuilt top-level nodes in sorted order.
        """
        keyed_nodes = []

        for child in children:
            if isinstance(child, QgsLayerTreeGroup):
                # Sort the group's children by key_func.
                sorted_kids = sorted(
                    child.children(), key=key_func, reverse=reverse,
                )
                sorted_kid_clones = [kid.clone() for kid in sorted_kids]

                # Clone the group itself to preserve all properties
                # (visibility, expanded state, mutually-exclusive flag, etc.)
                # then replace its children with the sorted clones.
                group_clone = child.clone()
                group_clone.removeAllChildren()
                for kid_clone in sorted_kid_clones:
                    group_clone.addChildNode(kid_clone)

                # Group sort key: derived from its first child after sorting.
                if sorted_kids:
                    group_key = key_func(sorted_kids[0])
                else:
                    group_key = key_func(child)

                keyed_nodes.append((group_key, group_clone))
            else:
                keyed_nodes.append((key_func(child), child.clone()))

        keyed_nodes.sort(key=lambda x: x[0], reverse=reverse)
        return [node for _, node in keyed_nodes]

    # ------------------------------------------------------------------
    # Sort key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _key_file_path(node):
        """Full source path, lower-cased."""
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            return node.layer().source().lower()
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
            file_path = node.layer().source().split("|")[0]
            if os.path.isfile(file_path):
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
            file_path = node.layer().source().split("|")[0]
            if os.path.isfile(file_path):
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
                group.addChildNode(node.clone())
            new_children.append(group)

        self._rebuild_tree(root, new_children)

    def group_by_folder(self):
        """Group all layers by their source folder path.

        Creates one group per unique directory.  Layers whose source is
        not a local file (WMS, PostGIS, memory, etc.) are placed in an
        "Other Sources" group.  Existing groups are flattened first.
        """
        root = QgsProject.instance().layerTreeRoot()
        all_layers = self._flatten_layer_nodes(root)
        if not all_layers:
            return

        self._save_original_order()

        # Categorise by source folder.
        folders = {}   # {folder_path: [nodes]}
        other = []

        for node in all_layers:
            layer = node.layer()
            if layer is None:
                other.append(node)
                continue
            source = layer.source().split("|")[0]
            if os.path.isfile(source):
                folder = os.path.dirname(source)
                folders.setdefault(folder, []).append(node)
            else:
                other.append(node)

        # Generate short, unique display names for each folder.
        display_names = self._unique_folder_names(list(folders.keys()))

        # Build the new tree, sorted alphabetically by display name.
        new_children = []
        for folder_path in sorted(
            folders, key=lambda fp: display_names[fp].lower(),
        ):
            group = QgsLayerTreeGroup(display_names[folder_path])
            for node in folders[folder_path]:
                group.addChildNode(node.clone())
            new_children.append(group)

        if other:
            group = QgsLayerTreeGroup("Other Sources")
            for node in other:
                group.addChildNode(node.clone())
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
        if self.original_order_clones is None:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Sort and Group Layers",
                "No original order has been saved yet.\n"
                "Use a sort or group option first.",
            )
            return

        root = QgsProject.instance().layerTreeRoot()

        # Clone the saved nodes so the snapshot remains usable.
        clones = [node.clone() for node in self.original_order_clones]
        self._rebuild_tree(root, clones)

        # Clear saved order after a successful restore.
        self.original_order_clones = None
