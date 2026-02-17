"""
Sort Layers - QGIS Plugin

Created by Australis Asset Advisory Group

Provides layer sorting functionality via a 'Sort Layers' submenu under
the Layer menu. Supports sorting by file path, alphabetical order, file
date, geometry type, feature count, and file size, with the ability to
restore the original layer order.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # noqa: N802
    """Load the SortLayersPlugin class.

    Args:
        iface: QgisInterface instance.

    Returns:
        SortLayersPlugin instance.
    """
    from .sort_layers import SortLayersPlugin

    return SortLayersPlugin(iface)
