# report_writer.py
import csv
from datetime import datetime

REPORT = "../anomaly_report.csv"

def init_report():
    try:
        with open(REPORT, "x", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp","source_file","line_number",
                "anomaly_type","score","context"
            ])
            writer.writeheader()
    except FileExistsError:
        pass

def write_row(file, line, anomaly_type, score, context):
    row = {
        "timestamp": datetime.utcnow().isoformat(),
        "source_file": file,
        "line_number": line,
        "anomaly_type": anomaly_type,
        "score": float(score),
        "context": context
    }

    with open(REPORT, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writerow(row)

    print(f"[REPORT] {file}:{line} — {anomaly_type} — score={score}")
