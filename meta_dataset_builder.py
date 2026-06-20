"""
meta_dataset_builder.py
-----------------------
Builds meta_dataset.csv by processing a list of datasets,
extracting meta-features, training a baseline model, and assigning risk labels.

Usage:
    python meta_dataset_builder.py

Each dataset file must be in the data/ folder and have a 'target' column.
"""

import os
import pandas as pd
from meta_features import extract_meta_features
from baseline_model import evaluate_dataset
from risk_label import assign_risk

COLUMNS = [
    "n_samples", "n_features", "ratio", "variance", "correlation",
    "imbalance", "missing", "skewness", "duplicate_pct", "outlier_pct", "risk",
]


def build_meta_dataset(dataset_files: list[str], data_dir: str = "data") -> pd.DataFrame:
    """
    Build a meta-dataset from a list of CSV filenames.

    Parameters
    ----------
    dataset_files : list of CSV filenames (expected in data_dir/)
    data_dir      : directory containing the CSV files

    Returns
    -------
    pd.DataFrame with meta-features and risk labels
    """
    rows = []

    for file in dataset_files:
        filepath = os.path.join(data_dir, file)
        print(f"\nProcessing: {filepath}")

        try:
            df = pd.read_csv(filepath)

            if "target" not in df.columns:
                print(f"  [SKIP] No 'target' column found in {file}")
                continue

            # Extract meta-features (10 features)
            features = extract_meta_features(df, "target")

            # Train baseline model and get accuracy metrics
            train_acc, test_acc, gap = evaluate_dataset(df, "target")
            print(f"  train_acc={train_acc:.4f}  test_acc={test_acc:.4f}  gap={gap:.4f}")

            # Assign risk label using both model metrics and meta-features
            n_samples = features[0]
            imbalance = features[5]
            missing = features[6]
            risk = assign_risk(train_acc, test_acc, gap, n_samples, imbalance, missing)
            print(f"  risk={risk}")

            rows.append(features + [risk])

        except Exception as e:
            print(f"  [ERROR] {file}: {e}")
            continue

    if not rows:
        raise RuntimeError("No datasets were successfully processed.")

    return pd.DataFrame(rows, columns=COLUMNS)


if __name__ == "__main__":
    dataset_files = ["iris.csv", "breast_cancer.csv", "wine.csv", "digits.csv"]
    meta_df = build_meta_dataset(dataset_files)
    print("\n--- Meta Dataset ---")
    print(meta_df)
    meta_df.to_csv("meta_dataset.csv", index=False)
    print("\nMeta dataset saved to meta_dataset.csv")
