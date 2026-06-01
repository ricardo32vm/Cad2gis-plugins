# 📐 CAD2GIS Georeferencer — Plugin QGIS

> Plugin QGIS para georreferenciar capas vectoriales provenientes de AutoCAD mediante transformación afín con puntos homólogos, con separación de geometrías mixtas y reparación topológica.
> Desarrollado en la UTN Facultad Regional Villa María.

---

## 📋 Descripción

Las capas exportadas desde AutoCAD (SHP/DXF) suelen llegar sin sistema de referencia asignado, con geometrías mezcladas en una sola capa y con defectos topológicos típicos del dibujo CAD. `CAD2GIS Georeferencer` resuelve ese flujo completo dentro de QGIS.

El usuario marca puntos homólogos entre la capa CAD y una capa de referencia ya georreferenciada; el plugin calcula la transformación afín por mínimos cuadrados y la aplica simultáneamente a todas las capas seleccionadas.

**Características principales:**
- Transformación afín 2D por mínimos cuadrados a partir de puntos homólogos
- Marcado interactivo de puntos homólogos por clic en el mapa
- Aplicación simultánea de la transformación a múltiples capas
- Reporte del error cuadrático medio (RMS) residual del ajuste
- Separación de geometrías mixtas (puntos, líneas y polígonos) en capas independientes
- Reparación topológica básica: cierre de polígonos, vértices casi coincidentes, líneas duplicadas

---

## 🧮 Modelo de transformación

La transformación afín 2D se calcula resolviendo, por mínimos cuadrados, el sistema:

```
X = a·x + b·y + c
Y = d·x + e·y + f
```

En forma matricial:

```
[X]   [a b c] [x]
[Y] = [d e f] [y]
              [1]
```

Se requieren **al menos 3 pares de puntos homólogos** no colineales. Con más de 3 puntos, el ajuste por mínimos cuadrados minimiza el error residual, que se reporta como RMS.

---

## 🛠️ Requisitos

| Requisito | Versión mínima |
|---|---|
| QGIS | 3.16 |
| Python | 3.7+ |
| numpy | 1.17+ |

> Usa las APIs de QGIS (`qgis.core`) y numpy para el cálculo matricial.

---

## 🚀 Instalación

1. Clonar o descargar el repositorio:

```bash
git clone https://github.com/utnfrvm/cad2gis.git
```

2. Copiar la carpeta `cad2gis_plugin` a la carpeta de plugins de QGIS:

```
# Windows
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\

# Linux
~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
```

3. En QGIS → **Complementos** → **Administrar e instalar complementos** → activar **CAD2GIS Georeferencer**.

---

## 📁 Estructura

```
cad2gis_plugin/
├── __init__.py
├── cad2gis_plugin.py          Entrada del plugin
├── cad2gis_dialog.py          Interfaz de usuario
├── transform_engine.py        Motor de transformación afín (mínimos cuadrados)
├── geometry_tools.py          Separación de geometrías y reparación topológica
├── map_tools.py               Herramientas de clic para puntos homólogos
└── metadata.txt
```

---

## 💡 Uso básico

1. Cargar en QGIS la capa CAD (sin georreferenciar) y una capa de referencia georreferenciada.
2. Activar el plugin desde **Complementos → CAD2GIS Georeferencer**.
3. Marcar pares de puntos homólogos: un punto en la capa CAD y su correspondiente en la capa de referencia (mínimo 3 pares).
4. Calcular la transformación. El plugin muestra el error RMS del ajuste.
5. Seleccionar las capas a transformar y aplicar.
6. Opcionalmente, usar las herramientas de separación de geometrías y reparación topológica sobre las capas resultantes.

Consultá el **manual** (PDF incluido en el repositorio) para el detalle de cada paso.

---

## 🧩 Lugar en la suite de plugins

`CAD2GIS Georeferencer` es el **Nivel 0** de la suite de herramientas para redes eléctricas: prepara y georreferencia los datos CAD de origen para que puedan usarse luego en los plugins de trazado, topología y análisis.

| Plugin | Nivel |
|---|---|
| **CAD2GIS Georeferencer** | 0 — preparación y georreferenciación de datos CAD |
| [`crear_red_electrica`](https://github.com/ricardo32vm/crear-red-electrica) | Trazado de red MT |
| [`red_bt`](https://github.com/ricardo32vm/crear-red-bt) | Trazado de red BT |
| [`electric_network_tools`](https://github.com/ricardo32vm/electric-network-tools) | Topología y análisis de fallas |

---

## 🗺️ Contexto de aplicación

Desarrollado para preparar la cartografía CAD de cooperativas eléctricas de la Provincia de Córdoba, Argentina, como paso previo a su análisis en un entorno SIG.

---

## 👨‍💻 Autoría

**UTN Facultad Regional Villa María**
📍 Villa María, Córdoba, Argentina

---

## 📄 Licencia

[GPL v2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html) — compatible con la licencia estándar de plugins QGIS.
