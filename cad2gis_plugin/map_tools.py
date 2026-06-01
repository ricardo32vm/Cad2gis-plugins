# -*- coding: utf-8 -*-
"""
Herramienta de mapa para captura interactiva de puntos homólogos.
Modo A: clic en capa fuente (CAD) → guarda punto fuente
Modo B: clic en capa destino (referencia) → guarda punto destino
"""

from qgis.gui import QgsMapTool, QgsVertexMarker, QgsRubberBand
from qgis.core import (
    QgsPointXY, QgsWkbTypes, QgsSnappingConfig,
    QgsSnappingUtils, QgsTolerance, QgsProject
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QPixmap


class PickPointTool(QgsMapTool):
    """
    Herramienta de mapa que captura un punto al hacer clic.
    Emite la señal point_picked con las coordenadas del punto.
    """
    point_picked = pyqtSignal(float, float)

    def __init__(self, canvas, snap_layer=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.snap_layer = snap_layer
        self.cursor = Qt.CrossCursor

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            point = self.toMapCoordinates(event.pos())

            # Intentar snap a vértice si hay capa de referencia
            if self.snap_layer:
                snapped = self._snap_to_vertex(point, event.pos())
                if snapped:
                    point = snapped

            self.point_picked.emit(point.x(), point.y())

    def _snap_to_vertex(self, point, pos):
        """Intenta snapear al vértice más cercano en la capa snap_layer."""
        try:
            snapper = QgsSnappingUtils(self.canvas)
            config = QgsSnappingConfig()
            config.setEnabled(True)
            config.setMode(QgsSnappingConfig.ActiveLayer)
            config.setType(QgsSnappingConfig.Vertex)
            config.setTolerance(10)
            config.setUnits(QgsTolerance.Pixels)
            snapper.setConfig(config)

            match = snapper.snapToMap(pos)
            if match.isValid():
                return match.point()
        except Exception:
            pass
        return None

    def activate(self):
        self.canvas.setCursor(QCursor(Qt.CrossCursor))

    def deactivate(self):
        super().deactivate()


class PointPairManager:
    """
    Gestiona los pares de puntos homólogos y los marcadores visuales en el mapa.
    
    Un par tiene:
      - src: (x, y) en coordenadas CAD
      - dst: (X, Y) en coordenadas reales
      - marcadores en el canvas
    """

    COLOR_SRC = QColor(255, 0, 0)    # Rojo para puntos fuente (CAD)
    COLOR_DST = QColor(0, 120, 255)  # Azul para puntos destino (georef)

    def __init__(self, canvas):
        self.canvas = canvas
        self.pares = []          # lista de {'src': (x,y), 'dst': (X,Y)}
        self.marcadores = []     # lista de [marker_src, marker_dst]

    def agregar_par(self, src, dst):
        """Agrega un par completo y dibuja los marcadores."""
        self.pares.append({'src': src, 'dst': dst})
        idx = len(self.pares) - 1

        m_src = self._crear_marcador(src, self.COLOR_SRC, idx + 1)
        m_dst = self._crear_marcador(dst, self.COLOR_DST, idx + 1)
        self.marcadores.append((m_src, m_dst))

        return idx

    def eliminar_par(self, idx):
        """Elimina un par y sus marcadores del canvas."""
        if 0 <= idx < len(self.pares):
            m_src, m_dst = self.marcadores[idx]
            self.canvas.scene().removeItem(m_src)
            self.canvas.scene().removeItem(m_dst)
            self.pares.pop(idx)
            self.marcadores.pop(idx)
            self._renumerar_marcadores()

    def limpiar(self):
        """Elimina todos los pares y marcadores."""
        for m_src, m_dst in self.marcadores:
            self.canvas.scene().removeItem(m_src)
            self.canvas.scene().removeItem(m_dst)
        self.pares.clear()
        self.marcadores.clear()

    def get_src_points(self):
        return [p['src'] for p in self.pares]

    def get_dst_points(self):
        return [p['dst'] for p in self.pares]

    def exportar(self):
        """Exporta pares como lista de dicts para guardar en archivo."""
        return list(self.pares)

    def importar(self, pares_list):
        """Importa pares desde lista de dicts y recrea marcadores."""
        self.limpiar()
        for par in pares_list:
            self.agregar_par(par['src'], par['dst'])

    def _crear_marcador(self, coords, color, numero):
        marker = QgsVertexMarker(self.canvas)
        marker.setCenter(QgsPointXY(*coords))
        marker.setColor(color)
        marker.setIconSize(12)
        marker.setIconType(QgsVertexMarker.ICON_CROSS)
        marker.setPenWidth(2)
        return marker

    def _renumerar_marcadores(self):
        """Actualiza los marcadores después de eliminar un par."""
        pass  # Los marcadores no muestran número en esta versión
