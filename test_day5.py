from predictor import predict_dataset_risk

# Test using an existing dataset
risk = predict_dataset_risk("data/wine.csv", "target")

print("Predicted Risk:", risk)