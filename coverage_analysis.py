from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsFields, QgsField,
    QgsCoordinateReferenceSystem, QgsProject
)
import processing
import math
import os
from qgis.PyQt.QtCore import QVariant


def _ensure_shp_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        raise ValueError("Output path is empty.")
    if not path.lower().endswith(".shp"):
        path += ".shp"
    return path


def _ensure_prj_exists(shp_path: str, crs: QgsCoordinateReferenceSystem, log=None):
    """
    Some GDAL/QGIS builds may write .qpj instead of .prj, or skip .prj.
    We guarantee a .prj exists by writing it ourselves if missing.
    """
    base = os.path.splitext(shp_path)[0]
    prj_path = base + ".prj"
    qpj_path = base + ".qpj"

    # If GDAL wrote a .qpj, optionally mirror it to .prj (safe + simple)
    if os.path.exists(qpj_path) and not os.path.exists(prj_path):
        try:
            with open(qpj_path, "r", encoding="utf-8", errors="ignore") as src, \
                 open(prj_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            if log:
                log(f"ℹ️ .qpj existed; mirrored to .prj: {prj_path}")
        except Exception as e:
            if log:
                log(f"⚠️ Failed mirroring .qpj to .prj: {e}")

    # If still missing, write WKT to .prj
    if not os.path.exists(prj_path):
        wkt = crs.toWkt()
        try:
            with open(prj_path, "w", encoding="utf-8") as f:
                f.write(wkt)
            if log:
                log(f"🧷 Forced .prj written: {prj_path}")
        except Exception as e:
            if log:
                log(f"⚠️ Failed writing .prj: {e}")


def build_coverage_layer(
    all_lines, crs_authid, buffer_geom, dem_layer, coverage_path,
    beam_angle_deg, depth_sampling_interval=5, log=None
):
    # Create memory layer
    buffer_union_layer = QgsVectorLayer(f"Polygon?crs={crs_authid}", "buffer_union", "memory")
    buffer_provider = buffer_union_layer.dataProvider()

    # Fields
    buffer_provider.addAttributes([QgsField("line_id", QVariant.Int)])
    buffer_union_layer.updateFields()

    valid_feature_count = 0

    for line_id, (_swath, geom, _feat) in enumerate(all_lines):
        if not geom or geom.isEmpty() or not geom.isGeosValid():
            continue

        temp_line = QgsVectorLayer(f"LineString?crs={crs_authid}", "temp_line", "memory")
        prov = temp_line.dataProvider()
        f = QgsFeature()
        f.setGeometry(geom)
        prov.addFeature(f)
        temp_line.updateExtents()

        points_layer = processing.run("native:pointsalonglines", {
            "INPUT": temp_line,
            "DISTANCE": depth_sampling_interval,
            "OUTPUT": "memory:points"
        })["OUTPUT"]

        pts = [pf.geometry().asPoint() for pf in points_layer.getFeatures()]
        if len(pts) < 2:
            continue

        midpoint_layer = QgsVectorLayer(f"Point?crs={crs_authid}", "midpoints", "memory")
        dp = midpoint_layer.dataProvider()
        dp.addAttributes([QgsField("id", QVariant.Int)])
        midpoint_layer.updateFields()

        for i in range(len(pts) - 1):
            mid = QgsPointXY((pts[i].x() + pts[i + 1].x()) / 2, (pts[i].y() + pts[i + 1].y()) / 2)
            mf = QgsFeature()
            mf.setGeometry(QgsGeometry.fromPointXY(mid))
            mf.setAttributes([i])
            dp.addFeature(mf)

        midpoint_layer.updateExtents()

        sampled = processing.run("native:rastersampling", {
            "INPUT": midpoint_layer,
            "RASTERCOPY": dem_layer,
            "COLUMN_PREFIX": "z_",
            "OUTPUT": "memory:sampled"
        })["OUTPUT"]

        depth_dict = {}
        last_valid_depth = 5
        for sf in sampled.getFeatures():
            idx = sf["id"]
            z = sf["z_1"]
            if z is not None:
                last_valid_depth = abs(z)
            depth_dict[idx] = last_valid_depth

        segment_buffers = []
        for i in range(len(pts) - 1):
            depth = depth_dict.get(i, last_valid_depth)
            swath_width = 2 * depth * math.tan(math.radians(beam_angle_deg / 2))
            if swath_width <= 0:
                continue
            segment = QgsGeometry.fromPolylineXY([pts[i], pts[i + 1]])
            buf = segment.buffer(swath_width / 2, 3)
            if buf and not buf.isEmpty():
                segment_buffers.append(buf)

        if not segment_buffers:
            continue

        union = QgsGeometry.unaryUnion(segment_buffers)
        if union and not union.isEmpty():
            out_f = QgsFeature(buffer_union_layer.fields())
            out_f.setGeometry(union)
            out_f.setAttribute("line_id", line_id)
            buffer_provider.addFeature(out_f)
            valid_feature_count += 1

    buffer_union_layer.updateExtents()
    if log:
        log(f"✅ {valid_feature_count} per-line coverage polygons created")
    else:
        print(f"✅ {valid_feature_count} per-line coverage polygons created")

    # ---- WRITE ----
    out_path = _ensure_shp_path(coverage_path)

    # Robust CRS creation
    crs = QgsCoordinateReferenceSystem()
    if not crs.createFromUserInput(crs_authid):
        raise ValueError(f"Invalid CRS user input/authid: {crs_authid}")

    buffer_union_layer.setCrs(crs)

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "ESRI Shapefile"
    opts.fileEncoding = "UTF-8"

    err, msg = QgsVectorFileWriter.writeAsVectorFormatV2(
        buffer_union_layer,
        out_path,
        QgsProject.instance().transformContext(),
        opts
    )
    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Coverage write failed: {msg}")

    # Guarantee .prj exists
    _ensure_prj_exists(out_path, crs, log=log)

    if log:
        log(f"💾 Coverage saved: {out_path} | CRS={crs.authid()}")
    else:
        print(f"💾 Coverage saved: {out_path} | CRS={crs.authid()}")

    return buffer_union_layer


def find_coverage_gaps(polygon_layer, coverage_layer, log=None):
    if log:
        log(f"🟡 Polygon features: {polygon_layer.featureCount()}")
        log(f"🟡 Coverage features: {coverage_layer.featureCount()}")
    else:
        print(f"🟡 Polygon features: {polygon_layer.featureCount()}")
        print(f"🟡 Coverage features: {coverage_layer.featureCount()}")

    gap_raw = processing.run("native:difference", {
        "INPUT": polygon_layer,
        "OVERLAY": coverage_layer,
        "OUTPUT": "memory:gap_raw"
    })["OUTPUT"]

    gap = processing.run("native:multiparttosingleparts", {
        "INPUT": gap_raw,
        "OUTPUT": "memory:gap"
    })["OUTPUT"]

    return gap
