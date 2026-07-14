from io import BytesIO
import pandas as pd


def write_result_excel(
    result_df: pd.DataFrame,
    remain_df: pd.DataFrame,
    error_df: pd.DataFrame,
    customer_cols: list,
    invoice_cols: list,
) -> bytes:
    output = BytesIO()

    summary = pd.DataFrame([
        {"Metric": "Total customer rows", "Value": len(result_df) + len(error_df)},
        {"Metric": "Matched rows", "Value": len(result_df)},
        {"Metric": "Error rows", "Value": len(error_df)},
        {"Metric": "Remaining invoice rows", "Value": len(remain_df)},
        {"Metric": "Customer columns", "Value": str(customer_cols)},
        {"Metric": "Invoice columns", "Value": str(invoice_cols)},
    ])

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        sheets = {
            "Summary": summary,
            "Matched_Result": result_df,
            "Errors": error_df,
            "Invoice_Remain": remain_df,
        }

        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

        workbook = writer.book
        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#D9EAD3",
            "border": 1,
        })
        error_format = workbook.add_format({
            "bg_color": "#F4CCCC",
        })

        for sheet_name, df in sheets.items():
            worksheet = writer.sheets[sheet_name]

            for col_num, value in enumerate(df.columns):
                worksheet.write(0, col_num, str(value), header_format)

                if len(df) > 0:
                    max_data_len = (
                        df.iloc[:, col_num]
                        .fillna("")
                        .astype(str)
                        .map(len)
                        .max()
                    )
                    if pd.isna(max_data_len):
                        max_data_len = 0
                else:
                    max_data_len = 0

                width = min(
                    max(len(str(value)) + 2, int(max_data_len) + 2, 12),
                    50
                )

                worksheet.set_column(col_num, col_num, width)

            if len(df.columns) > 0:
                worksheet.freeze_panes(1, 0)
                worksheet.autofilter(
                    0,
                    0,
                    max(len(df), 1),
                    len(df.columns) - 1
                )

            if sheet_name == "Errors" and "error" in df.columns:
                error_col = list(df.columns).index("error")
                worksheet.conditional_format(
                    1,
                    error_col,
                    max(len(df), 1),
                    error_col,
                    {
                        "type": "text",
                        "criteria": "containing",
                        "value": "Không",
                        "format": error_format,
                    }
                )

    output.seek(0)
    return output.read()