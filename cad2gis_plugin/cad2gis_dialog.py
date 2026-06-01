# -*- coding: utf-8 -*-
"""
Diálogo principal del plugin CAD2GIS Georeferencer.
Tres pestañas:
  1. Separar geometrías (CAD mixto → puntos/líneas/polígonos)
  2. Georreferenciar (puntos homólogos + transformación afín)
  3. Reparar topología
"""

import json
import os

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsWkbTypes, QgsMapLayerProxyModel
)
from qgis.gui import QgsProjectionSelectionWidget
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QCheckBox, QDoubleSpinBox,
    QGroupBox, QFileDialog, QMessageBox, QSplitter,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QProgressBar, QTextEdit, QSpinBox
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QColor, QIcon

from .transform_engine import AfinTransform, aplicar_transformacion_a_capas
from .geometry_tools import separar_geometrias, reparar_topologia
from .map_tools import PickPointTool, PointPairManager


class CAD2GISDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.transform = AfinTransform()
        self.pair_manager = PointPairManager(self.canvas)
        self.pick_tool = None
        self.pick_mode = None   # 'src' o 'dst'
        self.pending_src = None # punto fuente esperando su par destino

        self.setWindowTitle("CAD2GIS Georeferencer — UTN FRVM")
        self.setMinimumSize(700, 550)
        self._build_ui()
        self._populate_layers()

    # ─────────────────────────────────────────────────────────────
    # UI CONSTRUCTION
    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_separar(),      "1. Separar geometrías")
        self.tabs.addTab(self._tab_georeferenciar(), "2. Georreferenciar")
        self.tabs.addTab(self._tab_topologia(),    "3. Reparar topología")
        main_layout.addWidget(self.tabs)

        # Barra de estado
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #333; font-style: italic; padding: 4px;")
        main_layout.addWidget(self.status_label)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.close)
        main_layout.addWidget(btn_cerrar)

    # ── TAB 1: SEPARAR GEOMETRÍAS ──────────────────────────────

    def _tab_separar(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel(
            "Separa una capa con geometrías mixtas proveniente de AutoCAD "
            "en capas independientes de puntos, líneas y polígonos.\n"
            "Las líneas cerradas con ≥4 vértices se convierten automáticamente a polígonos."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        grp = QGroupBox("Capa CAD a separar")
        grp_layout = QVBoxLayout(grp)

        self.cmb_capa_mixta = QComboBox()
        grp_layout.addWidget(QLabel("Capa de entrada (sin CRS o CRS local):"))
        grp_layout.addWidget(self.cmb_capa_mixta)
        layout.addWidget(grp)

        self.chk_agregar_mapa = QCheckBox("Agregar capas resultantes al mapa")
        self.chk_agregar_mapa.setChecked(True)
        layout.addWidget(self.chk_agregar_mapa)

        btn = QPushButton("Separar geometrías")
        btn.setStyleSheet("background-color: #2196F3; color: white; padding: 6px;")
        btn.clicked.connect(self._separar_geometrias)
        layout.addWidget(btn)

        self.txt_sep_resultado = QTextEdit()
        self.txt_sep_resultado.setReadOnly(True)
        self.txt_sep_resultado.setMaximumHeight(120)
        layout.addWidget(self.txt_sep_resultado)

        layout.addStretch()
        return w

    # ── TAB 2: GEORREFERENCIAR ─────────────────────────────────

    def _tab_georeferenciar(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        # Selección de capas
        grp_capas = QGroupBox("Capas a transformar")
        grp_layout = QVBoxLayout(grp_capas)

        grp_layout.addWidget(QLabel("Capa de referencia (con CRS real):"))
        self.cmb_ref = QComboBox()
        grp_layout.addWidget(self.cmb_ref)

        grp_layout.addWidget(QLabel("Capas a transformar (selección múltiple):"))
        self.lst_capas = QListWidget()
        self.lst_capas.setSelectionMode(QAbstractItemView.MultiSelection)
        self.lst_capas.setMaximumHeight(100)
        grp_layout.addWidget(self.lst_capas)

        grp_layout.addWidget(QLabel("CRS de destino:"))
        self.crs_widget = QgsProjectionSelectionWidget()
        self.crs_widget.setCrs(QgsCoordinateReferenceSystem("EPSG:22194"))  # Gauss-Krüger Faja 4
        grp_layout.addWidget(self.crs_widget)

        layout.addWidget(grp_capas)

        # Tabla de puntos homólogos
        grp_puntos = QGroupBox("Pares de puntos homólogos")
        grp_puntos_layout = QVBoxLayout(grp_puntos)

        # Botones de captura
        btn_row = QHBoxLayout()

        self.btn_pick_src = QPushButton("📍 Marcar punto en CAD")
        self.btn_pick_src.setCheckable(True)
        self.btn_pick_src.setStyleSheet("QPushButton:checked { background-color: #FF5722; color: white; }")
        self.btn_pick_src.clicked.connect(self._activar_pick_src)
        btn_row.addWidget(self.btn_pick_src)

        self.btn_pick_dst = QPushButton("📍 Marcar punto en referencia")
        self.btn_pick_dst.setCheckable(True)
        self.btn_pick_dst.setEnabled(False)
        self.btn_pick_dst.setStyleSheet("QPushButton:checked { background-color: #1976D2; color: white; }")
        self.btn_pick_dst.clicked.connect(self._activar_pick_dst)
        btn_row.addWidget(self.btn_pick_dst)

        grp_puntos_layout.addLayout(btn_row)

        # Estado de captura
        self.lbl_pick_estado = QLabel("→ Primero marcá un punto en la capa CAD")
        self.lbl_pick_estado.setStyleSheet("color: #666; font-style: italic;")
        grp_puntos_layout.addWidget(self.lbl_pick_estado)

        # Tabla
        self.tabla_pares = QTableWidget(0, 5)
        self.tabla_pares.setHorizontalHeaderLabels(
            ["#", "X fuente", "Y fuente", "X destino", "Y destino"]
        )
        self.tabla_pares.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla_pares.setMaximumHeight(160)
        grp_puntos_layout.addWidget(self.tabla_pares)

        btn_row2 = QHBoxLayout()
        btn_eliminar = QPushButton("Eliminar seleccionado")
        btn_eliminar.clicked.connect(self._eliminar_par)
        btn_row2.addWidget(btn_eliminar)

        btn_limpiar = QPushButton("Limpiar todos")
        btn_limpiar.clicked.connect(self._limpiar_pares)
        btn_row2.addWidget(btn_limpiar)

        btn_guardar = QPushButton("💾 Guardar pares")
        btn_guardar.clicked.connect(self._guardar_pares)
        btn_row2.addWidget(btn_guardar)

        btn_cargar = QPushButton("📂 Cargar pares")
        btn_cargar.clicked.connect(self._cargar_pares)
        btn_row2.addWidget(btn_cargar)

        grp_puntos_layout.addLayout(btn_row2)
        layout.addWidget(grp_puntos)

        # RMS y transformar
        self.lbl_rms = QLabel("RMS: — (necesitás al menos 3 pares)")
        self.lbl_rms.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self.lbl_rms)

        btn_transformar = QPushButton("✅ Aplicar transformación a capas seleccionadas")
        btn_transformar.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px; font-weight: bold;")
        btn_transformar.clicked.connect(self._aplicar_transformacion)
        layout.addWidget(btn_transformar)

        return w

    # ── TAB 3: REPARAR TOPOLOGÍA ───────────────────────────────

    def _tab_topologia(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel(
            "Repara problemas topológicos típicos de capas importadas desde AutoCAD:\n"
            "polígonos no cerrados, geometrías duplicadas y vértices casi coincidentes."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        grp = QGroupBox("Configuración")
        grp_layout = QVBoxLayout(grp)

        grp_layout.addWidget(QLabel("Capa a reparar:"))
        self.cmb_reparar = QComboBox()
        grp_layout.addWidget(self.cmb_reparar)

        self.chk_cerrar = QCheckBox("Cerrar polígonos abiertos")
        self.chk_cerrar.setChecked(True)
        grp_layout.addWidget(self.chk_cerrar)

        self.chk_duplicados = QCheckBox("Eliminar geometrías duplicadas")
        self.chk_duplicados.setChecked(True)
        grp_layout.addWidget(self.chk_duplicados)

        self.chk_snap = QCheckBox("Snap de vértices cercanos")
        self.chk_snap.setChecked(True)
        grp_layout.addWidget(self.chk_snap)

        tol_row = QHBoxLayout()
        tol_row.addWidget(QLabel("Tolerancia snap:"))
        self.spin_tol = QDoubleSpinBox()
        self.spin_tol.setRange(0.0001, 100.0)
        self.spin_tol.setValue(0.001)
        self.spin_tol.setDecimals(4)
        self.spin_tol.setSuffix(" m")
        tol_row.addWidget(self.spin_tol)
        tol_row.addStretch()
        grp_layout.addLayout(tol_row)

        layout.addWidget(grp)

        btn = QPushButton("Reparar topología")
        btn.setStyleSheet("background-color: #FF9800; color: white; padding: 6px;")
        btn.clicked.connect(self._reparar_topologia)
        layout.addWidget(btn)

        self.txt_topo_resultado = QTextEdit()
        self.txt_topo_resultado.setReadOnly(True)
        self.txt_topo_resultado.setMaximumHeight(150)
        layout.addWidget(self.txt_topo_resultado)

        layout.addStretch()
        return w

    # ─────────────────────────────────────────────────────────────
    # LOGIC
    # ─────────────────────────────────────────────────────────────

    def _populate_layers(self):
        """Llena los combos y lista con las capas vectoriales del proyecto."""
        layers = [l for l in QgsProject.instance().mapLayers().values()
                  if isinstance(l, QgsVectorLayer)]

        for cmb in [self.cmb_capa_mixta, self.cmb_ref, self.cmb_reparar]:
            cmb.clear()
            for l in layers:
                cmb.addItem(l.name(), l.id())

        self.lst_capas.clear()
        for l in layers:
            item = QListWidgetItem(l.name())
            item.setData(Qt.UserRole, l.id())
            self.lst_capas.addItem(item)

    def _get_layer_by_combo(self, cmb):
        lid = cmb.currentData()
        if lid:
            return QgsProject.instance().mapLayer(lid)
        return None

    # ── SEPARAR ────────────────────────────────────────────────

    def _separar_geometrias(self):
        capa = self._get_layer_by_combo(self.cmb_capa_mixta)
        if not capa:
            QMessageBox.warning(self, "Error", "Seleccioná una capa.")
            return

        capas_sep = separar_geometrias(
            capa,
            capa.crs().authid() if capa.crs().isValid() else "EPSG:4326"
        )

        resumen = []
        for tipo, c in capas_sep.items():
            if self.chk_agregar_mapa.isChecked():
                QgsProject.instance().addMapLayer(c)
            resumen.append(f"  {tipo}: {c.featureCount()} objetos")

        self.txt_sep_resultado.setText(
            f"Separación completada para '{capa.name()}':\n" + "\n".join(resumen)
        )
        self._set_status(f"Capa separada en {len(capas_sep)} tipo(s) de geometría.")

    # ── GEORREFERENCIAR ────────────────────────────────────────

    def _activar_pick_src(self):
        """Activa la herramienta para marcar punto fuente en CAD."""
        self.btn_pick_dst.setChecked(False)
        if self.btn_pick_src.isChecked():
            self.pick_tool = PickPointTool(self.canvas)
            self.pick_tool.point_picked.connect(self._on_src_picked)
            self.canvas.setMapTool(self.pick_tool)
            self.lbl_pick_estado.setText("→ Hacé clic sobre un punto reconocible en la capa CAD")
            self.lbl_pick_estado.setStyleSheet("color: #FF5722; font-style: italic;")
        else:
            self.canvas.unsetMapTool(self.pick_tool)

    def _activar_pick_dst(self):
        """Activa la herramienta para marcar punto destino en referencia."""
        self.btn_pick_src.setChecked(False)
        if self.btn_pick_dst.isChecked():
            self.pick_tool = PickPointTool(self.canvas)
            self.pick_tool.point_picked.connect(self._on_dst_picked)
            self.canvas.setMapTool(self.pick_tool)
            self.lbl_pick_estado.setText("→ Ahora hacé clic en el punto homólogo en la capa de referencia")
            self.lbl_pick_estado.setStyleSheet("color: #1976D2; font-style: italic;")
        else:
            self.canvas.unsetMapTool(self.pick_tool)

    def _on_src_picked(self, x, y):
        """Callback cuando el usuario marcó el punto fuente."""
        self.pending_src = (x, y)
        self.btn_pick_src.setChecked(False)
        self.btn_pick_dst.setEnabled(True)
        self.btn_pick_dst.setChecked(False)
        self.canvas.unsetMapTool(self.pick_tool)
        self.lbl_pick_estado.setText(
            f"→ Punto CAD capturado ({x:.2f}, {y:.2f}). "
            f"Ahora marcá el punto homólogo en la referencia."
        )
        self.lbl_pick_estado.setStyleSheet("color: #FF9800; font-style: italic;")

    def _on_dst_picked(self, X, Y):
        """Callback cuando el usuario marcó el punto destino. Completa el par."""
        if self.pending_src is None:
            return

        src = self.pending_src
        dst = (X, Y)
        self.pair_manager.agregar_par(src, dst)
        self._agregar_fila_tabla(src, dst)

        self.pending_src = None
        self.btn_pick_dst.setEnabled(False)
        self.btn_pick_dst.setChecked(False)
        self.canvas.unsetMapTool(self.pick_tool)
        self.lbl_pick_estado.setText(
            f"→ Par agregado. Total: {len(self.pair_manager.pares)} pares. "
            f"Podés agregar más o aplicar la transformación."
        )
        self.lbl_pick_estado.setStyleSheet("color: #4CAF50; font-style: italic;")
        self._actualizar_rms()

    def _agregar_fila_tabla(self, src, dst):
        n = self.tabla_pares.rowCount()
        self.tabla_pares.insertRow(n)
        self.tabla_pares.setItem(n, 0, QTableWidgetItem(str(n + 1)))
        self.tabla_pares.setItem(n, 1, QTableWidgetItem(f"{src[0]:.4f}"))
        self.tabla_pares.setItem(n, 2, QTableWidgetItem(f"{src[1]:.4f}"))
        self.tabla_pares.setItem(n, 3, QTableWidgetItem(f"{dst[0]:.6f}"))
        self.tabla_pares.setItem(n, 4, QTableWidgetItem(f"{dst[1]:.6f}"))

    def _eliminar_par(self):
        fila = self.tabla_pares.currentRow()
        if fila >= 0:
            self.pair_manager.eliminar_par(fila)
            self.tabla_pares.removeRow(fila)
            self._actualizar_rms()

    def _limpiar_pares(self):
        self.pair_manager.limpiar()
        self.tabla_pares.setRowCount(0)
        self.lbl_rms.setText("RMS: — (necesitás al menos 3 pares)")

    def _actualizar_rms(self):
        """Recalcula y muestra el RMS con los pares actuales."""
        pares = self.pair_manager.pares
        if len(pares) < 3:
            self.lbl_rms.setText(f"RMS: — ({len(pares)}/3 pares mínimos)")
            return
        ok, msg = self.transform.calcular(
            self.pair_manager.get_src_points(),
            self.pair_manager.get_dst_points()
        )
        if ok:
            color = "#4CAF50" if self.transform.rms_error < 1.0 else "#FF9800"
            self.lbl_rms.setText(f"RMS: {self.transform.rms_error:.4f} m  ✓")
            self.lbl_rms.setStyleSheet(f"font-weight: bold; color: {color}; padding: 4px;")

    def _guardar_pares(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar pares de puntos", "", "JSON (*.json)"
        )
        if path:
            with open(path, 'w') as f:
                json.dump(self.pair_manager.exportar(), f, indent=2)
            self._set_status(f"Pares guardados en {os.path.basename(path)}")

    def _cargar_pares(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Cargar pares de puntos", "", "JSON (*.json)"
        )
        if path:
            with open(path, 'r') as f:
                pares = json.load(f)
            self._limpiar_pares()
            for par in pares:
                self.pair_manager.agregar_par(par['src'], par['dst'])
                self._agregar_fila_tabla(par['src'], par['dst'])
            self._actualizar_rms()
            self._set_status(f"Cargados {len(pares)} pares desde {os.path.basename(path)}")

    def _aplicar_transformacion(self):
        """Calcula la transformación y la aplica a todas las capas seleccionadas."""
        if len(self.pair_manager.pares) < 3:
            QMessageBox.warning(self, "Faltan puntos",
                                "Necesitás al menos 3 pares de puntos homólogos.")
            return

        # Calcular transformación
        ok, msg = self.transform.calcular(
            self.pair_manager.get_src_points(),
            self.pair_manager.get_dst_points()
        )
        if not ok:
            QMessageBox.critical(self, "Error en transformación", msg)
            return

        # Capas seleccionadas
        capas_sel = []
        for item in self.lst_capas.selectedItems():
            lid = item.data(Qt.UserRole)
            l = QgsProject.instance().mapLayer(lid)
            if l:
                capas_sel.append(l)

        if not capas_sel:
            QMessageBox.warning(self, "Sin capas", "Seleccioná al menos una capa para transformar.")
            return

        crs_dst = self.crs_widget.crs()
        if not crs_dst.isValid():
            QMessageBox.warning(self, "CRS inválido", "Seleccioná un CRS de destino válido.")
            return

        # Aplicar
        capas_resultado = aplicar_transformacion_a_capas(capas_sel, self.transform, crs_dst)

        for c in capas_resultado:
            QgsProject.instance().addMapLayer(c)

        self.iface.mapCanvas().refresh()
        self._set_status(
            f"Transformación aplicada a {len(capas_resultado)} capa(s). "
            f"RMS: {self.transform.rms_error:.4f} m"
        )
        QMessageBox.information(
            self, "Transformación completada",
            f"Se transformaron {len(capas_resultado)} capa(s).\n"
            f"RMS residual: {self.transform.rms_error:.4f} m\n"
            f"Puntos de control usados: {self.transform.n_points}"
        )

    # ── REPARAR TOPOLOGÍA ──────────────────────────────────────

    def _reparar_topologia(self):
        capa = self._get_layer_by_combo(self.cmb_reparar)
        if not capa:
            QMessageBox.warning(self, "Error", "Seleccioná una capa.")
            return

        capa_rep, stats = reparar_topologia(
            capa,
            tolerancia=self.spin_tol.value(),
            cerrar_poligonos=self.chk_cerrar.isChecked(),
            eliminar_duplicados=self.chk_duplicados.isChecked(),
            snap_vertices=self.chk_snap.isChecked()
        )

        QgsProject.instance().addMapLayer(capa_rep)
        self.iface.mapCanvas().refresh()

        resumen = (
            f"Reparación de '{capa.name()}':\n"
            f"  Objetos procesados:      {stats['total']}\n"
            f"  Polígonos cerrados:      {stats['poligonos_cerrados']}\n"
            f"  Duplicados eliminados:   {stats['duplicados_eliminados']}\n"
            f"  Vértices snapeados:      {stats['vertices_snapeados']}\n"
            f"  Geometrías inválidas:    {stats['geometrias_invalidas']}\n"
            f"  → Capa resultado: '{capa_rep.name()}'"
        )
        self.txt_topo_resultado.setText(resumen)
        self._set_status(f"Topología reparada. Ver capa '{capa_rep.name()}'.")

    # ─────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────

    def _set_status(self, msg):
        self.status_label.setText(msg)

    def closeEvent(self, event):
        """Limpia herramientas y marcadores al cerrar."""
        self.pair_manager.limpiar()
        if self.pick_tool:
            self.canvas.unsetMapTool(self.pick_tool)
        super().closeEvent(event)

    def showEvent(self, event):
        """Actualiza las capas cuando se abre el diálogo."""
        self._populate_layers()
        super().showEvent(event)
