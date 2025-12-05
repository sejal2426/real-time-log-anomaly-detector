# utils.py
def normalize(x):
    return (x - min(x)) / (max(x) - min(x) + 1e-9)
