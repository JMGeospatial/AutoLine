import os
import math
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFields, QgsField,
    QgsWkbTypes, QgsVectorFileWriter, QgsFeature, QgsPointXY
)
from PyQt5.QtCore import QVariant

from .geometry_tools import offset_line, extend_line_asym, clip_to_polygon, buffer_line
from .depth_sampling import sample_depth, compute_swath
from .line_generator import generate_side_lines, construct_manual_centerline, construct_auto_centerline
from .coverage_analysis import build_coverage_layer, find_coverage_gaps
from .infill_generator import generate_infills

def run_with_params(**kwargs):
    # GUI parameters
    Generate_new_line_plan = kwargs.get("Generate_new_line_plan", 'Yes')
    Generate_infills = kwargs.get("Generate_infills", 'No')
    Estimate_coverage = kwargs.get("Estimate_coverage", 'No')
    Crosslines_generate = kwargs.get("Crosslines_generate", 'No')
    Crossline_spacing = kwargs.get("Crossline_spacing", 1000)
    Crossline_output_path = kwargs.get("Crossline_output_path", "")
    Set_constant_mainline_spacing = kwargs.get("Set_constant_mainline_spacing", 'Yes')
    Constant_line_spacing = kwargs.get("Constant_line_spacing", 40)
    Line_spacing_depth_mode = kwargs.get("Line_spacing_depth_mode", 'min')
    Manual_heading_deg = kwargs.get("Manual_heading_deg")
    centerline_generate = kwargs.get("centerline_generate", 'Yes')
    sampling_interval = kwargs.get("sampling_interval", 1)
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
    tracklines_filename = kwargs.get("tracklines_filename", "")
    coverage_path = kwargs.get("coverage_path", "")
    gap_output_path = kwargs.get("gap_output_path", "")
    trackline_path = kwargs.get("trackline_path", "")
    Survey_stats_path = kwargs.get("Survey_stats_path", "")
    infill_output_path = kwargs.get("Infill_output_path", "")

    lines = []
    spacing_values = []
    mileage_no_runins = 0
    mileage_with_runins = 0

    if not polygon_layer and polygon_path:
        polygon_layer = QgsVectorLayer(polygon_path, "polygon", "ogr")
    if not polygon_layer or not polygon_layer.isValid():
        raise ValueError("Polygon layer is missing or invalid.")
    polygon_geom = list(polygon_layer.getFeatures())[0].geometry()
    crs_authid = polygon_layer.crs().authid()

    if not dem_layer and dem_path:
        dem_layer = QgsRasterLayer(dem_path, "DEM")
    if not dem_layer or not dem_layer.isValid():
        raise ValueError("DEM layer is missing or invalid.")

    if centerline_generate == 'Yes':
        if Manual_heading_deg is not None:
            raw_centerline = construct_manual_centerline(polygon_geom, Manual_heading_deg, extension_length)
        else:
            raw_centerline = construct_auto_centerline(polygon_layer, extension_length)
    else:
        if not centerline_layer and centerline_path:
            centerline_layer = QgsVectorLayer(centerline_path, "centerline", "ogr")
        if not centerline_layer or not centerline_layer.isValid():
            raise ValueError("Centerline layer is missing or invalid.")
        features = list(centerline_layer.getFeatures())
        if not features:
            raise ValueError("Centerline contains no features.")
        raw_centerline = features[0].geometry()

    buffer_geom = polygon_geom.buffer(buffer_distance_for_clipping, 32)
    centerline_extended = extend_line_asym(raw_centerline, run_in, run_out, buffer_geom)

    initial_depth = sample_depth(centerline_extended, dem_layer, crs_authid, interval=sampling_interval, mode=Line_spacing_depth_mode)
    swath, initial_spacing = compute_swath(initial_depth, beam_angle_deg, overlap_ratio)

    use_constant = Set_constant_mainline_spacing == 'Yes'
    if use_constant:
        initial_spacing = Constant_line_spacing

    if Generate_new_line_plan == 'Yes':
        lines, mileage_no_runins, mileage_with_runins, spacing_values = generate_side_lines(
            centerline_extended, crs_authid, dem_layer, buffer_geom, extension_length,
            use_constant, Constant_line_spacing, initial_spacing,
            line_spacing_mode=Line_spacing_depth_mode, beam_angle_deg=beam_angle_deg,
            overlap_ratio=overlap_ratio, sampling_interval=sampling_interval,
            run_in=run_in, run_out=run_out, buffer_offset=buffer_distance_for_clipping,
            crossline_spacing=Crossline_spacing if Crosslines_generate == 'Yes' else None,
            polygon_geom=polygon_geom,
            crossline_output_path=Crossline_output_path
        )

        centerline_feat = QgsFeature()
        centerline_feat.setGeometry(centerline_extended)
        centerline_feat.setAttributes([0])
        lines.insert(0, (swath, centerline_extended, centerline_feat))
        mileage_no_runins += centerline_extended.length()
        mileage_with_runins += centerline_extended.length()
    else:
        if not existing_layer and Existing_lineplan_path:
            existing_layer = QgsVectorLayer(Existing_lineplan_path, "existing_lines", "ogr")
        if not existing_layer or not existing_layer.isValid():
            raise ValueError("Existing lineplan layer is missing or invalid.")
        crs_authid = existing_layer.crs().authid()
        for i, f in enumerate(existing_layer.getFeatures()):
            geom = f.geometry()
            lines.append((None, geom, f))
        print(f"✅ Loaded {len(lines)} lines from existing source.")

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
        print(f"✅ Tracklines written to: {trackline_path}")

    if Estimate_coverage == 'Yes':
        coverage_layer = build_coverage_layer(
            lines, crs_authid, buffer_geom, dem_layer, coverage_path,
            beam_angle_deg=beam_angle_deg, sampling_interval=sampling_interval
        )
        gap_layer = find_coverage_gaps(polygon_layer, coverage_layer)
        QgsVectorFileWriter.writeAsVectorFormat(gap_layer, gap_output_path, "UTF-8", polygon_layer.crs(), "ESRI Shapefile")
        print(f"📂 Gap polygons saved to: {gap_output_path}")
    else:
        if Generate_infills == 'Yes':
            raise ValueError("Enable potential coverage layer creation to estimate multibeam coverage gaps and potential infills.")
        coverage_layer = None
        gap_layer = None

    if Generate_infills == 'Yes' and any(gap_layer.getFeatures()):
        generate_infills(
            gap_layer, lines, polygon_geom,
            dem_layer, crs_authid, infill_output_path or output_dir
        )

    print(f"📏 Mileage without run-ins: {mileage_no_runins / 1000:.2f} km")
    print(f"📏 Mileage with run-ins: {mileage_with_runins / 1000:.2f} km")

    if Survey_stats_path:
        with open(Survey_stats_path, "w", encoding="utf-8") as f:
            f.write(f"Mileage without run-ins: {mileage_no_runins / 1000:.2f} km\n")
            f.write(f"Mileage with run-ins: {mileage_with_runins / 1000:.2f} km\n")
            f.write(f"Number of lines: {len(lines)}\n")
        print(f"📝 Stats saved to: {Survey_stats_path}")

    if not use_constant:
        if spacing_values:
            print(f"📊 Dynamic spacing — average: {sum(spacing_values)/len(spacing_values):.2f} m")
            print(f"📊 Range: {min(spacing_values):.2f}–{max(spacing_values):.2f} m")
