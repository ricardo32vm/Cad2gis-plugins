# -*- coding: utf-8 -*-
"""
Motor de transformación afín para georreferenciación vectorial.
Calcula la matriz de transformación por mínimos cuadrados y la aplica
a geometrías QGIS.
"""

import numpy as np
from qgis.core import (
    QgsGeometry, QgsPointXY, QgsWkbTypes,
    QgsVectorLayer, QgsFeature, QgsField,
    QgsCoordinateReferenceSystem, QgsProject
)
from PyQt5.QtCore import QVariant


class AfinTransform:
    """
    Transformación afín 2D calculada por mínimos cuadrados.
    
    Modelo:
        X = a*x + b*y + c
        Y = d*x + e*y + f
    
    En forma matricial:
        [X]   [a b c] [x]
        [Y] = [d e f] [y]
                      [1]
    """

    def __init__(self):
        self.matrix = None      # 2x3 numpy array
        self.rms_error = None   # Error cuadrático medio residual
        self.n_points = 0

    def calcular(self, puntos_src, puntos_dst):
        """
        Calcula la transformación afín a partir de pares de puntos homólogos.
        
        Args:
            puntos_src: lista de (x, y) en coordenadas CAD
            puntos_dst: lista de (X, Y) en coordenadas reales
        
        Returns:
            True si el cálculo fue exitoso, False si no hay suficientes puntos
        """
        if len(puntos_src) < 3:
            return False, "Se necesitan al menos 3 pares de puntos homólogos"

        src = np.array(puntos_src)
        dst = np.array(puntos_dst)
        n = len(src)

        # Construir matriz del sistema Ax = b para mínimos cuadrados
        # Para cada punto: x_src, y_src, 1 → X_dst
        #                  x_src, y_src, 1 → Y_dst
        A = np.zeros((2 * n, 6))
        b = np.zeros(2 * n)

        for i in range(n):
            x, y = src[i]
            X, Y = dst[i]
            A[2*i]     = [x, y, 1, 0, 0, 0]
            A[2*i + 1] = [0, 0, 0, x, y, 1]
            b[2*i]     = X
            b[2*i + 1] = Y

        # Mínimos cuadrados
        params, residuals, rank, sv = np.linalg.lstsq(A, b, rcond=None)
        a, b_p, c, d, e, f = params

        self.matrix = np.array([[a, b_p, c],
                                 [d, e,   f]])
        self.n_points = n

        # Calcular RMS
        errores = []
        for i in range(n):
            x, y = src[i]
            X_est = a*x + b_p*y + c
            Y_est = d*x + e*y + f
            err = np.sqrt((X_est - dst[i][0])**2 + (Y_est - dst[i][1])**2)
            errores.append(err)
        self.rms_error = np.sqrt(np.mean(np.array(errores)**2))

        return True, f"Transformación calculada. RMS: {self.rms_error:.4f} m"

    def transformar_punto(self, x, y):
        """Transforma un punto individual."""
        if self.matrix is None:
            raise ValueError("Matriz no calculada. Ejecutar calcular() primero.")
        a, b, c = self.matrix[0]
        d, e, f = self.matrix[1]
        X = a*x + b*y + c
        Y = d*x + e*y + f
        return X, Y

    def transformar_geometria(self, geom):
        """
        Transforma una QgsGeometry aplicando la transformación afín.
        Soporta Point, MultiPoint, LineString, MultiLineString,
        Polygon, MultiPolygon.
        """
        if geom is None or geom.isNull():
            return geom

        tipo = geom.wkbType()

        if QgsWkbTypes.geometryType(tipo) == QgsWkbTypes.PointGeometry:
            return self._transformar_punto_geom(geom)
        elif QgsWkbTypes.geometryType(tipo) == QgsWkbTypes.LineGeometry:
            return self._transformar_linea(geom)
        elif QgsWkbTypes.geometryType(tipo) == QgsWkbTypes.PolygonGeometry:
            return self._transformar_poligono(geom)
        else:
            return geom

    def _transformar_coords(self, coords):
        """Transforma una lista de QgsPointXY."""
        return [QgsPointXY(*self.transformar_punto(p.x(), p.y())) for p in coords]

    def _transformar_punto_geom(self, geom):
        if geom.isMultipart():
            pts = [QgsPointXY(*self.transformar_punto(p.x(), p.y()))
                   for p in geom.asMultiPoint()]
            return QgsGeometry.fromMultiPointXY(pts)
        else:
            p = geom.asPoint()
            X, Y = self.transformar_punto(p.x(), p.y())
            return QgsGeometry.fromPointXY(QgsPointXY(X, Y))

    def _transformar_linea(self, geom):
        if geom.isMultipart():
            lineas = [self._transformar_coords(l) for l in geom.asMultiPolyline()]
            return QgsGeometry.fromMultiPolylineXY(lineas)
        else:
            coords = self._transformar_coords(geom.asPolyline())
            return QgsGeometry.fromPolylineXY(coords)

    def _transformar_poligono(self, geom):
        if geom.isMultipart():
            poligonos = []
            for poly in geom.asMultiPolygon():
                rings = [self._transformar_coords(ring) for ring in poly]
                poligonos.append(rings)
            return QgsGeometry.fromMultiPolygonXY(poligonos)
        else:
            rings = [self._transformar_coords(ring) for ring in geom.asPolygon()]
            return QgsGeometry.fromPolygonXY(rings)


def aplicar_transformacion_a_capas(capas, transform, crs_destino, tolerancia_snap=0.0):
    """
    Aplica una transformación afín a una lista de capas vectoriales.
    Crea nuevas capas en memoria con el resultado.
    
    Args:
        capas: lista de QgsVectorLayer
        transform: instancia de AfinTransform ya calculada
        crs_destino: QgsCoordinateReferenceSystem de destino
        tolerancia_snap: si > 0, aplica snap de vértices cercanos (topología)
    
    Returns:
        lista de QgsVectorLayer transformadas
    """
    capas_resultado = []

    for capa in capas:
        tipo_geom = QgsWkbTypes.geometryDisplayString(capa.wkbType())
        nombre_nuevo = capa.name() + "_georef"

        # Determinar tipo de geometría para la capa nueva
        tipo_str = _tipo_geom_string(capa.wkbType())
        uri = f"{tipo_str}?crs={crs_destino.authid()}"

        capa_nueva = QgsVectorLayer(uri, nombre_nuevo, "memory")
        capa_nueva.dataProvider().addAttributes(capa.fields())
        capa_nueva.updateFields()

        features_nuevas = []
        for feat in capa.getFeatures():
            geom_orig = feat.geometry()
            geom_trans = transform.transformar_geometria(geom_orig)

            feat_nueva = QgsFeature(capa_nueva.fields())
            feat_nueva.setAttributes(feat.attributes())
            feat_nueva.setGeometry(geom_trans)
            features_nuevas.append(feat_nueva)

        capa_nueva.dataProvider().addFeatures(features_nuevas)
        capa_nueva.updateExtents()
        capas_resultado.append(capa_nueva)

    return capas_resultado


def _tipo_geom_string(wkb_type):
    """Convierte WKB type a string para URI de capa en memoria."""
    tipo = QgsWkbTypes.geometryType(wkb_type)
    if tipo == QgsWkbTypes.PointGeometry:
        return "Point"
    elif tipo == QgsWkbTypes.LineGeometry:
        return "LineString"
    elif tipo == QgsWkbTypes.PolygonGeometry:
        return "Polygon"
    else:
        return "Point"
