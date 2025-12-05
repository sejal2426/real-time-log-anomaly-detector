# river_detector.py
from river import anomaly, preprocessing
from parser import parse_line

# Build model once
model = preprocessing.StandardScaler() | anomaly.HalfSpaceTrees(
    seed=42, n_trees=10, height=8
)

THRESHOLD = 0.6

def detect_river(line: str):
    parsed = parse_line(line)
    if parsed is None:
        return None

    x = parsed["features"]

    # River returns float score
    score = model.learn_one(x).score_one(x)

    if score > THRESHOLD:
        return {
            "source_file": parsed["source_file"],
            "line_number": parsed["line_number"],
            "anomaly_type": "river_high_score",
            "score": score,
            "context": parsed["raw"]
        }

    return None
