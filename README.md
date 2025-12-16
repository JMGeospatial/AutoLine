AutoLine 2.0 – MBES & SSS Line Planning Plugin for QGIS

Author: Jan Majcher
📧 janmajcher710@gmail.com

JMGeospatial for Green Rebel Marine Limited. LLM assisted

**Overview**

AutoLine is a QGIS plugin for planning optimized multibeam echosounder (MBES) and side-scan sonar (SSS) survey tracklines.
It supports depth-adaptive (dynamic) and fixed line spacing, coverage estimation, crosslines, gap detection, infill generation, and survey duration estimation.

The goal is to minimise line mileage while ensuring full seabed coverage, using bathymetry-driven spacing where available.
**
What “Adaptive / Dynamic Spacing” Means
**
Line spacing is adjusted automatically based on depth:

Depth is sampled along the centerline from a DEM

Swath width is computed using beam angle

Required overlap is applied (e.g. 20–30%)

Shallow areas → tighter spacing

Deeper areas → wider spacing

This ensures conservative coverage without unnecessary redundancy.

**Key Features**
Line Planning

Automatic centerline generation (polygon orientation)

Manual heading or predefined centerline support

Fixed or depth-adaptive line spacing

Alternating run-in / run-out extensions

Crossline generation

Existing line plan analysis (no regeneration)

Coverage & QA

Per-segment swath-based coverage polygons

Gap detection inside survey polygon

Automatic infill line generation

Robust CRS validation (projected CRS enforced)

Outputs

Tracklines (Shapefile)

Coverage polygon

Gap polygons

Infill lines

Survey statistics (line count, mileage)

Utilities (New in 2.0)

Survey Time Calculator

Estimates survey duration (days)

Inputs: total km, number of lines, vessel speed, turn time, operational hours

Outputs CSV summary for reporting

Plugin Architecture
GUI

line_planner_dialog.py

dialog_line_planner.ui

survey_time_dialog.py

dialog_survey_time.ui

Provides:

Layer loading (project layers or file paths)

Line spacing configuration

Direction control

Coverage, gaps, infills toggles

Output paths

Progress bar + live log

Execution Flow

Plugin launched from line_planner_plugin.py

GUI collects parameters

main_line_planner.run_with_params() executes the workflow

Core Workflow (main_line_planner.py)

Load polygon & DEM

CRS validation (must match & be projected)

Generate or load centerline

Sample depth along centerline

Compute swath width & spacing

Generate main lines (dynamic or fixed)

Optional:

Crosslines

Coverage polygons

Gap detection

Infills

Write outputs & stats

Key Modules
line_generator.py

generate_side_lines()

construct_auto_centerline()

construct_manual_centerline()

Offsets centerline, applies spacing logic, handles extensions, crosslines, mileage.

depth_sampling.py

sample_depth()

compute_swath()

Depth sampling + swath/spacing computation:

swath = 2 × depth × tan(beam_angle / 2)

geometry_tools.py

Line offsetting

Asymmetric extension

Polygon clipping

Swath buffering

coverage_analysis.py

Builds per-segment swath coverage

Ensures .prj CRS integrity

Detects uncovered gaps

infill_generator.py

Generates infill lines from gap geometry orientation

survey_time_calculator.py (New)

Estimates survey duration

Accounts for vessel speed & line turns

Writes results to CSV

Requirements

QGIS 3.44+ (Qt6 required)

Processing toolbox enabled

Projected CRS (metres)

Input Data

Survey polygon (Shapefile)

Bathymetric DEM (raster covering full area)

**Disclaimer**

**This plugin is provided as is.
The author accepts no liability for loss of operational time, data, revenue, or other damages.
All generated line plans and coverage estimates must be independently reviewed before operational use.**
