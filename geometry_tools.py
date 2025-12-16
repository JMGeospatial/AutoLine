from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY
)
import processing
import math

def offset_line(line_geom, offset_dist, crs_authid):
    temp_layer = QgsVectorLayer(f"LineString?crs={crs_authid}", "temp", "memory")
    prov = temp_layer.dataProvider()
    feat = QgsFeature()
    feat.setGeometry(line_geom)
    prov.addFeature(feat)
    temp_layer.updateExtents()
    return processing.run("native:offsetline", {
        'INPUT': temp_layer,
        'DISTANCE': offset_dist,
        'SEGMENTS': 1,
        'JOIN_STYLE': 1,
        'MITER_LIMIT': 2,
        'OUTPUT': 'memory:offset'
    })['OUTPUT']

def extend_line_asym(geom, start_ext, end_ext, buffer_geom):
    pts = geom.asPolyline() if not geom.isMultipart() else geom.asMultiPolyline()[0]
    if len(pts) < 2:
        return geom

    p1, p2 = pts[0], pts[-1]
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length

    # Over-extend far beyond requested range
    long_start = QgsPointXY(p1.x() - ux * 1000000, p1.y() - uy * 1000000)
    long_end   = QgsPointXY(p2.x() + ux * 1000000, p2.y() + uy * 1000000)
    long_line  = QgsGeometry.fromPolylineXY([long_start, long_end])

    # Clip to buffered polygon
    clipped = long_line.intersection(buffer_geom)

    # Select longest clipped segment
    clipped_seg = clipped.asPolyline() if not clipped.isMultipart() else max(
        clipped.asMultiPolyline(), key=lambda seg: QgsGeometry.fromPolylineXY(seg).length())

    if len(clipped_seg) < 2:
        return geom

    cp1, cp2 = clipped_seg[0], clipped_seg[-1]

    # Apply asymmetric extension
    final_start = QgsPointXY(cp1.x() - ux * start_ext, cp1.y() - uy * start_ext)
    final_end   = QgsPointXY(cp2.x() + ux * end_ext, cp2.y() + uy * end_ext)

    return QgsGeometry.fromPolylineXY([final_start, final_end])


# def extend_line(geom, extension, buffer_geom):
#     pts = geom.asPolyline() if not geom.isMultipart() else geom.asMultiPolyline()[0]
#     if len(pts) < 2:
#         return None
#     p1, p2 = pts[0], pts[-1]
#     dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
#     length = math.hypot(dx, dy)
#     ux, uy = dx / length, dy / length
#     long_p1 = QgsPointXY(p1.x() - ux * 1000000, p1.y() - uy * 1000000)
#     long_p2 = QgsPointXY(p2.x() + ux * 1000000, p2.y() + uy * 1000000)
#     long_line = QgsGeometry.fromPolylineXY([long_p1, long_p2])
#     clipped = long_line.intersection(buffer_geom)
#     clipped_seg = clipped.asPolyline() if not clipped.isMultipart() else max(
#         clipped.asMultiPolyline(), key=lambda seg: QgsGeometry.fromPolylineXY(seg).length())
#     if len(clipped_seg) < 2:
#         return geom
#     cp1, cp2 = clipped_seg[0], clipped_seg[-1]
#     return QgsGeometry.fromPolylineXY([
#         QgsPointXY(cp1.x() - ux * extension, cp1.y() - uy * extension),
#         QgsPointXY(cp2.x() + ux * extension, cp2.y() + uy * extension)
#     ])

def clip_to_polygon(geom, buffer_geom):
    return geom.intersection(buffer_geom)

def buffer_line(line_geom, width, crs_authid):
    temp = QgsVectorLayer(f"LineString?crs={crs_authid}", "temp", "memory")
    prov = temp.dataProvider()
    feat = QgsFeature()
    feat.setGeometry(line_geom)
    prov.addFeature(feat)
    temp.updateExtents()
    return processing.run("native:buffer", {
        'INPUT': temp,
        'DISTANCE': width,
        'SEGMENTS': 1,
        'END_CAP_STYLE': 1,
        'JOIN_STYLE': 1,
        'MITER_LIMIT': 2,
        'DISSOLVE': False,
        'OUTPUT': 'memory:buffered'
    })['OUTPUT']
