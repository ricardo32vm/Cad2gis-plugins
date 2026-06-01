# -*- coding: utf-8 -*-
def classFactory(iface):
    from .cad2gis_plugin import CAD2GISPlugin
    return CAD2GISPlugin(iface)
