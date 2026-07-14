from io import BytesIO
from typing import Iterable

import pandas as pd


def clean_header(value) -> str:
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


def flatten_candidates(column_config: dict) -> set[str]:
    candidates = set()

    for names in column_config.values():
        for name in names:
            candidates.add(clean_header(name))

    return candidates


def read_excel_upload(
    file_bytes: bytes,
    column_config: dict,
    file_label: str,
) -> pd.DataFrame:
    """
    Đọc toàn bộ sheet và tự chọn đúng sheet + dòng header
    dựa trên cấu hình cột của từng file.
    """

    excel_data = pd.read_excel(
        BytesIO(file_bytes),
        sheet_name=None,
        header=None,
    )

    candidates = flatten_candidates(column_config)

    best_sheet = None
    best_header_row = None
    best_score = -1
    best_headers = []

    for sheet_name, raw_df in excel_data.items():
        if raw_df.empty:
            continue

        max_rows = min(100, len(raw_df))

        for row_index in range(max_rows):
            row_values = (
                raw_df.iloc[row_index]
                .fillna("")
                .astype(str)
                .tolist()
            )

            normalized_values = {
                clean_header(value)
                for value in row_values
                if clean_header(value)
            }

            # Chỉ tính tên cột khớp chính xác, không tìm chuỗi con.
            # Vì dữ liệu VCD-2603... không được coi là header VCD.
            matched_headers = normalized_values.intersection(candidates)
            score = len(matched_headers)

            if score > best_score:
                best_score = score
                best_sheet = sheet_name
                best_header_row = row_index
                best_headers = row_values

    if best_sheet is None or best_header_row is None:
        raise ValueError(
            f"Không đọc được sheet nào trong file {file_label}"
        )

    # Với nghiệp vụ hiện tại phải nhận được ít nhất 3 cột cấu hình.
    if best_score < 3:
        raise ValueError(
            f"Không tìm thấy sheet/header phù hợp trong file {file_label}. "
            f"Sheet tốt nhất: {best_sheet}; "
            f"dòng header: {best_header_row + 1}; "
            f"điểm khớp: {best_score}; "
            f"giá trị dòng: {best_headers}"
        )

    df = pd.read_excel(
        BytesIO(file_bytes),
        sheet_name=best_sheet,
        header=best_header_row,
    )

    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")

    print(
        f"[{file_label}] sheet={best_sheet}, "
        f"header_row={best_header_row + 1}, "
        f"score={best_score}"
    )
    print(f"[{file_label}] columns={df.columns.tolist()}")

    return df