# -*- coding: utf-8 -*-
"""
CAD2GIS Georeferencer
Plugin QGIS para georreferenciar capas vectoriales provenientes de AutoCAD.

UTN Facultad Regional Villa María
"""

import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication

from .cad2gis_dialog import CAD2GISDialog


class CAD2GISPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.dialog = None
        self.action = None

    def initGui(self):
        """Crea la entrada en el menú y la barra de herramientas."""
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(
            icon,
            "CAD2GIS Georeferencer",
            self.iface.mainWindow()
        )
        self.action.setToolTip(
            "Georreferencia capas CAD mediante transformación afín\n"
            "Separa geometrías y repara topología"
        )
        self.action.triggered.connect(self.run)

        # Agregar al menú Vector y a la toolbar
        self.iface.addPluginToVectorMenu("CAD2GIS", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Elimina el plugin de la interfaz."""
        self.iface.removePluginVectorMenu("CAD2GIS", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            self.dialog.close()

    def run(self):
        """Abre el diálogo principal."""
        if self.dialog is None:
            self.dialog = CAD2GISDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
