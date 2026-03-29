import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import pickle

# Load meta dataset
meta_df = pd.read_csv("meta_dataset.csv")

# Split features and target
X = meta_df.drop(columns=["risk"])
y = meta_df["risk"]

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42
)

# Train model
model = RandomForestClassifier()
model.fit(X_train, y_train)

# Evaluate
preds = model.predict(X_test)

print("Classification Report:\n")
print(classification_report(y_test, preds))

# Save model
pickle.dump(model, open("meta_model.pkl", "wb"))

print("\nMeta model saved as meta_model.pkl")