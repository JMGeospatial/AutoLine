# line_planner_dialog.py
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import QDialog, QFileDialog, QMessageBox, QDialogButtonBox
from . import main_line_planner
import os
import traceback
from qgis.core import Qgis, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), "dialog_line_planner.ui"
))

class LinePlannerDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
            super().__init__(parent)
            self.iface = iface
            self.setupUi(self)

            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(0)
            self.textLog.clear()

            self.init_logic()
            self.log("Dialog launched")

            # Intercept OK button
            # Intercept the OK button so it doesn't close the dialog
            ok_button = self.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
            if ok_button is not None:
                try:
                    ok_button.clicked.disconnect()
                except TypeError:
                    # no previous connection, ignore
                    pass
                ok_button.clicked.connect(self.on_ok_clicked)

        
    def on_ok_clicked(self):
        # Switch to LOG tab immediately
        try:
            self.tabWidget.setCurrentIndex(1)  # index 1 = Log tab
        except Exception:
            pass

        # Prevent dialog from closing
        # (do NOT call accept() or reject())

        # Start progress + logs
        self.textLog.clear()
        self.update_progress(0)
        self.log("▶ Starting AutoLine...")

        # Run the tool
        self.run_planner()
    
    def log(self, message: str):
        """
        Send a message to the Log tab and to the console.
        """
        message = str(message)
        print(message)
        if hasattr(self, "textLog"):
            self.textLog.append(message)
            QtWidgets.QApplication.processEvents()

    def update_progress(self, value: int):
        """
        Update progress bar (0–100).
        """
        if hasattr(self, "progressBar"):
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(int(value))
            QtWidgets.QApplication.processEvents()

    def init_logic(self):
        # Populate layer dropdowns
        self.populate_layer_combobox(self.comboBox_dem, 'raster')
        self.populate_layer_combobox(self.comboBox_polygon, 'polygon')
        self.populate_layer_combobox(self.comboBox_centerline, 'line')
        self.populate_layer_combobox(self.comboBox_existinglineplan, 'line')

        QgsProject.instance().layerWasAdded.connect(self.refresh_layer_dropdowns)
        QgsProject.instance().layerWillBeRemoved.connect(self.refresh_layer_dropdowns)

        
        self.checkbox_generate.toggled.connect(self.toggle_generation_mode)
        self.toggle_generation_mode()
        self.radio_constant_spacing.toggled.connect(self.toggle_spacing_mode)
        self.radio_dynamic_spacing.toggled.connect(self.toggle_spacing_mode)
        self.toggle_spacing_mode()
        self.combo_surveydirection_mode.currentIndexChanged.connect(self.toggle_direction_mode)
        self.combo_manualdirection_mode.currentIndexChanged.connect(self.toggle_direction_mode)
        self.toggle_direction_mode()
        self.checkBox_crosslines.toggled.connect(self.toggle_crosslines)
        self.toggle_crosslines()
        self.checkBox_coverage.toggled.connect(self.toggle_coverage)
        self.toggle_coverage()
        self.checkBox_gaps.toggled.connect(self.toggle_gap_logic)
        self.checkBox_infills.toggled.connect(self.toggle_gap_logic)
        self.checkBox_coverage.toggled.connect(self.toggle_gap_logic)
        self.checkBox_coverage.toggled.connect(self.toggle_generation_mode)
        self.toggle_gap_logic()
        self.checkBox_stats.toggled.connect(self.toggle_stats_output)
        self.toggle_stats_output()
        self.toggle_direction_mode()

        # Browse buttons
        self.browse_dem_path.clicked.connect(lambda: self.set_path_to_combobox(self.comboBox_dem, True, "Raster files (*.tif *.asc *.img *.vrt *.sdat)"))
        self.browse_surveypolygon_path.clicked.connect(lambda: self.set_path_to_combobox(self.comboBox_polygon, True, "Shapefiles (*.shp)"))
        self.pushButton_lineplan_output_path.clicked.connect(lambda: self.set_path_to_combobox(self.lineEdit_lineplan_output_path, False, "Shapefiles (*.shp)"))
        self.pushButton_existinglineplan_path.clicked.connect(lambda: self.set_path_to_combobox(self.comboBox_existinglineplan, True, "Shapefiles (*.shp)"))
        self.browse_centerline.clicked.connect(lambda: self.set_path_to_combobox(self.comboBox_centerline, True, "Shapefiles (*.shp)"))
        self.pushButton_crossline_path.clicked.connect(lambda: self.set_path_to_combobox(self.lineEdit_crossline_path, False, "Shapefiles (*.shp)"))
        self.pushButton_coverage.clicked.connect(lambda: self.set_path_to_combobox(self.lineEdit_coverage_path, False, "Shapefiles (*.shp)"))
        self.pushButton_gaps_path.clicked.connect(lambda: self.set_path_to_combobox(self.lineEdit_gaps_path, False, "Shapefiles (*.shp)"))
        self.pushButton_infills_path.clicked.connect(lambda: self.set_path_to_combobox(self.lineEdit_infills_path, False, "Shapefiles (*.shp)"))
        self.pushButton_stats.clicked.connect(lambda: self.set_path_to_combobox(self.lineEdit_stats_path, False, "Text files (*.txt)"))

    def populate_layer_combobox(self, combo, layer_type):
        combo.blockSignals(True)
        combo.clear()

        # Placeholder → means “no selection”
        combo.addItem("-- Select layer --", None)

        for layer in QgsProject.instance().mapLayers().values():
            if layer_type == 'raster' and isinstance(layer, QgsRasterLayer):
                combo.addItem(layer.name(), layer.id())

            elif (
                layer_type == 'polygon'
                and isinstance(layer, QgsVectorLayer)
                and layer.geometryType() == QgsWkbTypes.PolygonGeometry
            ):
                combo.addItem(layer.name(), layer.id())

            elif (
                layer_type == 'line'
                and isinstance(layer, QgsVectorLayer)
                and layer.geometryType() == QgsWkbTypes.LineGeometry
            ):
                combo.addItem(layer.name(), layer.id())

        combo.setCurrentIndex(0)
        combo.blockSignals(False)


    def refresh_layer_dropdowns(self):
        self.populate_layer_combobox(self.comboBox_dem, 'raster')
        self.populate_layer_combobox(self.comboBox_polygon, 'polygon')
        self.populate_layer_combobox(self.comboBox_centerline, 'line')
        self.populate_layer_combobox(self.comboBox_existinglineplan, 'line')

    def set_path_to_combobox(self, widget, file=True, file_filter=None):
        path = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)[0] if file else \
               QFileDialog.getSaveFileName(self, "Select Output Path", "", file_filter)[0]
        if not path:
            return

        # QComboBox support
        if hasattr(widget, "findText") and hasattr(widget, "addItem") and hasattr(widget, "setCurrentText"):
            if widget.findText(path) == -1:
                widget.addItem(path)
            widget.setCurrentText(path)
        # QLineEdit fallback
        elif hasattr(widget, "setText"):
            widget.setText(path)

    def resolve_layer_or_path(self, combo):
        layer_id = combo.currentData()
        if layer_id:
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                return layer
        text = combo.currentText().strip()
        return text or None


    def toggle_generation_mode(self):
        gen_enabled = self.checkbox_generate.isChecked()
        cov_enabled = self.checkBox_coverage.isChecked()

        self.lineEdit_lineplan_output_path.setEnabled(gen_enabled)
        self.pushButton_lineplan_output_path.setEnabled(gen_enabled)

        self.combo_surveydirection_mode.setEnabled(gen_enabled)
        self.combo_manualdirection_mode.setEnabled(gen_enabled)
        is_manual = self.combo_surveydirection_mode.currentText() == "Manual"
        manual_mode = self.combo_manualdirection_mode.currentText() if is_manual else ""

        self.spin_heading.setEnabled(gen_enabled and is_manual and manual_mode == "Use manual heading")
        self.comboBox_centerline.setEnabled(gen_enabled and is_manual and manual_mode == "Use a pre-defined centerline")
        self.browse_centerline.setEnabled(gen_enabled and is_manual and manual_mode == "Use a pre-defined centerline")

        self.radio_dynamic_spacing.setEnabled(gen_enabled)
        self.radio_constant_spacing.setEnabled(gen_enabled)

        self.combo_swath_mode.setEnabled(gen_enabled or (not self.radio_constant_spacing.isChecked() and cov_enabled))
        self.spin_overlap_ratio.setEnabled(gen_enabled)
        self.spin_beam_angle.setEnabled(gen_enabled or cov_enabled)

        self.spin_runin.setEnabled(gen_enabled)
        self.spin_runout.setEnabled(gen_enabled)

        self.comboBox_existinglineplan.setEnabled(not gen_enabled)
        self.pushButton_existinglineplan_path.setEnabled(not gen_enabled)

    def toggle_spacing_mode(self):
        is_constant = self.radio_constant_spacing.isChecked()
        cov_enabled = self.checkBox_coverage.isChecked()

        self.spin_constant_spacing.setEnabled(is_constant)
        self.combo_swath_mode.setEnabled(not is_constant or cov_enabled)
        self.spin_overlap_ratio.setEnabled(not is_constant)
        self.spin_beam_angle.setEnabled(not is_constant or cov_enabled)

    def toggle_direction_mode(self):
        is_manual = self.combo_surveydirection_mode.currentText() == "Manual"
        self.combo_manualdirection_mode.setEnabled(is_manual)

        self.spin_heading.setEnabled(False)
        self.comboBox_centerline.setEnabled(False)
        self.browse_centerline.setEnabled(False)

        if not is_manual:
            return

        manual_mode = self.combo_manualdirection_mode.currentText()
        self.spin_heading.setEnabled(manual_mode == "Use manual heading")
        self.comboBox_centerline.setEnabled(manual_mode == "Use a pre-defined centerline")
        self.browse_centerline.setEnabled(manual_mode == "Use a pre-defined centerline")

    def toggle_crosslines(self):
        enabled = self.checkBox_crosslines.isChecked()
        self.spinBox_crosslines.setEnabled(enabled)
        self.lineEdit_crossline_path.setEnabled(enabled)
        self.pushButton_crossline_path.setEnabled(enabled)

    def toggle_coverage(self):
        enabled = self.checkBox_coverage.isChecked()
        self.lineEdit_coverage_path.setEnabled(enabled)
        self.pushButton_coverage.setEnabled(enabled)

    def toggle_gap_logic(self):
        cov = self.checkBox_coverage.isChecked()
        gaps = self.checkBox_gaps.isChecked()
        infills = self.checkBox_infills.isChecked()

        self.checkBox_gaps.setEnabled(cov)
        self.lineEdit_gaps_path.setEnabled(cov and gaps)
        self.pushButton_gaps_path.setEnabled(cov and gaps)

        self.checkBox_infills.setEnabled(cov and gaps)
        self.lineEdit_infills_path.setEnabled(cov and gaps and infills)
        self.pushButton_infills_path.setEnabled(cov and gaps and infills)

    def toggle_stats_output(self):
        enabled = self.checkBox_stats.isChecked()
        self.lineEdit_stats_path.setEnabled(enabled)
        self.pushButton_stats.setEnabled(enabled)

    def run_planner(self):
        self.log("🟢 run_planner() triggered")
        # (optional) don’t clear here, it’s already cleared in on_ok_clicked
        self.update_progress(0)

        centerline_generate = 'Yes' if (
            self.combo_surveydirection_mode.currentText() == 'Automatic'
            or (
                self.combo_surveydirection_mode.currentText() == 'Manual'
                and self.combo_manualdirection_mode.currentText() == 'Use manual heading'
            )
        ) else 'No'

        kwargs = {
            "Generate_new_line_plan": 'Yes' if self.checkbox_generate.isChecked() else 'No',
            "Estimate_coverage": 'Yes' if self.checkBox_coverage.isChecked() else 'No',
            "Generate_infills": 'Yes' if self.checkBox_infills.isChecked() else 'No',
            "Crosslines_generate": 'Yes' if self.checkBox_crosslines.isChecked() else 'No',
            "Crossline_spacing": self.spinBox_crosslines.value(),
            "Crossline_output_path": self.lineEdit_crossline_path.text(),
            "Set_constant_mainline_spacing": 'Yes' if self.radio_constant_spacing.isChecked() else 'No',
            "Constant_line_spacing": self.spin_constant_spacing.value(),
            "Line_spacing_depth_mode": 'min' if self.combo_swath_mode.currentText() == 'Use min depth' else 'mean',
            "Manual_heading_deg": (
                self.spin_heading.value()
                if self.combo_surveydirection_mode.currentText() == 'Manual'
                and self.combo_manualdirection_mode.currentText() == 'Use manual heading'
                else None
            ),
            "centerline_generate": centerline_generate,
            "beam_angle_deg": self.spin_beam_angle.value(),
            "overlap_ratio": self.spin_overlap_ratio.value(),
            "extension_length": 200,
            "buffer_distance_for_clipping": 10,
            "run_in": self.spin_runin.value(),
            "run_out": self.spin_runout.value(),
            "output_dir": os.path.dirname(self.lineEdit_lineplan_output_path.text()),
            "tracklines_filename": "",
            "depth_sampling_interval": self.spinDepthSampling.value(),
            "Infill_output_path": self.lineEdit_infills_path.text(),
            "coverage_path": self.lineEdit_coverage_path.text(),
            "gap_output_path": self.lineEdit_gaps_path.text(),
            "trackline_path": self.lineEdit_lineplan_output_path.text(),
            "Survey_stats_path": self.lineEdit_stats_path.text() if self.checkBox_stats.isChecked() else ""
        }

        # Resolve combo layer or path for DEM, polygon, centerline, existing lines
        dem_res = self.resolve_layer_or_path(self.comboBox_dem)
        kwargs["dem_layer"] = dem_res if isinstance(dem_res, QgsRasterLayer) else None
        kwargs["dem_path"] = dem_res if isinstance(dem_res, str) else None

        polygon_res = self.resolve_layer_or_path(self.comboBox_polygon)
        kwargs["polygon_layer"] = polygon_res if isinstance(polygon_res, QgsVectorLayer) else None
        kwargs["polygon_path"] = polygon_res if isinstance(polygon_res, str) else None

        centerline_res = self.resolve_layer_or_path(self.comboBox_centerline)
        kwargs["centerline_layer"] = centerline_res if isinstance(centerline_res, QgsVectorLayer) else None
        kwargs["centerline_path"] = centerline_res if isinstance(centerline_res, str) else None

        existing_res = self.resolve_layer_or_path(self.comboBox_existinglineplan)
        kwargs["existing_layer"] = existing_res if isinstance(existing_res, QgsVectorLayer) else None
        kwargs["Existing_lineplan_path"] = existing_res if isinstance(existing_res, str) else None

        # attach callbacks
        kwargs["log_callback"] = self.log
        kwargs["progress_callback"] = self.update_progress

        try:
            self.log("📱 Running main_line_planner with parameters:")
            for k, v in kwargs.items():
                self.log(f"  {k}: {v}")

            main_line_planner.run_with_params(**kwargs)

            self.update_progress(100)
            self.log("✅ Line planning finished.")
        except Exception as e:
            self.log("❌ Error running planner:")
            self.log(str(e))
            traceback.print_exc()
            QMessageBox.critical(self, "Line Planner Error", str(e))
        finally:
            self.iface.messageBar().pushMessage(
                "⚠️ AutoLine Notice",
                "USE CAREFULLY. ALWAYS CHECK DYNAMIC LINE PLANS AGAINST TRADITIONAL LINE PLANS.\n"
                "ESTIMATED COVERAGE IGNORES: SEABED CHANGE & ACROSS-TRACK SWATH VARIABILITY.\n"
                "USE SAFETY BUFFERS. PLAN CONSERVATIVELY.",
                level=Qgis.Warning,
                duration=15
            )

