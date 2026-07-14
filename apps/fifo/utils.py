import pandas as pd


def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_number(value) -> float:
    if pd.isna(value):
        return 0.0
    text = str(value).replace(",", "").strip()
    if text == "":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df
