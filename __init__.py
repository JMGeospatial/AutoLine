# Init file for line planner module package
def classFactory(iface):
    from .line_planner_plugin import LinePlannerPlugin
    return LinePlannerPlugin(iface)
