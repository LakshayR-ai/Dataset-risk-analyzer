"""
predictor.py
------------
Loads the trained meta-model and predicts the risk category
for a new dataset file.

Usage:
    python predictor.py
    or import predict_dataset_risk() in other modules.
"""

import os
import pickle
import pandas as pd
from meta_features import extract_meta_features

MODEL_PATH = os.path.join(os.path.dirname(__file__), "meta_model.pkl")


def predict_dataset_risk(file_path: str, target_column: str) -> str:
    """
    Predict the ML risk category for a dataset.

    Parameters
    ----------
    file_path     : Path to the CSV dataset file
    target_column : Name of the target/label column

    Returns
    -------
    str : "Safe Dataset" | "Overfitting Risk" | "Underfitting Risk"

    Raises
    ------
    FileNotFoundError : if model or dataset file is missing
    ValueError        : if target column not found
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Meta-model not found at {MODEL_PATH}. Run meta_model.py first."
        )
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset file not found: {file_path}")

    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    df = pd.read_csv(file_path)

    if target_column not in df.columns:
        raise ValueError(
            f"Target column '{target_column}' not found. "
            f"Available: {df.columns.tolist()}"
        )

    features = extract_meta_features(df, target_column)
    prediction = model.predict([features])[0]
    return str(prediction)


if __name__ == "__main__":
    # Quick smoke-test
    test_file = os.path.join("data", "iris.csv")
    if os.path.exists(test_file):
        result = predict_dataset_risk(test_file, "target")
        print(f"Predicted Risk for iris.csv: {result}")
    else:
        print("Place iris.csv in data/ to test predictor.")
