"""
Sort Layers Plugin for QGIS

Created by Australis Asset Advisory Group

A QGIS plugin that provides layer sorting functionality via a submenu
under the Layer menu. Supports sorting by file path, alphabetical order,
file modification date, geometry type, feature count, and file size, with
the ability to save and restore the original layer order.

Script created by Australis Asset Advisory Group.
"""

import os

from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox
from qgis.core import (
    Qgis,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsMapLayer,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)


# Geometry type display order: Point=0, Line=1, Polygon=2, then others.
_GEOMETRY_SORT_ORDER = {
    QgsWkbTypes.PointGeometry: 0,
    QgsWkbTypes.LineGeometry: 1,
    QgsWkbTypes.PolygonGeometry: 2,
    QgsWkbTypes.NullGeometry: 3,
    QgsWkbTypes.UnknownGeometry: 4,
}


class SortLayersPlugin:
    """QGIS plugin to sort layers in the Layers panel.

    Adds a 'Sort Layers' submenu under the Layer menu with options to sort
    by file path, alphabetical order, file date, geometry type, feature
    count, or file size, and to restore the original layer order.

    Script created by Australis Asset Advisory Group.
    """

    def __init__(self, iface):
        """Initialise the plugin.

        Args:
            iface: QgisInterface instance providing access to the QGIS GUI.
        """
        self.iface = iface
        self.sort_menu = None
        self.menu_action = None
        self.actions = []
        self.original_order_clones = None

    # ------------------------------------------------------------------
    # Plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self):
        """Create the Sort Layers submenu under the Layer menu."""
        layer_menu = self._find_layer_menu()
        if layer_menu is None:
            return

        self.sort_menu = QMenu("Sort Layers", self.iface.mainWindow())

        # --- Sort actions ---
        sort_options = [
            ("Sort by File Path", "Sort layers by full file source path",
             self.sort_by_file_path),
            ("Sort Alphabetically", "Sort layers alphabetically by name",
             self.sort_alphabetically),
            ("Sort by File Date (Newest First)",
             "Sort layers by file modification date",
             self.sort_by_file_date),
            ("Sort by Geometry Type",
             "Group layers by geometry: Point, Line, Polygon, then others",
             self.sort_by_geometry),
            ("Sort by Feature Count (Most First)",
             "Sort vector layers by number of features",
             self.sort_by_feature_count),
            ("Sort by File Size (Largest First)",
             "Sort layers by file size on disk",
             self.sort_by_file_size),
        ]

        for label, tooltip, slot in sort_options:
            action = QAction(label, self.iface.mainWindow())
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.sort_menu.addAction(action)
            self.actions.append(action)

        self.sort_menu.addSeparator()

        action_restore = QAction(
            "Restore Original Order", self.iface.mainWindow()
        )
        action_restore.setToolTip(
            "Restore the layer order from before the first sort"
        )
        action_restore.triggered.connect(self.restore_original_order)
        self.sort_menu.addAction(action_restore)
        self.actions.append(action_restore)

        # Insert the submenu into the Layer menu.
        self.menu_action = layer_menu.addMenu(self.sort_menu)

        # Clear saved order when the project is cleared or a new one loaded.
        QgsProject.instance().cleared.connect(self._clear_saved_order)

    def unload(self):
        """Remove the plugin menu entries and clean up."""
        if self.sort_menu and self.menu_action:
            layer_menu = self._find_layer_menu()
            if layer_menu:
                layer_menu.removeAction(self.menu_action)

        if self.sort_menu:
            self.sort_menu.deleteLater()
            self.sort_menu = None

        self.menu_action = None
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
        """Save the current layer tree order (once, before the first sort)."""
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
    # Sorting engine
    # ------------------------------------------------------------------

    def _reorder_layers(self, key_func, reverse=False):
        """Reorder top-level layer tree nodes using *key_func*.

        The layer-tree-registry bridge is temporarily disabled so that
        removing tree nodes does not de-register map layers from the
        project.

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

        sorted_clones = [
            child.clone()
            for child in sorted(children, key=key_func, reverse=reverse)
        ]

        project = QgsProject.instance()
        bridge = project.layerTreeRegistryBridge()
        bridge.setEnabled(False)
        try:
            root.removeAllChildren()
            for clone in sorted_clones:
                root.addChildNode(clone)
        finally:
            bridge.setEnabled(True)

    # ------------------------------------------------------------------
    # Sort key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _layer_source(node):
        """Return the data source path for a layer tree node."""
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            return node.layer().source()
        return ""

    @staticmethod
    def _file_path_from_source(source):
        """Strip provider suffixes (e.g. '|layername=...') from a source."""
        return source.split("|")[0]

    # --- Key functions (each returns a sortable value) -----------------

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
            file_path = cls._file_path_from_source(node.layer().source())
            if os.path.isfile(file_path):
                try:
                    return os.path.getmtime(file_path)
                except OSError:
                    pass
        return 0.0

    @staticmethod
    def _key_geometry(node):
        """Geometry sort order: Point < Line < Polygon < Null < Unknown.

        Raster layers and groups sort after all geometry types.
        """
        if isinstance(node, QgsLayerTreeLayer) and node.layer():
            layer = node.layer()
            if isinstance(layer, QgsVectorLayer):
                return (
                    _GEOMETRY_SORT_ORDER.get(layer.geometryType(), 99),
                    layer.name().lower(),
                )
            # Raster or other layer types sort after vector layers.
            return (90, layer.name().lower())
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
            file_path = cls._file_path_from_source(node.layer().source())
            if os.path.isfile(file_path):
                try:
                    return os.path.getsize(file_path)
                except OSError:
                    pass
        return -1

    # ------------------------------------------------------------------
    # Public sort actions (connected to menu items)
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

    def restore_original_order(self):
        """Restore the layer order saved before the first sort."""
        if self.original_order_clones is None:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Sort Layers",
                "No original order has been saved yet.\n"
                "Use one of the sort options first.",
            )
            return

        project = QgsProject.instance()
        root = project.layerTreeRoot()
        bridge = project.layerTreeRegistryBridge()

        # Clone saved nodes so the snapshot can still be used if needed.
        clones = [node.clone() for node in self.original_order_clones]

        bridge.setEnabled(False)
        try:
            root.removeAllChildren()
            for clone in clones:
                root.addChildNode(clone)
        finally:
            bridge.setEnabled(True)

        # Clear saved order after a successful restore.
        self.original_order_clones = None
