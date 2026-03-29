def assign_risk(train_acc, test_acc, gap):

    if gap > 0.15:
        return "Overfitting Risk"

    elif train_acc < 0.6 and test_acc < 0.6:
        return "Underfitting Risk"

    else:
        return "Safe Dataset"