from qgis.core import QgsCoordinateTransformContext



def generate_infills(gap_layer, all_lines, polygon_geom, dem_layer, crs_authid, infill_output_path):
    from qgis.core import (
        QgsVectorLayer, QgsFields, QgsField, QgsFeature, QgsGeometry,
        QgsVectorFileWriter, QgsPointXY
    )
    from qgis import processing
    from PyQt5.QtCore import QVariant
    import math
    import os

    infill_fields = QgsFields()
    infill_fields.append(QgsField("id", QVariant.Int))

    infill_layer = QgsVectorLayer(f"LineString?crs={crs_authid}", "infill_lines", "memory")
    infill_provider = infill_layer.dataProvider()
    infill_provider.addAttributes(infill_fields)
    infill_layer.updateFields()

    features = gap_layer.getFeatures()
    line_geometries = [geom if isinstance(geom, QgsGeometry) else QgsGeometry.fromWkt(geom.asWkt()) for _, geom, _ in all_lines]

    count = 0
    for gap in features:
        centroid = gap.geometry().centroid().asPoint()

        min_dist = float("inf")
        nearest_geom = None
        for geom in line_geometries:
            dist = geom.distance(QgsGeometry.fromPointXY(centroid))
            if dist < min_dist:
                min_dist = dist
                nearest_geom = geom

        if not nearest_geom:
            continue

        seg = nearest_geom.asPolyline() if not nearest_geom.isMultipart() else nearest_geom.asMultiPolyline()[0]
        if len(seg) < 2:
            continue

        dx = seg[-1].x() - seg[0].x()
        dy = seg[-1].y() - seg[0].y()
        angle = math.atan2(dy, dx)
        ux = math.cos(angle)
        uy = math.sin(angle)

        # Sample depth at centroid
        depth = 5
        sample_layer = QgsVectorLayer(f"Point?crs={crs_authid}", "sample", "memory")
        sample_dp = sample_layer.dataProvider()
        sample_feat = QgsFeature()
        sample_feat.setGeometry(QgsGeometry.fromPointXY(centroid))
        sample_dp.addFeature(sample_feat)
        sample_layer.updateExtents()

        sampled = processing.run("native:rastersampling", {
            'INPUT': sample_layer,
            'RASTERCOPY': dem_layer,
            'COLUMN_PREFIX': 'z_',
            'OUTPUT': 'memory:sampled'
        })['OUTPUT']
        for f in sampled.getFeatures():
            val = f['z_1']
            if val is not None:
                depth = abs(val)

        # Offset perpendicular
        nx, ny = -uy, ux
        offset_centroid = QgsPointXY(centroid.x() + nx * (depth / 2), centroid.y() + ny * (depth / 2))

        # Minimum bounding box (OBB)
        temp_layer = QgsVectorLayer("Polygon?crs=" + crs_authid, "temp", "memory")
        temp_provider = temp_layer.dataProvider()
        temp_feat = QgsFeature()
        temp_feat.setGeometry(gap.geometry())
        temp_provider.addFeature(temp_feat)
        temp_layer.updateExtents()

        obb_result = processing.run("qgis:minimumboundinggeometry", {
            'INPUT': temp_layer,
            'TYPE': 1,
            'OUTPUT': 'memory:obb'
        })['OUTPUT']
        
        try:
            obb_feat = next(obb_result.getFeatures())
            segs = obb_feat.geometry().asPolygon()[0]
        except Exception as e:
            print(f"⚠️ Failed to get OBB for gap feature: {e}")
            continue

        maxlen, ux, uy = 0, 1, 0
        for j in range(len(segs) - 1):
            dx = segs[j + 1].x() - segs[j].x()
            dy = segs[j + 1].y() - segs[j].y()
            l = math.hypot(dx, dy)
            if l > maxlen:
                maxlen = l
                ux, uy = dx / l, dy / l
        half = (maxlen + 200) / 2

        p1 = QgsPointXY(offset_centroid.x() - ux * half, offset_centroid.y() - uy * half)
        p2 = QgsPointXY(offset_centroid.x() + ux * half, offset_centroid.y() + uy * half)
        infill_geom = QgsGeometry.fromPolylineXY([p1, p2])

        f = QgsFeature(infill_layer.fields())
        f.setGeometry(infill_geom)
        f.setAttribute("id", count)
        infill_provider.addFeature(f)
        count += 1

    infill_layer.updateExtents()

    # Ensure path ends with .shp
    if not infill_output_path.lower().endswith(".shp"):
        infill_output_path += ".shp"

    QgsVectorFileWriter.writeAsVectorFormat(
        infill_layer,
        infill_output_path,
        "UTF-8",
        infill_layer.crs(),
        "ESRI Shapefile")


    print(f"🧩 {count} infill lines saved to: {infill_output_path}")
    return infill_layer
