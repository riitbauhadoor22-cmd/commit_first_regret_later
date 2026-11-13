import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

df = pd.read_csv('DATA/synthetic_loan_data.csv')

# print(df.shape)
# print(df.describe())
# print(df.head())
#print(df.columns.to_list())

feature_cols = ['monthly_income', 'monthly_expenses', 'existing_debt_payment', 'credit_score', 'age', 'debt_to_income_ratio']

X = df[feature_cols]
y = df['max_affordable_loan']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

predictions = model.predict(X_test)
mae = mean_absolute_error(y_test, predictions)
r2 = r2_score(y_test, predictions)

#for pitching
importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
print(importances)

print(f"Mean absolute error: {mae}")
print(f"r2_score: {r2}")

joblib.dump(model, 'AI_model/loan_amount_model.pkl')





# print(X_train.shape)
# print(X_test.shape)
# print(y_train.shape)
# print(y_test.shape)










