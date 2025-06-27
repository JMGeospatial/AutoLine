from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsFields, QgsField
)
import processing
import math
import os
from PyQt5.QtCore import QVariant

def build_coverage_layer(all_lines, crs_authid, buffer_geom, dem_layer, coverage_path,
                         beam_angle_deg,sampling_interval=25):
    buffer_union_layer = QgsVectorLayer(f"Polygon?crs={crs_authid}", "buffer_union", "memory")
    buffer_provider = buffer_union_layer.dataProvider()

    # Add one feature per input line to preserve overlaps
    id_field = QgsField("line_id", QVariant.Int)
    buffer_union_layer.dataProvider().addAttributes([id_field])
    buffer_union_layer.updateFields()

    valid_feature_count = 0

    for line_id, (swath, geom, _) in enumerate(all_lines):
        if geom.isEmpty() or not geom.isGeosValid():
            continue

        temp_line = QgsVectorLayer(f"LineString?crs={crs_authid}", "temp_line", "memory")
        prov = temp_line.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(geom)
        prov.addFeature(feat)
        temp_line.updateExtents()

        points_layer = processing.run("native:pointsalonglines", {
            'INPUT': temp_line,
            'DISTANCE': sampling_interval,
            'OUTPUT': 'memory:points'
        })['OUTPUT']
        pts = [f.geometry().asPoint() for f in points_layer.getFeatures()]
        if len(pts) < 2:
            continue

        midpoint_layer = QgsVectorLayer(f"Point?crs={crs_authid}", "midpoints", "memory")
        dp = midpoint_layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        dp.addAttributes(fields)
        midpoint_layer.updateFields()

        midpoints = []
        for i in range(len(pts) - 1):
            mid = QgsPointXY((pts[i].x() + pts[i + 1].x()) / 2, (pts[i].y() + pts[i + 1].y()) / 2)
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(mid))
            f.setAttributes([i])
            dp.addFeature(f)
            midpoints.append((i, mid))

        midpoint_layer.updateExtents()

        sampled = processing.run("native:rastersampling", {
            'INPUT': midpoint_layer,
            'RASTERCOPY': dem_layer,
            'COLUMN_PREFIX': 'z_',
            'OUTPUT': 'memory:sampled'
        })['OUTPUT']

        depth_dict = {}
        last_valid_depth = 5  # fallback
        for f in sampled.getFeatures():
            idx = f['id']
            z = f['z_1']
            if z is not None:
                last_valid_depth = abs(z)
                depth_dict[idx] = last_valid_depth
            else:
                depth_dict[idx] = last_valid_depth  # fallback

        segment_buffers = []
        for i in range(len(pts) - 1):
            depth = depth_dict.get(i, last_valid_depth)
            swath_width = 2 * depth * math.tan(math.radians(beam_angle_deg / 2))
            if swath_width <= 0:
                continue
            segment = QgsGeometry.fromPolylineXY([pts[i], pts[i + 1]])
            buffer = segment.buffer(swath_width / 2, 3)
            if buffer and not buffer.isEmpty():
                segment_buffers.append(buffer)

        if not segment_buffers:
            continue

        union = QgsGeometry.unaryUnion(segment_buffers)
        if union and not union.isEmpty():
            f = QgsFeature(buffer_union_layer.fields())
            f.setGeometry(union)
            f.setAttribute("line_id", line_id)
            buffer_provider.addFeature(f)
            valid_feature_count += 1

    buffer_union_layer.updateExtents()
    print(f"✅ {valid_feature_count} per-line coverage polygons created with preserved overlaps")

    out_path = coverage_path
    QgsVectorFileWriter.writeAsVectorFormat(
        buffer_union_layer, out_path, "UTF-8", buffer_union_layer.crs(), "ESRI Shapefile"
    )
    print(f"💾 Coverage layer saved to: {out_path}")
    return buffer_union_layer

def find_coverage_gaps(polygon_layer, coverage_layer):
    print(f"🟡 Polygon features: {polygon_layer.featureCount()}")
    print(f"🟡 Coverage features: {coverage_layer.featureCount()}")

    gap_raw = processing.run("native:difference", {
        'INPUT': polygon_layer,
        'OVERLAY': coverage_layer,
        'OUTPUT': 'memory:gap_raw'
    })['OUTPUT']

    gap = processing.run("native:multiparttosingleparts", {
        'INPUT': gap_raw,
        'OUTPUT': 'memory:gap'
    })['OUTPUT']
    return gap
