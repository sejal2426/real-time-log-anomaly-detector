# log_analyzer.py
import os
import pandas as pd
from parser import parse_line
from lstm_score import score_window

WINDOW = 50

def analyze_log_file(log_path, report_path="anomaly_report.txt"):
    entries = []

    print(f"Reading log file: {log_path}")

    # ---- STEP 1: Read & parse log file ----
    with open(log_path, "r") as f:
        for line in f:
            parsed = parse_line(line)
            if parsed:
                entries.append(parsed)

    if len(entries) < WINDOW:
        print("Not enough entries to form a 50-value window!")
        return

    df = pd.DataFrame(entries)

    print(f"Loaded {len(df)} log entries.")

    # ---- STEP 2: Sliding windows ----
    report_lines = []
    for i in range(len(df) - WINDOW):
        window_df = df.iloc[i:i + WINDOW]

        resp_values = [x["features"]["resp"] for x in window_df.to_dict("records")]

        lstm_result = score_window(resp_values)

        if lstm_result["is_anomaly"]:
            last = window_df.iloc[-1]

            resp_value = last["features"]["resp"]

            # ---- Determine anomaly type ----
            if resp_value > 500:
                anomaly_type = "CRITICAL SPIKE"
                fix = "Investigate timeout, network delay, or infinite loop."
            elif resp_value > 100:
                anomaly_type = "HIGH RESPONSE TIME"
                fix = "May be caused by heavy computation or I/O blocking."
            elif resp_value > 50:
                anomaly_type = "MEDIUM SPIKE"
                fix = "Check function performance or system load."
            else:
                anomaly_type = "UNKNOWN ANOMALY"
                fix = "General anomaly detected."

            report_lines.append(
                "Anomaly Detected:\n"
                f"  Timestamp: {last['timestamp']}\n"
                f"  File: {last['source_file']}\n"
                f"  Line: {last['line_number']}\n"
                f"  Resp Value: {resp_value}\n"
                f"  LSTM MSE: {lstm_result['mse']:.4f}\n"
                f"  Category: {anomaly_type}\n"
                f"  Suggested Fix: {fix}\n"
                f"------------------------------------------------------------\n"
            )

    # ---- STEP 3: Save report ----
    with open(report_path, "w") as f:
        f.writelines(report_lines)

    print(f"Report generated: {report_path}")


if __name__ == "__main__":
    # Default sample log file location
    default_log = "../data/sample_logs"

    if os.path.exists(default_log):
        analyze_log_file(default_log)
    else:
        print("Sample log file not found. Please provide correct path.")
