from sklearn.datasets import load_iris
import pandas as pd
from meta_features import extract_meta_features

data = load_iris()
df = pd.DataFrame(data.data, columns=data.feature_names)
df["target"] = data.target

features = extract_meta_features(df, "target")
print(features)
