from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QFileDialog
import os
from .survey_time_calculator import estimate_survey_duration_km

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), "dialog_survey_time.ui"))

class SurveyTimeDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.pushButton_browse_output.clicked.connect(self.set_output_path)
        self.pushButton_calculate.clicked.connect(self.calculate)

    def set_output_path(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Output CSV File", "", "CSV Files (*.csv)")
        if path:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            self.lineEdit_output_path.setText(path)

    def calculate(self):
        self.label_result.clear()  # Clear previous output
        try:
            total_km = float(self.lineEdit_total_km.text())
            num_lines = int(self.lineEdit_num_lines.text())
            speed = float(self.lineEdit_speed.text())
            turn_time = float(self.lineEdit_turn_time.text())
            hours_per_day = int(self.comboBox_hours.currentText())
            output_csv = self.lineEdit_output_path.text()

            if not output_csv:
                raise ValueError("Please select an output CSV file.")

            days = estimate_survey_duration_km(
                total_km, num_lines, speed, turn_time, hours_per_day, output_csv
            )
            self.label_result.setText(f"Estimated days: {days:.2f}")
        except Exception as e:
            self.label_result.setText(f"❌ Error: {e}")
