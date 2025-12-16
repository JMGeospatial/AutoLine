from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProject
from .line_planner_dialog import LinePlannerDialog
from .survey_time_dialog import SurveyTimeDialog
import os

class LinePlannerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.menu = None
        self.action = None
        self.timecalc_action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.svg")
        icon_path_time = os.path.join(self.plugin_dir, "icon_time.svg")

        # Create actions
        self.action = QAction(QIcon(icon_path), "Launch Line Planner", self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.timecalc_action = QAction(QIcon(icon_path_time), "Survey Time Calculator", self.iface.mainWindow())
        self.timecalc_action.triggered.connect(self.run_time_calculator)

        # Add submenu under Plugins
        self.menu = QMenu("AutoLine Tools", self.iface.mainWindow())
        self.menu.addAction(self.action)
        self.menu.addAction(self.timecalc_action)
        self.iface.pluginMenu().addMenu(self.menu)

        # Add icon to toolbar for the main tool
        self.iface.addToolBarIcon(self.action)
        self.iface.addToolBarIcon(self.timecalc_action)


    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        if self.menu:
            self.iface.pluginMenu().removeAction(self.menu.menuAction())
        self.iface.removeToolBarIcon(self.timecalc_action)


    def run(self):
        if not self.dialog:
            self.dialog = LinePlannerDialog(self.iface)
        self.dialog.show()

    def run_time_calculator(self):
        dlg = SurveyTimeDialog(self.iface.mainWindow())
        dlg.exec()

