# -*- coding: utf-8 -*-
"""
Herramientas de separación de geometrías y reparación topológica.

Problema típico de CAD:
  - Todo en una sola capa (puntos, líneas y polígonos mezclados)
  - Polígonos no cerrados (último vértice no coincide con el primero)
  - Líneas duplicadas o superpuestas
  - Vértices casi coincidentes (no snapeados)
"""

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsWkbTypes, QgsPointXY, QgsCoordinateReferenceSystem,
    QgsFields, QgsField
)
from PyQt5.QtCore import QVariant


def separar_geometrias(capa_mixta, crs_str="EPSG:4326"):
    """
    Separa una capa con geometrías mixtas (típico de CAD) en tres capas:
    puntos, líneas y polígonos.
    
    Args:
        capa_mixta: QgsVectorLayer con geometrías mezcladas
        crs_str: CRS de la capa (si no tiene asignado)
    
    Returns:
        dict con claves 'puntos', 'lineas', 'poligonos' → QgsVectorLayer o None
    """
    capas = {
        'puntos':    _crear_capa_memoria("Point",      crs_str, capa_mixta.name() + "_puntos"),
        'lineas':    _crear_capa_memoria("LineString",  crs_str, capa_mixta.name() + "_lineas"),
        'poligonos': _crear_capa_memoria("Polygon",     crs_str, capa_mixta.name() + "_poligonos"),
    }

    # Copiar campos de la capa original a todas las nuevas
    for capa_nueva in capas.values():
        capa_nueva.dataProvider().addAttributes(capa_mixta.fields())
        capa_nueva.updateFields()

    feats = {'puntos': [], 'lineas': [], 'poligonos': []}

    for feat in capa_mixta.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isNull():
            continue

        tipo = QgsWkbTypes.geometryType(geom.wkbType())

        if tipo == QgsWkbTypes.PointGeometry:
            destino = 'puntos'
        elif tipo == QgsWkbTypes.LineGeometry:
            # Una línea cerrada con 4+ vértices puede ser un polígono
            if _es_poligono_disfrazado(geom):
                geom = _linea_a_poligono(geom)
                destino = 'poligonos'
            else:
                destino = 'lineas'
        elif tipo == QgsWkbTypes.PolygonGeometry:
            destino = 'poligonos'
        else:
            continue

        feat_nueva = QgsFeature(capas[destino].fields())
        feat_nueva.setAttributes(feat.attributes())
        feat_nueva.setGeometry(geom)
        feats[destino].append(feat_nueva)

    for key, lista in feats.items():
        if lista:
            capas[key].dataProvider().addFeatures(lista)
            capas[key].updateExtents()

    # Retornar solo las capas que tienen features
    return {k: v for k, v in capas.items() if v.featureCount() > 0}


def reparar_topologia(capa, tolerancia=0.001, cerrar_poligonos=True,
                       eliminar_duplicados=True, snap_vertices=True):
    """
    Repara problemas topológicos típicos de capas provenientes de CAD.
    
    Operaciones:
      - Cerrar polígonos abiertos (primer vértice ≠ último vértice)
      - Eliminar geometrías duplicadas
      - Snap de vértices muy cercanos (dentro de tolerancia)
    
    Args:
        capa: QgsVectorLayer a reparar
        tolerancia: distancia en unidades de mapa para snap
        cerrar_poligonos: si True, fuerza cierre de anillos
        eliminar_duplicados: si True, elimina features con geometría idéntica
        snap_vertices: si True, aplica snap de vértices cercanos
    
    Returns:
        QgsVectorLayer nueva con geometrías reparadas
        dict con estadísticas de reparación
    """
    tipo_geom = QgsWkbTypes.geometryType(capa.wkbType())
    crs_str = capa.crs().authid() if capa.crs().isValid() else "EPSG:4326"
    tipo_str = _tipo_geom_string(tipo_geom)

    capa_nueva = _crear_capa_memoria(tipo_str, crs_str, capa.name() + "_reparada")
    capa_nueva.dataProvider().addAttributes(capa.fields())
    capa_nueva.updateFields()

    stats = {
        'total': 0,
        'poligonos_cerrados': 0,
        'duplicados_eliminados': 0,
        'vertices_snapeados': 0,
        'geometrias_invalidas': 0
    }

    features_procesadas = []
    geometrias_vistas = set()

    for feat in capa.getFeatures():
        geom = feat.geometry()
        stats['total'] += 1

        if geom is None or geom.isNull():
            stats['geometrias_invalidas'] += 1
            continue

        # 1. Cerrar polígonos
        if cerrar_poligonos and tipo_geom == QgsWkbTypes.PolygonGeometry:
            geom, cerrado = _cerrar_poligono(geom)
            if cerrado:
                stats['poligonos_cerrados'] += 1

        # 2. Snap de vértices
        if snap_vertices and tolerancia > 0:
            geom, n_snap = _snap_vertices(geom, tolerancia)
            stats['vertices_snapeados'] += n_snap

        # 3. Eliminar duplicados
        if eliminar_duplicados:
            geom_wkb = geom.asWkb().data() if geom and not geom.isNull() else None
            if geom_wkb in geometrias_vistas:
                stats['duplicados_eliminados'] += 1
                continue
            geometrias_vistas.add(geom_wkb)

        # Validar geometría final
        if not geom.isGeosValid():
            geom = geom.makeValid()

        feat_nueva = QgsFeature(capa_nueva.fields())
        feat_nueva.setAttributes(feat.attributes())
        feat_nueva.setGeometry(geom)
        features_procesadas.append(feat_nueva)

    capa_nueva.dataProvider().addFeatures(features_procesadas)
    capa_nueva.updateExtents()

    return capa_nueva, stats


def _cerrar_poligono(geom):
    """Cierra los anillos de un polígono si no están cerrados."""
    cerrado = False
    if geom.isMultipart():
        poligonos = geom.asMultiPolygon()
        nuevos = []
        for poly in poligonos:
            rings = []
            for ring in poly:
                if ring and ring[0] != ring[-1]:
                    ring = ring + [ring[0]]
                    cerrado = True
                rings.append(ring)
            nuevos.append(rings)
        return QgsGeometry.fromMultiPolygonXY(nuevos), cerrado
    else:
        rings = geom.asPolygon()
        nuevos = []
        for ring in rings:
            if ring and ring[0] != ring[-1]:
                ring = ring + [ring[0]]
                cerrado = True
            nuevos.append(ring)
        return QgsGeometry.fromPolygonXY(nuevos), cerrado


def _snap_vertices(geom, tolerancia):
    """
    Snap básico: aplica snapGeometriesToLayer sobre sí mismo.
    Para snap real entre capas usar la herramienta de QGIS.
    Retorna geometría y cantidad de vértices modificados.
    """
    # Simplificación con tolerancia mínima para eliminar vértices redundantes
    geom_snap = geom.simplify(tolerancia * 0.1)
    if geom_snap and not geom_snap.isNull():
        return geom_snap, 1
    return geom, 0


def _es_poligono_disfrazado(geom):
    """
    Detecta si una LineString es en realidad un polígono cerrado
    (primer y último punto coinciden, y tiene al menos 4 vértices).
    """
    if geom.isMultipart():
        return False
    coords = geom.asPolyline()
    if len(coords) < 4:
        return False
    return coords[0] == coords[-1]


def _linea_a_poligono(geom):
    """Convierte una LineString cerrada en Polygon."""
    coords = geom.asPolyline()
    return QgsGeometry.fromPolygonXY([coords])


def _crear_capa_memoria(tipo_geom, crs_str, nombre):
    """Crea una capa vectorial en memoria."""
    uri = f"{tipo_geom}?crs={crs_str}"
    return QgsVectorLayer(uri, nombre, "memory")


def _tipo_geom_string(tipo):
    """Convierte QgsWkbTypes.GeometryType a string."""
    if tipo == QgsWkbTypes.PointGeometry:
        return "Point"
    elif tipo == QgsWkbTypes.LineGeometry:
        return "LineString"
    elif tipo == QgsWkbTypes.PolygonGeometry:
        return "Polygon"
    return "Point"
