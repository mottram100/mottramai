from typing import Dict, List
import pandas as pd


def find_column(df: pd.DataFrame, candidates: List[str]) -> str | None:
    columns = [str(c).strip() for c in df.columns]
    lower_map = {c.lower(): c for c in columns}

    for name in candidates:
        name = str(name).strip()
        if name in columns:
            return name
        if name.lower() in lower_map:
            return lower_map[name.lower()]

    return None


def resolve_columns(df: pd.DataFrame, mapping: Dict[str, List[str]], file_label: str) -> Dict[str, str]:
    resolved = {}
    missing = []

    for key, candidates in mapping.items():
        col = find_column(df, candidates)
        if col:
            resolved[key] = col
        else:
            missing.append(key)

    if missing:
        raise ValueError(
            f"File {file_label} thiếu cột: {', '.join(missing)}. "
            f"Các cột hiện có: {list(df.columns)}"
        )

    return resolved
