"""
Sort and Group Layers - QGIS Plugin

Created by Australis Asset Advisory Group

Provides layer sorting and grouping functionality via two submenus under
the Layer menu.  Supports sorting by file path, alphabetical order, file
date, geometry type, feature count, and file size, as well as grouping by
geometry type or source folder.  Original layer order can be restored.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # noqa: N802
    """Load the SortAndGroupLayersPlugin class.

    Args:
        iface: QgisInterface instance.

    Returns:
        SortAndGroupLayersPlugin instance.
    """
    from .sort_and_group_layers import SortAndGroupLayersPlugin

    return SortAndGroupLayersPlugin(iface)
