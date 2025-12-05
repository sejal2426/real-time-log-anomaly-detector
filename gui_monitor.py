# gui_monitor.py
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import time
import os
import csv
from collections import deque
from datetime import datetime
import webbrowser
import sys

# plotting (TkAgg backend for Tkinter)
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# your project modules (must exist in same folder)
from parser import parse_line
from lstm_score import score_window

# --------------------
# CONFIG
# --------------------
WINDOW = 50                     # must match model's window
BUFFER = deque(maxlen=WINDOW)
CSV_REPORT_DEFAULT = "realtime_report.csv"

# state
monitoring = False
monitor_thread = None
selected_log_file = None

# data
anomalies = []                  # list of dict anomaly records
resp_history = deque(maxlen=1000)
anomaly_points = []             # (index, resp)

# GUI state
header_printed = False

# --------------------
# Utility functions
# --------------------
def init_csv_file(path=CSV_REPORT_DEFAULT):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp", "file", "line", "resp", "mse",
                "anomaly_type", "suggested_fix", "reason"
            ])

def classify_anomaly(resp_value, raw_msg):
    raw = (raw_msg or "").lower()
    # keyword detection
    if "timeout" in raw or "timed out" in raw or "time out" in raw:
        return "CRITICAL SPIKE", "Investigate timeout, network latency or infinite loop.", "Timeout in log"
    if "login" in raw and ("fail" in raw or "incorrect" in raw or "denied" in raw):
        return "AUTH FAILURE", "Check authentication service and failed attempts.", "Login failure"
    if "error" in raw or "exception" in raw or "fail" in raw:
        return "ERROR", "Check stacktrace and fix exception cause.", "Error/Exception in log"
    if "db" in raw or "database" in raw:
        return "DB ISSUE", "Inspect DB performance / queries / connections.", "Database related"
    # numeric thresholds
    if resp_value > 500:
        return "CRITICAL SPIKE", "Investigate timeout, infinite loop, or network delay.", None
    if resp_value > 100:
        return "HIGH RESPONSE", "Possible heavy computation or I/O blocking.", None
    if resp_value > 50:
        return "MEDIUM SPIKE", "Possible slow code path, profile and optimize.", None
    return "ANOMALY", "Investigate (no clear reason).", None

# --------------------
# GUI row insertion & coloring
# --------------------
def gui_insert_row(gui_box, record):
    """
    Insert a formatted header (once) and append a row for `record`.
    Applies a color tag for the whole inserted block.
    """
    global header_printed

    if not header_printed:
        header = (
            f"{'Timestamp':20} | {'File':20} | {'Line':4} | {'Resp':7} | {'MSE':10} | {'Type':14} | Suggested Fix\n"
            + "-" * 120 + "\n"
        )
        gui_box.insert(tk.END, header)
        header_printed = True

    # prepare text for insertion
    row_text = (
        f"{record['timestamp']:20} | {record['file'][:20]:20} | {record['line']:4d} | "
        f"{record['resp']:7.2f} | {record['mse']:10.4f} | {record['anomaly_type'][:14]:14} | {record['suggested_fix']}\n"
    )
    reason_text = f"  Reason/Log: {record['reason']}\n"
    separator = "-" * 120 + "\n"

    # capture start index, insert, capture end index, then tag range
    start_index = gui_box.index(tk.END)
    gui_box.insert(tk.END, row_text)
    gui_box.insert(tk.END, reason_text)
    gui_box.insert(tk.END, separator)
    end_index = gui_box.index(tk.END)

    # determine tag name
    t = record['anomaly_type']
    if "CRITICAL" in t:
        tag = "crit"
    elif "HIGH" in t:
        tag = "high"
    elif "AUTH" in t or "ERROR" in t or "EXCEPTION" in t or "FAIL" in t:
        tag = "warn"
    elif "MEDIUM" in t:
        tag = "med"
    else:
        tag = "normal"

    try:
        gui_box.tag_add(tag, start_index, end_index)
    except Exception:
        pass

    gui_box.see(tk.END)

# --------------------
# anomaly append (store + csv + gui)
# --------------------
def append_anomaly(parsed, mse, gui_box):
    resp_value = parsed["features"]["resp"]
    raw_msg = parsed.get("raw", "")
    anomaly_type, fix, reason_hint = classify_anomaly(resp_value, raw_msg)
    record = {
        "timestamp": parsed["timestamp"],
        "file": parsed["source_file"],
        "line": parsed["line_number"],
        "resp": resp_value,
        "mse": float(mse),
        "anomaly_type": anomaly_type,
        "suggested_fix": fix,
        "reason": reason_hint or raw_msg
    }
    anomalies.append(record)

    # write append to default CSV immediately
    try:
        with open(CSV_REPORT_DEFAULT, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                record["timestamp"], record["file"], record["line"], record["resp"],
                record["mse"], record["anomaly_type"], record["suggested_fix"], record["reason"]
            ])
    except Exception:
        pass

    # schedule GUI insertion on main thread
    gui_box.after(0, gui_insert_row, gui_box, record)

    # update anomaly points (plot)
    anomaly_points.append((len(resp_history)-1 if resp_history else 0, record['resp']))

# --------------------
# Line processing
# --------------------
def process_line_gui(line, gui_box):
    parsed = parse_line(line)
    if not parsed:
        return

    resp = parsed['features']['resp']
    resp_history.append(resp)
    BUFFER.append(resp)

    # only score when buffer has required WINDOW
    if len(BUFFER) < WINDOW:
        return

    try:
        result = score_window(list(BUFFER))
    except Exception as e:
        # model error — print to GUI
        gui_box.after(0, lambda: gui_box.insert(tk.END, f"Model error: {e}\\n"))
        return

    if result.get('is_anomaly'):
        append_anomaly(parsed, result.get('mse', 0.0), gui_box)

# --------------------
# Monitoring: read existing lines then tail new lines
# --------------------
import glob

def monitor_log(gui_box):
    global monitoring, selected_log_file

    if not selected_log_file:
        gui_box.after(0, lambda: gui_box.insert(tk.END, "No folder selected.\n"))
        return

    folder = selected_log_file
    gui_box.after(0, lambda: gui_box.insert(tk.END, f"\n📁 Monitoring Folder: {folder}\n"))

    processed_files = {}

    while monitoring:
        try:
            log_files = glob.glob(folder + "/*.log") + \
                        glob.glob(folder + "/*.txt") + \
                        glob.glob(folder + "/*.csv")

            for file in log_files:
                if file not in processed_files:
                    processed_files[file] = 0  # start at line 0

                with open(file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                # process only new lines
                start = processed_files[file]
                new_lines = lines[start:]

                for line in new_lines:
                    if not monitoring:
                        break
                    # pass file name into parsed result
                    line_with_file = f"{file}::{line}"
                    process_line_gui(line_with_file, gui_box)

                processed_files[file] = len(lines)

            time.sleep(1)

        except Exception as e:
            gui_box.after(0, lambda: gui_box.insert(tk.END, f"Folder monitor error: {e}\n"))
            time.sleep(1)

    gui_box.after(0, lambda: gui_box.insert(tk.END, "🛑 Monitoring Stopped.\n"))

# --------------------
# GUI actions: select / start / stop
# --------------------
def select_log_file(label_widget):
    # Instead of selecting a single file, now select a folder
    global selected_log_file
    folder = filedialog.askdirectory(title="Select Folder Containing Log Files")

    if folder:
        selected_log_file = folder   # now this stores folder path
        label_widget.config(text=f"Selected Folder: {folder}")


def start_monitoring(gui_box):
    global monitoring, monitor_thread, selected_log_file, anomalies, header_printed

    if not selected_log_file:
        messagebox.showerror("Error", "Please select a log file first.")
        return

    init_csv_file(CSV_REPORT_DEFAULT)

    # clear previous GUI table and in-memory lists
    gui_box.delete("1.0", tk.END)
    header_printed = False
    anomalies = []
    resp_history.clear()
    BUFFER.clear()
    anomaly_points.clear()

    if monitoring:
        return

    monitoring = True
    monitor_thread = threading.Thread(target=monitor_log, args=(gui_box,), daemon=True)
    monitor_thread.start()

def stop_monitoring():
    global monitoring
    monitoring = False

# --------------------
# Export helpers
# --------------------
def export_csv():
    if not anomalies:
        messagebox.showinfo("Export CSV", "No anomalies to export.")
        return
    dest = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")], initialfile="anomaly_report.csv")
    if not dest:
        return
    try:
        with open(dest, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp","file","line","resp","mse","anomaly_type","suggested_fix","reason"])
            for r in anomalies:
                w.writerow([r["timestamp"], r["file"], r["line"], r["resp"], r["mse"], r["anomaly_type"], r["suggested_fix"], r["reason"]])
        messagebox.showinfo("Export CSV", f"CSV saved to: {dest}")
    except Exception as e:
        messagebox.showerror("Export CSV", f"Failed to save CSV: {e}")

import os
import platform
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from tkinter import filedialog, messagebox
import datetime

def export_pdf(auto_open=False):
    if not anomalies:
        messagebox.showinfo("Export PDF", "No anomalies to export.")
        return

    # Ask user for save path
    path = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF Files", "*.pdf")],
        initialfile="anomaly_report.pdf"
    )
    if not path:
        return

    # Setup document
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=40, rightMargin=40,
                            topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph("<b>Log Monitoring Report</b>", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                           styles["Normal"]))
    story.append(Spacer(1, 20))

    # Table of anomalies
    story.append(Paragraph("<b>Anomaly Summary</b>", styles["Heading2"]))
    story.append(Spacer(1, 6))
    table_data = [["Timestamp", "Severity", "Message", "File"]]
    for entry in anomalies:
        table_data.append([
            Paragraph(entry["timestamp"], styles["Normal"]),
            Paragraph(entry["anomaly_type"], styles["Normal"]),
            Paragraph(entry["suggested_fix"], styles["Normal"]),
            Paragraph(entry["file"], styles["Normal"])
        ])
    table = Table(table_data, colWidths=[100, 80, 250, 120], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))

    # Log contents
    story.append(Paragraph("<b>Log Contents</b>", styles["Heading2"]))
    story.append(Spacer(1, 6))
    log_text = log_box.get("1.0", "end")
    code_style = ParagraphStyle('Code', fontName='Courier', fontSize=8, leading=10)
    story.append(Preformatted(log_text, code_style))

    try:
        # Build PDF
        doc.build(story)
        messagebox.showinfo("Success", f"PDF Exported Successfully:\n{path}")

        # Auto-open safely
        if auto_open:
            if platform.system() == 'Windows':
                os.startfile(path)
            elif platform.system() == 'Darwin':  # macOS
                os.system(f"open '{path}'")
            else:  # Linux
                os.system(f"xdg-open '{path}'")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to export PDF:\n{e}")

# --------------------
# Create GUI
# --------------------
def create_gui():
    global header_printed

    root = tk.Tk()
    root.title("Real-Time Log Anomaly Detector")
    root.geometry("1000x800")

    # Top title
    title = tk.Label(root, text="AI Real-Time Log Anomaly Detector", font=("Arial", 18, "bold"))
    title.pack(pady=6)

    # File selection frame
    file_frame = tk.Frame(root)
    file_frame.pack(fill="x", padx=12)

    label_file = tk.Label(file_frame, text="No file selected", anchor="w")
    label_file.pack(side="left", padx=6, pady=6, fill="x", expand=True)

    btn_select = tk.Button(file_frame, text="Select Log File", command=lambda: select_log_file(label_file))
    btn_select.pack(side="right", padx=6)

    # Control buttons
    ctrl_frame = tk.Frame(root)
    ctrl_frame.pack(fill="x", padx=12, pady=6)

    btn_start = tk.Button(ctrl_frame, text="Start Monitoring", bg="#2e8b57", fg="white",
                          command=lambda: start_monitoring(log_box))
    btn_start.pack(side="left", padx=6)

    btn_stop = tk.Button(ctrl_frame, text="Stop Monitoring", bg="#a52a2a", fg="white",
                         command=stop_monitoring)
    btn_stop.pack(side="left", padx=6)

    btn_export_csv = tk.Button(ctrl_frame, text="Download CSV", command=export_csv)
    btn_export_csv.pack(side="right", padx=6)

    btn_export_pdf = tk.Button(ctrl_frame, text="Download PDF", command=export_pdf)
    btn_export_pdf.pack(side="right", padx=6)

    # Output text (table) - use monospace font for alignment
    text_frame = tk.Frame(root)
    text_frame.pack(fill="both", expand=False, padx=12)

    log_box = scrolledtext.ScrolledText(text_frame, width=130, height=18, font=("Courier", 10))
    log_box.pack(fill="both", expand=True)

    # configure color tags
    log_box.tag_config('crit', foreground='white', background='#b22222')   # dark red
    log_box.tag_config('high', foreground='black', background='#ffa500')   # orange
    log_box.tag_config('warn', foreground='black', background='#ffd700')   # yellow
    log_box.tag_config('med',  foreground='black', background='#87cefa')   # light blue
    log_box.tag_config('normal', foreground='black', background='white')

    # Plot area below table
    fig = Figure(figsize=(10, 3), dpi=100)
    ax = fig.add_subplot(111)
    ax.set_title("Response time (live)")
    ax.set_xlabel("Index")
    ax.set_ylabel("Resp")
    line_plot, = ax.plot([], [], '-o', markersize=2)
    scatter_plot = ax.scatter([], [], c='red', s=30)

    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack(fill='both', expand=False, padx=12, pady=(6,12))
    
    

    def update_plot():
        try:
            ys = list(resp_history)
            xs = list(range(len(ys)))
            if xs:
                line_plot.set_data(xs, ys)
                ax.relim()
                ax.autoscale_view()

            # draw anomaly points
            if anomaly_points:
                ax.collections.clear()
                xs_a = [p[0] for p in anomaly_points]
                ys_a = [p[1] for p in anomaly_points]
                ax.scatter(xs_a, ys_a, c='red', s=30)

            canvas.draw_idle()
        except Exception:
            pass
        root.after(2000, update_plot)

    root.after(2000, update_plot)

    # on close cleanup
    def on_closing():
        global monitoring
        if monitoring:
            if not messagebox.askyesno("Exit", "Monitoring is running. Stop and exit?"):
                return
            monitoring = False
            time.sleep(0.2)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

# --------------------
# main
# --------------------
if __name__ == "__main__":
    init_csv_file(CSV_REPORT_DEFAULT)
    create_gui()
