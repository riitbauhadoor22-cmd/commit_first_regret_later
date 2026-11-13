# train_loan_risk_model.py — trains the Loans tab risk model on REAL loan outcomes (Lending Club, Kaggle
# "All Lending Club loan data"). It predicts the probability that a personal loan is NOT repaid (default),
# from ratios only (no FICO, grade, zip code, age or other personal/demographic fields).
# Output: AI_model/loan_risk_model.pkl (the model) + AI_model/loan_risk_model_card.json (facts about it).
#
# Run (from the project root, takes a few minutes on the 1.2 GB file):
#   backend\venv\Scripts\python backend\train_loan_risk_model.py --input backend\DATA\lending_club\loan.csv --out-dir backend\AI_model
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

# ===== SETTINGS =====
HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "DATA" / "lending_club" / "loan.csv"
DEFAULT_OUT_DIR = HERE / "AI_model"
MODEL_FILE = "loan_risk_model.pkl"
CARD_FILE = "loan_risk_model_card.json"
LAST_YEAR = 2015  # loans issued after 2015 were mostly still running when the data was collected
COLUMNS = ["loan_amnt", "term", "int_rate", "installment", "annual_inc", "issue_d", "loan_status", "dti", "delinq_2yrs"]
# The model's inputs, in this order (routes/loans.py builds the same columns)
FEATURES = ["payment_to_income", "dti", "loan_to_income", "int_rate", "term_months", "missed_payment"]
# +1 = more of this can only raise the risk (keeps the answer sensible and the amount search monotonic); 0 = free
MONOTONIC = [1, 1, 1, 1, 0, 1]
# Final outcomes only. "Does not meet the credit policy. Status:X" loans (2007–2010) are real loans with a real
# outcome X, issued under LC's older rules — we keep them with the outcome X.
LABELS = {"Fully Paid": 0, "Charged Off": 1, "Default": 1,
          "Does not meet the credit policy. Status:Fully Paid": 0,
          "Does not meet the credit policy. Status:Charged Off": 1}
BANDS = [(0, 0.10, "<10%"), (0.10, 0.20, "10-20%"), (0.20, 0.30, "20-30%"), (0.30, np.inf, ">30%")]
MAX_LOAN_TO_INCOME = 5  # a loan over 5 years of income is treated as a data error


# ===== LOAD + CLEAN =====
def to_number(series):
    """'13.56%' / ' 13.56' / 13.56 → 13.56 (NaN if it isn't a number)."""
    return pd.to_numeric(series.astype(str).str.strip().str.rstrip("%"), errors="coerce")


def clean_chunk(chunk, removed):
    """Keeps finished loans up to LAST_YEAR with sane values; counts what was removed (and why) in `removed`."""
    def drop(mask, reason):  # mask = rows to remove
        nonlocal chunk
        removed[reason] = removed.get(reason, 0) + int(mask.sum())
        chunk = chunk[~mask]

    drop(~chunk["loan_status"].isin(LABELS), "no final outcome (Current, Late, In Grace Period, ...)")
    issued = pd.to_datetime(chunk["issue_d"], format="%b-%Y", errors="coerce")  # e.g. "Dec-2015"
    drop(issued.isna() | (issued.dt.year > LAST_YEAR), f"issued after {LAST_YEAR} (or no issue date)")
    issued = issued[chunk.index]

    rows = pd.DataFrame(index=chunk.index)
    rows["issue_month"] = issued.dt.strftime("%Y-%m")
    rows["default"] = chunk["loan_status"].map(LABELS)
    annual_inc = pd.to_numeric(chunk["annual_inc"], errors="coerce")
    rows["payment_to_income"] = pd.to_numeric(chunk["installment"], errors="coerce") / (annual_inc / 12)
    rows["dti"] = pd.to_numeric(chunk["dti"], errors="coerce") / 100  # LC dti is in % and excludes this loan
    rows["loan_to_income"] = pd.to_numeric(chunk["loan_amnt"], errors="coerce") / annual_inc
    rows["int_rate"] = to_number(chunk["int_rate"])  # stays in % (13.56), like the rate typed in the app
    rows["term_months"] = pd.to_numeric(chunk["term"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    delinq = pd.to_numeric(chunk["delinq_2yrs"], errors="coerce")
    rows["missed_payment"] = (delinq > 0).astype(int).where(delinq.notna())  # NaN stays NaN → dropped below

    def drop_rows(mask, reason):
        nonlocal rows
        removed[reason] = removed.get(reason, 0) + int(mask.sum())
        rows = rows[~mask]

    drop_rows(annual_inc.reindex(rows.index).isna() | (annual_inc.reindex(rows.index) <= 0), "income missing or <= 0")
    drop_rows(rows[FEATURES].isna().any(axis=1) | ~np.isfinite(rows[FEATURES]).all(axis=1), "missing feature value")
    drop_rows((rows["dti"] < 0) | (rows["dti"] > 1), "dti below 0% or above 100%")
    drop_rows((rows["payment_to_income"] <= 0) | (rows["payment_to_income"] > 1)
              | (rows["loan_to_income"] <= 0) | (rows["loan_to_income"] > MAX_LOAN_TO_INCOME),
              "extreme payment or loan size (installment > monthly income, loan > 5x income, or <= 0)")
    drop_rows((rows["int_rate"] <= 0) | (rows["int_rate"] > 100) | ~rows["term_months"].isin([36, 60]),
              "odd interest rate or term")
    return rows


def load_data(path, chunksize=200_000):
    removed, parts, total = {}, [], 0
    for chunk in pd.read_csv(path, usecols=COLUMNS, chunksize=chunksize, low_memory=False):
        total += len(chunk)
        parts.append(clean_chunk(chunk, removed))
    return pd.concat(parts, ignore_index=True), removed, total


# ===== REPORT HELPERS =====
def band_table(data):
    """Real default rate for each payment-to-income band."""
    table = []
    for low, high, name in BANDS:
        part = data[(data["payment_to_income"] >= low) & (data["payment_to_income"] < high)]
        rate = float(part["default"].mean()) if len(part) else None
        table.append({"payment_to_income": name, "loans": int(len(part)),
                      "default_rate": round(rate, 4) if rate is not None else None})
    return table


# ===== TRAIN =====
def train(input_path, out_dir):
    out_dir = Path(out_dir)
    data, removed, total = load_data(input_path)
    print(f"Read {total:,} loans; using {len(data):,}.")
    for reason, count in removed.items():
        print(f"  removed {count:,}: {reason}")

    X, y = data[FEATURES], data["default"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, monotonic_cst=MONOTONIC, random_state=42)
    model.fit(X_train, y_train)
    auc = float(roc_auc_score(y_test, model.predict_proba(X_test)[:, 1]))

    card = {
        "dataset": "All Lending Club loan data",
        "source": "Kaggle - All Lending Club loan data (Lending Club, USA)",
        "rows_read": total,
        "rows_used": int(len(data)),
        "rows_removed": removed,
        "date_from": data["issue_month"].min(),
        "date_to": data["issue_month"].max(),
        "label": "1 = Charged Off / Default, 0 = Fully Paid (incl. 'Does not meet the credit policy' loans with that outcome)",
        "features": FEATURES,
        "feature_notes": {
            "payment_to_income": "monthly installment / (annual_inc / 12)",
            "dti": "LC dti / 100: existing monthly debt payments (excluding this loan and mortgage) / monthly income",
            "loan_to_income": "loan_amnt / annual_inc",
            "int_rate": "interest rate in % a year",
            "term_months": "36 or 60 (the app clips its term to this range)",
            "missed_payment": "1 if delinq_2yrs > 0 (30+ days late in the last 2 years); the app asks about 12 months",
        },
        "model": "HistGradientBoostingClassifier (monotonic: risk never goes down when a burden ratio goes up)",
        "test_roc_auc": round(auc, 4),
        "base_default_rate": round(float(y.mean()), 4),
        "payment_to_income_bands": band_table(data),
        "split": "80/20 stratified, random_state=42",
        "training_date": date.today().isoformat(),
        "sklearn_version": sklearn.__version__,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / MODEL_FILE)
    (out_dir / CARD_FILE).write_text(json.dumps(card, indent=2), encoding="utf-8")
    print(f"Test ROC-AUC {auc:.3f}, base default rate {card['base_default_rate']:.1%}, "
          f"{card['date_from']} to {card['date_to']}")
    for band in card["payment_to_income_bands"]:
        print(f"  payment/income {band['payment_to_income']}: {band['loans']:,} loans, default rate {band['default_rate']}")
    print(f"Saved {out_dir / MODEL_FILE} and {out_dir / CARD_FILE}")
    return card


# ===== START =====
def main(argv=None):
    parser = argparse.ArgumentParser(description="Train the loan risk model on Lending Club data.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="path to loan.csv")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="folder for the .pkl and the model card")
    args = parser.parse_args(argv)
    return train(args.input, args.out_dir)


if __name__ == "__main__":
    main(sys.argv[1:])
