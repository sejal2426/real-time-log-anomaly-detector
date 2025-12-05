# gui.py
import tkinter as tk
from tkinter import filedialog, messagebox
from river_detector import detect_river
from parser import parse_line
from lstm_score import score_window
from collections import deque

WINDOW = 50
buffer = deque(maxlen=WINDOW)

def select_file():
    path = filedialog.askopenfilename(
        title="Select log file",
        filetypes=[("Log files", "*.log"), ("All files", "*.*")]
    )
    if path:
        run_detection(path)

def run_detection(path):
    output.delete("1.0", tk.END)

    with open(path, "r") as f:
        for raw in f:
            parsed = parse_line(raw)
            if not parsed:
                continue

            resp = parsed["features"]["resp"]
            buffer.append(resp)

            river_result = detect_river(raw)
            if river_result:
                output.insert(tk.END, f"RIVER DETECTED: {river_result}\n")

                if len(buffer) == WINDOW:
                    lstm_result = score_window(list(buffer))

                    if lstm_result["is_anomaly"]:
                        output.insert(tk.END,
                                      f"  --> LSTM CONFIRMED! MSE={lstm_result['mse']}\n")
                    else:
                        output.insert(tk.END, "  --> LSTM rejected (normal).\n")

    messagebox.showinfo("Done", "Detection finished!")

root = tk.Tk()
root.title("Anomaly Detection System")

btn = tk.Button(root, text="Select Log File", command=select_file)
btn.pack(pady=10)

output = tk.Text(root, width=120, height=30)
output.pack()

root.mainloop()
