# AutoLine 

Author: Jan Majcher janmajcher710@gmail.com JMGeospatial for Green Rebel Marine Limited

AutoLine – Multibeam & SSS Line Planning Plugin for QGIS
AutoLine is a QGIS plugin that generates optimized tracklines for multibeam echosounder (MBES) and side-scan sonar (SSS) surveys. It supports both adaptive* and fixed line spacing, coverage estimation, crossline generation, and infill planning, streamlining survey preparation and ensuring full seabed coverage with minimal redundancy.


*Adaptive/dynamic spacing means:
The distance between each survey line is not fixed—it changes depending on the depth.
How it works:
The plugin samples depth along the centerline from an existing bathymetric DEM.
It calculates how wide the MBES swath would be at each depth using the beam angle.
It then sets line spacing based on this swath and the required overlap (e.g. 20%).
Shallower areas get lines spaced closer together, deeper areas get lines spaced farther apart.
This ensures full coverage while minimizing unnecessary lines.

**Features**
Automatic & Manual Centerline Generation
Depth-Adaptive or Fixed Line Spacing
Crossline Generation
Swath Coverage Estimation
Gap Detection & Infill Line Creation
Shapefile Output of Tracklines and Coverage
Survey Statistics Output (mileage, line count)
Plugin Architecture
GUI Defined in line_planner_dialog.py and dialog_line_planner.ui. It allows users to:
Load input survey polygon and DEM
Configure line spacing (constant or adaptive)
Choose centerline mode (auto, manual heading, or predefined)
Enable crosslines, coverage analysis, infill generation
Define output paths for shapefiles and stats

**Execution Flow**
The plugin is initiated from line_planner_plugin.py, which launches the GUI. Upon execution, run_with_params() from main_line_planner.py is called with parameters gathered from the UI.

**Core Logic**
main_line_planner.run_with_params(**kwargs)
Main orchestration function:
Loads polygon and DEM
Generates or loads a centerline
Samples depth to determine swath width
Computes line spacing (constant or dynamic)
Calls generate_side_lines() to offset the centerline

**Optionally generates:**
crosslines
a coverage polygon (build_coverage_layer)
gap polygons (find_coverage_gaps)
infill lines (generate_infills)
Outputs shapefiles and stats

**Key Modules & Functions**
line_generator.py
generate_side_lines(...)
Offsets the centerline left/right, computes spacing (fixed or adaptive), extends and clips lines. Returns tracklines and total mileage.

construct_manual_centerline(...) / construct_auto_centerline(...)
Returns a centerline from heading or longest polygon edge.

depth_sampling.py
sample_depth(...)
Samples DEM along a line at regular intervals and returns min/mean depth.

compute_swath(...)
Calculates total swath width and spacing using the formula:
swath = 2 * depth * tan(beam_angle / 2)

geometry_tools.py
offset_line: Offsets line laterally using native:offsetline

extend_line: Extends both ends using vector math

clip_to_polygon: Clips a line to the buffered survey polygon

buffer_line: Generates a swath-width buffer polygon

coverage_analysis.py
build_coverage_layer(...)
Samples DEM along lines, builds per-segment swath-width buffers, and merges into a coverage polygon layer.

find_coverage_gaps(...)
Computes difference between the survey polygon and coverage polygon to detect gaps.

infill_generator.py
generate_infills(...)
For each gap, computes direction from nearest line, samples depth at the centroid, and generates an extended line along the orientation of nearby coverage.

**Output**
Tracklines: Shapefile with line geometry (.shp)

Coverage Polygon: Swath union

Gap Polygon: Missed areas

Infills: Supplemental lines

Stats File: Line count and mileage

**Requirements**
QGIS 3.10+

Processing toolbox (native algorithms)

**Input:**

Polygon shapefile (of the site to be covered with survey data)

DEM (existing raster with open source bathymetric coverage encompassing the entire site)
