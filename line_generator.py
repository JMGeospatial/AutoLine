from qgis.core import (
    QgsFeature, QgsPointXY, QgsGeometry, QgsVectorLayer,
    QgsVectorFileWriter, QgsField
)
from .geometry_tools import offset_line, clip_to_polygon
from .depth_sampling import sample_depth, compute_swath
from qgis.PyQt.QtCore import QVariant
import math

def construct_manual_centerline(polygon_geom, heading_deg, extension_length):
    """
    Build an infinite line through polygon centroid at a given heading.
    (extension_length not used here; kept for API compatibility)
    """
    centroid = polygon_geom.centroid().asPoint()
    angle_rad = math.radians(float(heading_deg))

    # Your original convention:
    ux, uy = math.sin(angle_rad), math.cos(angle_rad)

    p1 = QgsPointXY(centroid.x() - ux * 1000000, centroid.y() - uy * 1000000)
    p2 = QgsPointXY(centroid.x() + ux * 1000000, centroid.y() + uy * 1000000)
    return QgsGeometry.fromPolylineXY([p1, p2])


def construct_auto_centerline(polygon_layer, extension_length):
    """
    Auto-centerline based on the longest segment of a simplified polygon boundary,
    then rotated/translated through the polygon centroid and clipped to polygon.
    """
    from qgis import processing

    feats = list(polygon_layer.getFeatures())
    if not feats:
        raise ValueError("Polygon layer has no features.")
    polygon_geom = feats[0].geometry()

    simplified = processing.run("native:simplifygeometries", {
        "INPUT": polygon_layer,
        "METHOD": 0,
        "TOLERANCE": 0.5,
        "OUTPUT": "memory:simplified"
    })["OUTPUT"]

    lines = processing.run("native:polygonstolines", {
        "INPUT": simplified,
        "OUTPUT": "memory:lines"
    })["OUTPUT"]

    exploded = processing.run("native:explodelines", {
        "INPUT": lines,
        "OUTPUT": "memory:exploded"
    })["OUTPUT"]

    longest = None
    max_length = -1.0
    for f in exploded.getFeatures():
        g = f.geometry()
        if not g or g.isEmpty():
            continue
        length = g.length()
        if length > max_length:
            max_length = length
            longest = g

    if not longest or longest.isEmpty():
        raise ValueError("Could not derive a longest boundary segment for auto centerline.")

    centroid = polygon_geom.centroid().asPoint()
    seg = longest.asPolyline() if not longest.isMultipart() else longest.asMultiPolyline()[0]
    if len(seg) < 2:
        raise ValueError("Longest boundary segment is too short.")

    a, b = seg[0], seg[-1]
    dx, dy = b.x() - a.x(), b.y() - a.y()
    mag = math.hypot(dx, dy)
    if mag == 0:
        raise ValueError("Degenerate longest boundary segment.")

    ux, uy = dx / mag, dy / mag

    p1 = QgsPointXY(centroid.x() - ux * 1000000, centroid.y() - uy * 1000000)
    p2 = QgsPointXY(centroid.x() + ux * 1000000, centroid.y() + uy * 1000000)

    initial_cl = QgsGeometry.fromPolylineXY([p1, p2])
    return initial_cl.intersection(polygon_geom)


def generate_side_lines(centerline_geom, crs_authid, dem_layer, buffer_geom, extension_length,
                        use_constant_spacing, constant_spacing, initial_spacing,
                        line_spacing_mode='min', beam_angle_deg=120, overlap_ratio=0.3,
                        depth_sampling_interval=5, run_in=200, run_out=100, buffer_offset=10,
                        crossline_spacing=None, polygon_geom=None, crossline_output_path=None, log=None):

    from .geometry_tools import extend_line_asym  # Ensure it's imported

    all_lines = []
    spacing_values = []
    mileage_no_runins = 0.0
    mileage_with_runins = 0.0

    crossline_count = 0
    crossline_length = 0.0
    crossline_layer = None  # <-- NEW

    line_id = 1
    run_in_adj = max(run_in - buffer_offset, 0)
    run_out_adj = max(run_out - buffer_offset, 0)

    for sign in [1, -1]:
        offset = initial_spacing
        while True:
            offset_result = offset_line(centerline_geom, offset * sign, crs_authid)
            offset_feat = next(offset_result.getFeatures())
            offset_geom = offset_feat.geometry()

            # Alternate which end gets run-in vs run-out
            if (line_id % 2) == 0:
                start_ext, end_ext = run_in_adj, run_out_adj
            else:
                start_ext, end_ext = run_out_adj, run_in_adj

            extended = extend_line_asym(offset_geom, start_ext, end_ext, buffer_geom)
            if not extended or extended.isEmpty() or not extended.isGeosValid():
                break

            clipped = clip_to_polygon(extended, buffer_geom)
            if not clipped or clipped.isEmpty():
                break

            depth = sample_depth(
                extended, dem_layer, crs_authid,
                depth_sampling_interval=depth_sampling_interval,
                mode=line_spacing_mode, log=log
            )
            if depth is None:
                break

            swath, spacing_local = compute_swath(depth, beam_angle_deg, overlap_ratio)
            if not use_constant_spacing:
                spacing_values.append(spacing_local)

            mileage_no_runins += clipped.length()
            mileage_with_runins += extended.length()

            feat = QgsFeature()
            feat.setGeometry(extended)
            feat.setAttributes([line_id])
            all_lines.append((swath, extended, feat))

            offset += constant_spacing if use_constant_spacing else spacing_local
            line_id += 1

    # CROSSLINE GENERATION
    if crossline_spacing and polygon_geom:
        longest = max((g for _, g, _ in all_lines), key=lambda g: g.length(), default=None)
        if not longest or longest.isEmpty():
            if log:
                log("⚠️ No base line for crosslines.")
        else:
            seg = longest.asPolyline() if not longest.isMultipart() else longest.asMultiPolyline()[0]
            if len(seg) < 2:
                if log:
                    log("⚠️ Longest line too short for crosslines.")
            else:
                p0, p1 = seg[0], seg[-1]
                dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
                mag = math.hypot(dx, dy)
                ux, uy = dx / mag, dy / mag
                nx, ny = -uy, ux

                cline = QgsVectorLayer(f"LineString?crs={crs_authid}", "crosslines", "memory")
                provider = cline.dataProvider()
                provider.addAttributes([QgsField("id", QVariant.Int)])
                cline.updateFields()

                centroid = polygon_geom.centroid().asPoint()
                i = -crossline_spacing * 50
                cross_id = 1

                while i <= crossline_spacing * 50:
                    cx = centroid.x() + ux * i
                    cy = centroid.y() + uy * i
                    base = QgsPointXY(cx, cy)

                    a = QgsPointXY(base.x() - nx * 1000000, base.y() - ny * 1000000)
                    b = QgsPointXY(base.x() + nx * 1000000, base.y() + ny * 1000000)
                    raw = QgsGeometry.fromPolylineXY([a, b])

                    clipped_x = clip_to_polygon(raw, polygon_geom)
                    if clipped_x and not clipped_x.isEmpty():
                        if (cross_id % 2) == 0:
                            start_ext, end_ext = run_in, run_out
                        else:
                            start_ext, end_ext = run_out, run_in

                        ext = extend_line_asym(clipped_x, start_ext, end_ext, polygon_geom)

                        feat = QgsFeature(cline.fields())
                        feat.setGeometry(ext)
                        feat.setAttribute("id", cross_id)
                        provider.addFeature(feat)

                        crossline_count += 1
                        crossline_length += ext.length()
                        cross_id += 1

                    i += crossline_spacing

                cline.updateExtents()
                crossline_layer = cline  # <-- NEW: expose layer to caller

                if crossline_output_path:
                    if not crossline_output_path.lower().endswith(".shp"):
                        crossline_output_path += ".shp"
                    QgsVectorFileWriter.writeAsVectorFormat(
                        cline, crossline_output_path, "UTF-8", cline.crs(), "ESRI Shapefile"
                    )
                    if log:
                        log(f"📎 Crosslines saved to: {crossline_output_path}")

    return (
        all_lines,
        mileage_no_runins,
        mileage_with_runins,
        spacing_values,
        crossline_count,
        crossline_length,
        crossline_layer
    )


def generate_crosslines_from_lines(base_lines, crs_authid, polygon_geom,
                                   crossline_spacing, run_in, run_out,
                                   crossline_output_path=None, buffer_offset=0, log=None):
    from .geometry_tools import extend_line_asym, clip_to_polygon

    longest = max(base_lines, key=lambda g: g.length(), default=None)
    if not longest or longest.isEmpty():
        if log:
            log("⚠️ No base line for crosslines.")
        return 0, 0.0, None

    seg = longest.asPolyline() if not longest.isMultipart() else longest.asMultiPolyline()[0]
    if len(seg) < 2:
        if log:
            log("⚠️ Base line too short for crosslines.")
        return 0, 0.0, None

    p0, p1 = seg[0], seg[-1]
    dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
    mag = math.hypot(dx, dy)
    ux, uy = dx / mag, dy / mag
    nx, ny = -uy, ux

    cline = QgsVectorLayer(f"LineString?crs={crs_authid}", "crosslines", "memory")
    provider = cline.dataProvider()
    provider.addAttributes([QgsField("id", QVariant.Int)])
    cline.updateFields()

    centroid = polygon_geom.centroid().asPoint()
    i = -crossline_spacing * 50
    cross_id = 1
    count = 0
    total_len = 0.0

    while i <= crossline_spacing * 50:
        cx = centroid.x() + ux * i
        cy = centroid.y() + uy * i
        base = QgsPointXY(cx, cy)

        a = QgsPointXY(base.x() - nx * 1000000, base.y() - ny * 1000000)
        b = QgsPointXY(base.x() + nx * 1000000, base.y() + ny * 1000000)
        raw = QgsGeometry.fromPolylineXY([a, b])

        clipped = clip_to_polygon(raw, polygon_geom)
        if clipped and not clipped.isEmpty():
            if (cross_id % 2) == 0:
                start_ext, end_ext = run_in, run_out
            else:
                start_ext, end_ext = run_out, run_in

            ext = extend_line_asym(clipped, start_ext, end_ext, polygon_geom)

            feat = QgsFeature(cline.fields())
            feat.setGeometry(ext)
            feat.setAttribute("id", cross_id)
            provider.addFeature(feat)

            count += 1
            total_len += ext.length()
            cross_id += 1

        i += crossline_spacing

    cline.updateExtents()

    if crossline_output_path:
        if not crossline_output_path.lower().endswith(".shp"):
            crossline_output_path += ".shp"
        QgsVectorFileWriter.writeAsVectorFormat(
            cline, crossline_output_path, "UTF-8", cline.crs(), "ESRI Shapefile"
        )
        if log:
            log(f"📎 Crosslines saved to: {crossline_output_path}")

    return count, total_len, cline
