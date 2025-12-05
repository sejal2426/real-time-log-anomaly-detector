# lstm_train.py
import numpy as np
import pandas as pd
from tensorflow.keras import layers, models
from sklearn.preprocessing import StandardScaler
import joblib
import os

WINDOW = 50

# ------------------------------
# LOAD CSV FILE
# ------------------------------
df = pd.read_csv("../data/sample_timeseries.csv")   # adjust if needed
series = df["value"].values

# ------------------------------
# SCALE DATA
# ------------------------------
scaler = StandardScaler()
scaled_series = scaler.fit_transform(series.reshape(-1, 1)).flatten()

# ensure models dir exists (outside src/)
os.makedirs("../models", exist_ok=True)

joblib.dump(scaler, "../models/scaler.joblib")

# ------------------------------
# MAKE WINDOWS
# ------------------------------
def make_windows(arr):
    return np.array([arr[i:i + WINDOW] for i in range(len(arr) - WINDOW)]) \
        .reshape(-1, WINDOW, 1)

X = make_windows(scaled_series)

# ------------------------------
# LSTM AUTOENCODER
# ------------------------------
inp = layers.Input(shape=(WINDOW, 1))
x = layers.LSTM(64, return_sequences=True)(inp)
x = layers.LSTM(32)(x)
x = layers.RepeatVector(WINDOW)(x)
x = layers.LSTM(32, return_sequences=True)(x)
x = layers.LSTM(64, return_sequences=True)(x)
out = layers.TimeDistributed(layers.Dense(1))(x)

model = models.Model(inp, out)
model.compile(optimizer="adam", loss="mse")

# ------------------------------
# TRAIN
# ------------------------------
model.fit(X, X, epochs=5, batch_size=32)

# ------------------------------
# THRESHOLD CALCULATION
# ------------------------------
recon = model.predict(X)
mse = np.mean((recon - X) ** 2, axis=(1, 2))
threshold = mse.mean() + 3 * mse.std()

joblib.dump(threshold, "../models/lstm_threshold.joblib")

# save trained autoencoder
model.save("../models/lstm_autoencoder.h5")

print("TRAINED. Threshold:", threshold)
