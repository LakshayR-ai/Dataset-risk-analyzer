import pandas as pd
from meta_features import extract_meta_features
from baseline_model import evaluate_dataset
from risk_label import assign_risk

def build_meta_dataset(dataset_files):

    rows = []

    for file in dataset_files:
        print("Processing:", file)

        df = pd.read_csv(f"data/{file}")

        # Extract meta features
        features = extract_meta_features(df, "target")

        # Train baseline model
        train_acc, test_acc, gap = evaluate_dataset(df, "target")

        # Assign risk
        risk = assign_risk(train_acc, test_acc, gap)

        row = features + [risk]

        rows.append(row)

    columns = [
        "n_samples",
        "n_features",
        "ratio",
        "variance",
        "correlation",
        "imbalance",
        "missing",
        "risk"
    ]

    meta_df = pd.DataFrame(rows, columns=columns)

    return meta_df