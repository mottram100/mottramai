import re
from typing import Iterable, Optional

import pandas as pd

from .config import CUSTOMER_COLUMNS, INVOICE_COLUMNS, QTY_TOLERANCE


def clean_col(value) -> str:
    if value is None:
        return ""

    return (
        str(value)
        .replace("\n", "")
        .replace("\r", "")
        .replace("\t", "")
        .replace(" ", "")
        .strip()
        .lower()
    )


def clean_text(series: pd.Series) -> pd.Series:
    result = series.copy()
    result = result.where(result.notna(), "")
    result = result.astype(str).str.strip()
    result = result.str.replace(r"^(\d+)\.0$", r"\1", regex=True)
    return result


def parse_number(value) -> Optional[float]:
    if pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(" ", "").replace("，", ",")
    text = re.sub(r"[^0-9,.\-]", "", text)

    if not text:
        return None

    comma_count = text.count(",")
    dot_count = text.count(".")

    if comma_count > 0 and dot_count > 0:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif comma_count > 0:
        parts = text.split(",")
        if comma_count > 1 or len(parts[-1]) == 3:
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif dot_count > 0:
        parts = text.split(".")
        if dot_count > 1 or len(parts[-1]) == 3:
            text = text.replace(".", "")

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def clean_qty(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.apply(parse_number), errors="coerce")


def find_col(
    df: pd.DataFrame,
    candidates: Iterable[str],
) -> Optional[str]:
    normalized_columns = {
        clean_col(column): column
        for column in df.columns
    }

    for candidate in candidates:
        key = clean_col(candidate)
        if key in normalized_columns:
            return normalized_columns[key]

    return None


def require_column(
    df: pd.DataFrame,
    config: dict,
    key: str,
) -> Optional[str]:
    return find_col(df, config.get(key, []))


def prepare_customer(df: pd.DataFrame):
    df = df.copy()
    original_columns = list(df.columns)

    vcd_col = require_column(df, CUSTOMER_COLUMNS, "vcd")
    po_col = require_column(df, CUSTOMER_COLUMNS, "po")
    material_col = require_column(df, CUSTOMER_COLUMNS, "material")
    qty_col = require_column(df, CUSTOMER_COLUMNS, "qty")

    missing = []

    if vcd_col is None:
        missing.append("vcd")
    if po_col is None:
        missing.append("po")
    if material_col is None:
        missing.append("material")
    if qty_col is None:
        missing.append("qty")

    if missing:
        raise ValueError(
            f"File customer thiếu cột: {missing}. "
            f"Các cột hiện có: {original_columns}"
        )

    out = pd.DataFrame({
        "vcd": clean_text(df[vcd_col]),
        "po": clean_text(df[po_col]),
        "material": clean_text(df[material_col]),
        "qty": clean_qty(df[qty_col]).abs(),
        "_source_row": df.index + 2,
    })

    completely_empty = (
        out["vcd"].eq("")
        & out["po"].eq("")
        & out["material"].eq("")
        & out["qty"].isna()
    )

    out = out.loc[~completely_empty].copy()

    valid_mask = (
        out["vcd"].ne("")
        & out["po"].ne("")
        & out["material"].ne("")
        & out["qty"].notna()
        & out["qty"].gt(0)
    )

    valid_rows = out.loc[valid_mask].copy()
    invalid_rows = out.loc[~valid_mask].copy()

    if not invalid_rows.empty:
        invalid_rows["status"] = (
            "Thiếu VCD/PO/Material/Qty hoặc Qty <= 0"
        )

    return valid_rows, invalid_rows, original_columns


def prepare_invoice(df: pd.DataFrame):
    df = df.copy()
    original_columns = list(df.columns)

    vcd_col = require_column(df, INVOICE_COLUMNS, "vcd")
    invoice_col = require_column(df, INVOICE_COLUMNS, "invoice")
    material_col = require_column(df, INVOICE_COLUMNS, "material")
    qty_col = require_column(df, INVOICE_COLUMNS, "qty")

    missing = []

    if vcd_col is None:
        missing.append("vcd")
    if invoice_col is None:
        missing.append("invoice")
    if material_col is None:
        missing.append("material")
    if qty_col is None:
        missing.append("qty")

    if missing:
        raise ValueError(
            f"File invoice thiếu cột: {missing}. "
            f"Các cột hiện có: {original_columns}"
        )

    out = pd.DataFrame({
        "vcd": clean_text(df[vcd_col]),
        "invoice": clean_text(df[invoice_col]),
        "material": clean_text(df[material_col]),
        "qty": clean_qty(df[qty_col]).abs(),
        "_source_row": df.index + 2,
    })

    completely_empty = (
        out["vcd"].eq("")
        & out["invoice"].eq("")
        & out["material"].eq("")
        & out["qty"].isna()
    )

    out = out.loc[~completely_empty].copy()

    valid_mask = (
        out["vcd"].ne("")
        & out["invoice"].ne("")
        & out["material"].ne("")
        & out["qty"].notna()
        & out["qty"].gt(0)
    )

    valid_rows = out.loc[valid_mask].copy()
    invalid_rows = out.loc[~valid_mask].copy()

    if not invalid_rows.empty:
        invalid_rows["status"] = (
            "Thiếu VCD/Invoice/Material/Qty hoặc Qty <= 0"
        )

    return valid_rows, invalid_rows, original_columns


def join_unique(values) -> str:
    result = []
    seen = set()

    for value in values:
        if pd.isna(value):
            continue

        text = str(value).strip()
        if not text:
            continue

        if text not in seen:
            seen.add(text)
            result.append(text)

    return ", ".join(result)


def join_source_rows(values) -> str:
    return ", ".join(
        str(int(value))
        for value in values
        if pd.notna(value)
    )


def fifo_match(
    customer_df: pd.DataFrame,
    invoice_df: pd.DataFrame,
):
    match_keys = ["vcd", "material"]

    customer_grouped = (
        customer_df
        .groupby(match_keys, dropna=False, as_index=False)
        .agg(
            po=("po", join_unique),
            customer_qty=("qty", "sum"),
            customer_row_count=("qty", "size"),
            customer_source_rows=("_source_row", join_source_rows),
        )
    )

    invoice_grouped = (
        invoice_df
        .groupby(match_keys, dropna=False, as_index=False)
        .agg(
            invoice=("invoice", join_unique),
            invoice_qty=("qty", "sum"),
            invoice_row_count=("qty", "size"),
            invoice_source_rows=("_source_row", join_source_rows),
        )
    )

    comparison = customer_grouped.merge(
        invoice_grouped,
        on=match_keys,
        how="outer",
        indicator=True,
    )

    comparison["customer_qty"] = pd.to_numeric(
        comparison["customer_qty"],
        errors="coerce",
    ).fillna(0.0)

    comparison["invoice_qty"] = pd.to_numeric(
        comparison["invoice_qty"],
        errors="coerce",
    ).fillna(0.0)

    comparison["difference"] = (
        comparison["customer_qty"] - comparison["invoice_qty"]
    )
    comparison["absolute_difference"] = comparison["difference"].abs()

    def determine_status(row) -> str:
        if row["_merge"] == "left_only":
            return "Không có trong file invoice"
        if row["_merge"] == "right_only":
            return "Không có trong file customer"
        if row["absolute_difference"] <= QTY_TOLERANCE:
            return "Matched"
        return "Lệch số lượng"

    comparison["status"] = comparison.apply(
        determine_status,
        axis=1,
    )

    comparison = comparison.drop(columns=["_merge"])

    ordered_columns = [
        "vcd",
        "po",
        "invoice",
        "material",
        "customer_qty",
        "invoice_qty",
        "difference",
        "absolute_difference",
        "customer_row_count",
        "invoice_row_count",
        "customer_source_rows",
        "invoice_source_rows",
        "status",
    ]

    comparison = comparison.reindex(columns=ordered_columns)

    comparison = comparison.sort_values(
        by=["status", "vcd", "material"],
        na_position="last",
    ).reset_index(drop=True)

    result_df = comparison.loc[
        comparison["status"].eq("Matched")
    ].copy()

    error_df = comparison.loc[
        ~comparison["status"].eq("Matched")
    ].copy()

    remain_df = comparison.loc[
        comparison["status"].eq("Không có trong file customer")
        |
        (
            comparison["status"].eq("Lệch số lượng")
            & comparison["invoice_qty"].gt(
                comparison["customer_qty"]
            )
        )
    ].copy()

    return result_df, remain_df, error_df