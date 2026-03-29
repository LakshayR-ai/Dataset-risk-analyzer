import pandas as pd
import pickle
from meta_features import extract_meta_features

def predict_dataset_risk(file_path, target_column):

    # Load trained meta model
    model = pickle.load(open("meta_model.pkl", "rb"))

    # Load new dataset
    df = pd.read_csv(file_path)

    # Extract meta features
    features = extract_meta_features(df, target_column)

    # Predict risk
    prediction = model.predict([features])

    return prediction[0]