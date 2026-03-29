from meta_dataset_builder import build_meta_dataset

dataset_files = [
    "iris.csv",
    "breast_cancer.csv",
    "wine.csv",
    "digits.csv"
]
meta_df = build_meta_dataset(dataset_files)

print(meta_df)

meta_df.to_csv("meta_dataset.csv", index=False)

print("Meta dataset saved.")