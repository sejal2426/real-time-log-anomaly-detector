from lstm_score import score_window
import random

WINDOW = 50

# Normal test (should not be anomaly)
normal = [random.uniform(0.9, 1.1) for _ in range(WINDOW)]
print("Testing NORMAL sample:")
res1 = score_window(normal)
print(res1)
print()

# Anomaly test (should be anomaly)
anomaly = [random.uniform(5, 10) for _ in range(WINDOW)]
print("Testing ANOMALY sample:")
res2 = score_window(anomaly)
print(res2)
print()

print("Test completed.")
