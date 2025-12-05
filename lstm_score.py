# lstm_score.py
import numpy as np
import joblib
from tensorflow.keras.models import load_model

WINDOW = 50

# Load trained components
import os
import tensorflow as tf

BASE = os.path.dirname(os.path.dirname(__file__))   # go up from src/

scaler = joblib.load(os.path.join(BASE, "models", "scaler.joblib"))
threshold = joblib.load(os.path.join(BASE, "models", "lstm_threshold.joblib"))


def mse_loss(y_true, y_pred):
    return tf.reduce_mean(tf.math.squared_difference(y_true, y_pred))

model = load_model(
    os.path.join(BASE, "models", "lstm_autoencoder.h5"),
    compile=False   # IMPORTANT: prevents Keras from trying to load 'mse'
)

# Now compile manually (optional)
model.compile(optimizer="adam", loss=mse_loss)


def score_window(window_values):
    """
    Takes a window of 50 'resp' values and returns:
    - mse (float)
    - is_anomaly (bool)
    """

    if len(window_values) != WINDOW:
        raise ValueError(f"Window must be {WINDOW} values long")

    # Convert to numpy array
    arr = np.array(window_values).reshape(-1, 1)

    # Scale using saved scaler
    scaled = scaler.transform(arr).reshape(1, WINDOW, 1)

    # Reconstruct with autoencoder
    recon = model.predict(scaled, verbose=0)

    # Calculate reconstruction MSE
    mse = float(np.mean((recon - scaled)**2))

    # Determine anomaly using threshold
    is_anomaly = mse > threshold

    return {
        "mse": mse,
        "is_anomaly": is_anomaly
    }
