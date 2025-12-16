import os
import math
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFields, QgsField,
    QgsWkbTypes, QgsVectorFileWriter, QgsFeature
)
from qgis.PyQt.QtCore import QVariant

from .geometry_tools import extend_line_asym
from .depth_sampling import sample_depth, compute_swath
from .line_generator import generate_side_lines, construct_manual_centerline, construct_auto_centerline
from .coverage_analysis import build_coverage_layer, find_coverage_gaps
from .infill_generator import generate_infills

from qgis.core import QgsProject, QgsVectorLayer

def _replace_layer_in_project(layer, name: str):
    """Remove existing layer(s) with same name and add the new one."""
    prj = QgsProject.instance()
    for lyr in prj.mapLayers().values():
        if lyr.name() == name:
            prj.removeMapLayer(lyr.id())
    layer.setName(name)
    prj.addMapLayer(layer)

def _add_shapefile_to_project(path: str, name: str, log=None):
    """Load shapefile from disk and add to project (replace same-name layer)."""
    if not path:
        return None
    lyr = QgsVectorLayer(path, name, "ogr")
    if not lyr.isValid():
        if log:
            log(f"⚠️ Could not load layer from disk: {path}")
        return None
    _replace_layer_in_project(lyr, name)
    return lyr

def run_with_params(**kwargs):
    log_callback = kwargs.get("log_callback")
    progress_callback = kwargs.get("progress_callback")

    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    def progress(pct: int):
        if progress_callback:
            try:
                progress_callback(pct)
            except Exception:
                pass

    # GUI parameters
    Generate_new_line_plan = kwargs.get("Generate_new_line_plan", "Yes")
    Generate_infills = kwargs.get("Generate_infills", "No")
    Estimate_coverage = kwargs.get("Estimate_coverage", "No")
    Crosslines_generate = kwargs.get("Crosslines_generate", "No")
    Crossline_spacing = kwargs.get("Crossline_spacing", 1000)
    Crossline_output_path = kwargs.get("Crossline_output_path", "")

    Set_constant_mainline_spacing = kwargs.get("Set_constant_mainline_spacing", "Yes")
    Constant_line_spacing = kwargs.get("Constant_line_spacing", 40)
    Line_spacing_depth_mode = kwargs.get("Line_spacing_depth_mode", "min")
    Manual_heading_deg = kwargs.get("Manual_heading_deg")

    centerline_generate = kwargs.get("centerline_generate", "Yes")
    depth_sampling_interval = kwargs.get("depth_sampling_interval", kwargs.get("sampling_interval", 1.0))
    beam_angle_deg = kwargs.get("beam_angle_deg", 120)
    overlap_ratio = kwargs.get("overlap_ratio", 0.3)

    extension_length = kwargs.get("extension_length", 200)
    buffer_distance_for_clipping = kwargs.get("buffer_distance_for_clipping", 10)
    run_in = kwargs.get("run_in", 200)
    run_out = kwargs.get("run_out", 100)

    # Optional pre-loaded layers or fallback paths
    polygon_layer = kwargs.get("polygon_layer")
    polygon_path = kwargs.get("polygon_path")
    dem_layer = kwargs.get("dem_layer")
    dem_path = kwargs.get("dem_path")
    centerline_layer = kwargs.get("centerline_layer")
    centerline_path = kwargs.get("centerline_path")
    existing_layer = kwargs.get("existing_layer")
    Existing_lineplan_path = kwargs.get("Existing_lineplan_path", "")

    output_dir = kwargs.get("output_dir", os.path.dirname(polygon_path or ""))
    coverage_path = kwargs.get("coverage_path", "")
    gap_output_path = kwargs.get("gap_output_path", "")
    trackline_path = kwargs.get("trackline_path", "")
    Survey_stats_path = kwargs.get("Survey_stats_path", "")
    infill_output_path = kwargs.get("Infill_output_path", "")

    # Outputs / accumulators
    lines = []
    spacing_values = []
    mileage_no_runins = 0.0
    mileage_with_runins = 0.0
    crossline_count = 0
    crossline_mileage = 0.0

    progress(5)
    log("Inputs read, checking layers...")

    # Load polygon
    if not polygon_layer and polygon_path:
        polygon_layer = QgsVectorLayer(polygon_path, "polygon", "ogr")
    if not polygon_layer or not polygon_layer.isValid():
        raise ValueError("Polygon layer is missing or invalid.")

    feats = list(polygon_layer.getFeatures())
    if not feats:
        raise ValueError("Polygon layer has no features.")
    polygon_geom = feats[0].geometry()

    # CRS authid fallback to WKT (important for your case)
    poly_crs = polygon_layer.crs()
    crs_authid = poly_crs.authid() or poly_crs.toWkt()
    if not crs_authid:
        raise ValueError("Polygon CRS is valid but has no authid and no WKT.")

    # Load DEM
    if not dem_layer and dem_path:
        dem_layer = QgsRasterLayer(dem_path, "DEM")
    if not dem_layer or not dem_layer.isValid():
        raise ValueError("DEM layer is missing or invalid.")

    # CRS sanity checks
    dem_crs = dem_layer.crs()

    def _crs_eq(a, b):
        if not a.isValid() or not b.isValid():
            return False
        a_id, b_id = a.authid(), b.authid()
        if a_id and b_id:
            return a_id == b_id
        return a.toWkt() == b.toWkt()

    log(f"CRS check → DEM: {dem_crs.authid() or dem_crs.description()}")
    log(f"CRS check → Polygon: {poly_crs.authid() or poly_crs.description()}")

    if not _crs_eq(dem_crs, poly_crs):
        raise ValueError(
            "DEM and survey polygon must use the same projected CRS.\n"
            f"DEM CRS: {dem_crs.authid() or dem_crs.description()}, "
            f"Polygon CRS: {poly_crs.authid() or poly_crs.description()}.\n"
            "Please reproject one of them before running AutoLine."
        )

    if dem_crs.isGeographic():
        raise ValueError("DEM is in a geographic CRS (degrees). Please reproject to metres.")

    # Generate / load centerline geometry (only needed for NEW plan generation)
    if Generate_new_line_plan == "Yes":
        if centerline_generate == "Yes":
            if Manual_heading_deg is not None:
                raw_centerline = construct_manual_centerline(polygon_geom, Manual_heading_deg, extension_length)
            else:
                raw_centerline = construct_auto_centerline(polygon_layer, extension_length)
        else:
            if not centerline_layer and centerline_path:
                centerline_layer = QgsVectorLayer(centerline_path, "centerline", "ogr")
            if not centerline_layer or not centerline_layer.isValid():
                raise ValueError("Centerline layer is missing or invalid.")
            c_feats = list(centerline_layer.getFeatures())
            if not c_feats:
                raise ValueError("Centerline contains no features.")
            raw_centerline = c_feats[0].geometry()

        progress(20)
        log("Centerline generation finished.")

        buffer_geom = polygon_geom.buffer(buffer_distance_for_clipping, 32)
        centerline_extended = extend_line_asym(raw_centerline, run_in, run_out, buffer_geom)

        initial_depth = sample_depth(
            centerline_extended, dem_layer, crs_authid,
            depth_sampling_interval=depth_sampling_interval,
            mode=Line_spacing_depth_mode, log=log
        )
        swath, initial_spacing = compute_swath(initial_depth, beam_angle_deg, overlap_ratio)

        use_constant = Set_constant_mainline_spacing == "Yes"
        if use_constant:
            initial_spacing = Constant_line_spacing

        lines, mileage_no_runins, mileage_with_runins, spacing_values, c_count, c_len, cross_layer = generate_side_lines(
            centerline_extended, crs_authid, dem_layer, buffer_geom, extension_length,
            use_constant, Constant_line_spacing, initial_spacing,
            line_spacing_mode=Line_spacing_depth_mode, beam_angle_deg=beam_angle_deg,
            overlap_ratio=overlap_ratio, depth_sampling_interval=depth_sampling_interval,
            run_in=run_in, run_out=run_out, buffer_offset=buffer_distance_for_clipping,
            crossline_spacing=Crossline_spacing if Crosslines_generate == "Yes" else None,
            polygon_geom=polygon_geom,
            crossline_output_path=Crossline_output_path,
            log=log
        )

        crossline_count += c_count
        crossline_mileage += c_len
        if cross_layer:
            _replace_layer_in_project(cross_layer, "AutoLine_Crosslines")
        elif Crosslines_generate == "Yes" and Crossline_output_path:
            _add_shapefile_to_project(Crossline_output_path, "AutoLine_Crosslines", log=log)


        # Insert the centerline itself as line 0
        centerline_feat = QgsFeature()
        centerline_feat.setGeometry(centerline_extended)
        centerline_feat.setAttributes([0])

        lines.insert(0, (swath, centerline_extended, centerline_feat))
        mileage_no_runins += centerline_extended.length()
        mileage_with_runins += centerline_extended.length()

    else:
        # EXISTING lineplan branch
        progress(20)
        log("Using existing line plan...")

        if not existing_layer and Existing_lineplan_path:
            existing_layer = QgsVectorLayer(Existing_lineplan_path, "existing_lines", "ogr")
        if not existing_layer or not existing_layer.isValid():
            raise ValueError("Existing lineplan layer is missing or invalid.")

        ex_crs = existing_layer.crs()
        crs_authid = ex_crs.authid() or ex_crs.toWkt()
        if not crs_authid:
            raise ValueError("Existing lineplan CRS is empty (no authid and no WKT).")

        buffer_geom = polygon_geom.buffer(buffer_distance_for_clipping, 32)

        mileage_with_runins = 0.0
        mileage_no_runins = 0.0
        line_count = 0

        for f in existing_layer.getFeatures():
            geom = f.geometry()
            if not geom or geom.isEmpty():
                continue

            mileage_with_runins += geom.length()

            clipped = geom.intersection(polygon_geom)
            if clipped and not clipped.isEmpty():
                mileage_no_runins += clipped.length()

            lines.append((None, geom, f))
            line_count += 1

        log(f"✅ Loaded {line_count} lines from existing source.")
        log(f"📏 Existing lineplan length (clipped, no run-ins): {mileage_no_runins/1000:.2f} km")
        log(f"📏 Existing lineplan length (full, with run-ins): {mileage_with_runins/1000:.2f} km")
        log(f"📏 Run-ins total: {(mileage_with_runins - mileage_no_runins)/1000:.2f} km")

        if Crosslines_generate == "Yes":
            from .line_generator import generate_crosslines_from_lines
            base_geoms = [g for _, g, _ in lines if g and not g.isEmpty()]
            c_count, c_len, cross_layer = generate_crosslines_from_lines(
                base_geoms,
                crs_authid,
                polygon_geom,
                Crossline_spacing,
                run_in,
                run_out,
                crossline_output_path=Crossline_output_path,
                log=log
            )
            crossline_count += c_count
            crossline_mileage += c_len
            if cross_layer:
                _replace_layer_in_project(cross_layer, "AutoLine_Crosslines")
            elif Crosslines_generate == "Yes" and Crossline_output_path:
                _add_shapefile_to_project(Crossline_output_path, "AutoLine_Crosslines", log=log)


    progress(60)
    log("Line generation processes finished")

    # Write tracklines (if requested)
    if trackline_path:
        trackline_fields = QgsFields()
        trackline_fields.append(QgsField("id", QVariant.Int))

        writer = QgsVectorFileWriter(
            trackline_path, "UTF-8", trackline_fields,
            QgsWkbTypes.LineString, polygon_layer.crs(), "ESRI Shapefile"
        )

        for _, _, feat in lines:
            writer.addFeature(feat)
        del writer
        log(f"✅ Tracklines written to: {trackline_path}")
        _add_shapefile_to_project(trackline_path, "AutoLine_Tracklines", log=log)


    # Coverage + gaps
    if Estimate_coverage == "Yes":
        coverage_layer = build_coverage_layer(
            lines, crs_authid, buffer_geom, dem_layer, coverage_path,
            beam_angle_deg=beam_angle_deg, depth_sampling_interval=depth_sampling_interval, log=log
        )
        if coverage_layer:
            _replace_layer_in_project(coverage_layer, "AutoLine_Coverage")
        gap_layer = find_coverage_gaps(polygon_layer, coverage_layer)
        QgsVectorFileWriter.writeAsVectorFormat(
            gap_layer, gap_output_path, "UTF-8", polygon_layer.crs(), "ESRI Shapefile"
        )
        log(f"📂 Gap polygons saved to: {gap_output_path}")
        if gap_output_path:
            _add_shapefile_to_project(gap_output_path, "AutoLine_Gaps", log=log)

    else:
        if Generate_infills == "Yes":
            raise ValueError("Enable coverage estimation to compute gaps and potential infills.")
        coverage_layer = None
        gap_layer = None

    # Infills
    if Generate_infills == "Yes" and gap_layer and any(gap_layer.getFeatures()):
        generate_infills(
            gap_layer, lines, polygon_geom,
            dem_layer, crs_authid, infill_output_path or output_dir, log=log
        )

    progress(80)
    log("Auxiliary routines (coverage etc.) completed.")
    log(f"📏 User-set depth sampling interval (spacing+coverage): {depth_sampling_interval} m")
    log(f"📏 Mileage without run-ins: {mileage_no_runins / 1000:.2f} km")
    log(f"📏 Mileage with run-ins: {mileage_with_runins / 1000:.2f} km")

    if crossline_count > 0:
        log(f"📏 Crosslines: {crossline_count} | Total crossline length: {crossline_mileage / 1000:.2f} km")

    # Stats TXT
    if Survey_stats_path:
        with open(Survey_stats_path, "w", encoding="utf-8") as f:
            f.write(f"Mileage without run-ins: {mileage_no_runins / 1000:.2f} km\n")
            f.write(f"Mileage with run-ins: {mileage_with_runins / 1000:.2f} km\n")
            f.write(f"Number of lines: {len(lines)}\n")
            if crossline_count > 0:
                f.write(f"Crosslines: {crossline_count}\n")
                f.write(f"Total crossline length: {crossline_mileage / 1000:.2f} km\n")
        log(f"📝 Stats saved to: {Survey_stats_path}")

    # Dynamic spacing stats (only meaningful for new plan + dynamic mode)
    if Generate_new_line_plan == "Yes" and Set_constant_mainline_spacing != "Yes":
        if spacing_values:
            log(f"📊 Dynamic spacing — average: {sum(spacing_values)/len(spacing_values):.2f} m")
            log(f"📊 Range: {min(spacing_values):.2f}–{max(spacing_values):.2f} m")

    progress(100)
    log("All outputs written...")
