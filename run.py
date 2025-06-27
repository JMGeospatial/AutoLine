import sys
import importlib

# Always add your script directory
script_dir = r"E:\Line_planner_refactor"
if script_dir not in sys.path:
    sys.path.append(script_dir)

# Unload modules if already loaded
for mod in ["geometry_tools", "infill_generator", "depth_sampling", "line_generator", "coverage_analysis", "main_line_planner"]:
    if mod in sys.modules:
        del sys.modules[mod]

# Reimport freshly
import geometry_tools
import depth_sampling
import line_generator
import coverage_analysis
import main_line_planner
import infill_generator

# Run the planner
main_line_planner.run()
