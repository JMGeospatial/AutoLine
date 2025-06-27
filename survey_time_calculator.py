import csv
import os

def estimate_survey_duration_km(
    total_km,
    total_lines,
    vessel_speed_knots,
    line_turn_time_min,
    hours_per_day,
    output_csv_path
):
    if not output_csv_path:
        raise ValueError("Output CSV path is required.")

    vessel_speed_kmh = vessel_speed_knots * 1.852
    line_time_hr = total_km / vessel_speed_kmh
    total_turns_hr = (total_lines - 1) * (line_turn_time_min / 60)
    total_turns_days = total_turns_hr / hours_per_day
    total_survey_time_hr = line_time_hr + total_turns_hr
    duration_days = total_survey_time_hr / hours_per_day

    headers = [
        "Total_km", "Number_of_Lines", "Vessel_Speed_knots",
        "Turn_Time_min", "Operational_Hours_per_Day", "Estimated_Days",
        "Total_Turn_Time_Hours", "Total_Turn_Time_Days"
    ]
    row = [
        total_km, total_lines, vessel_speed_knots,
        line_turn_time_min, hours_per_day, round(duration_days, 2),
        round(total_turns_hr, 2), round(total_turns_days, 2)
    ]
    write_header = not os.path.exists(output_csv_path)
    with open(output_csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(headers)
        writer.writerow(row)

    return duration_days
