import pandas as pd
from baseline_model import evaluate_dataset
from risk_label import assign_risk

datasets = ["iris.csv", "breast_cancer.csv"]

for file in datasets:
    print("\nTesting:", file)

    df = pd.read_csv(f"data/{file}")

    train_acc, test_acc, gap = evaluate_dataset(df, "target")

    print("Train Accuracy:", train_acc)
    print("Test Accuracy:", test_acc)
    print("Gap:", gap)

    risk = assign_risk(train_acc, test_acc, gap)

    print("Predicted Risk:", risk)
    