from io import BytesIO
import logging

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .config import CUSTOMER_COLUMNS, INVOICE_COLUMNS
from .excel_reader import read_excel_upload
from .excel_writer import write_result_excel
from .matcher import fifo_match, prepare_customer, prepare_invoice


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Inventory FIFO Matcher",
    version="1.0.0",
)


@app.get("/")
def health_check():
    return {
        "status": "OK",
        "service": "Inventory FIFO Matcher",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }


@app.post("/match-excel")
async def match_excel(
    customer_file: UploadFile = File(...),
    invoice_file: UploadFile = File(...),
):
    try:
        # Đọc dữ liệu file upload
        customer_bytes = await customer_file.read()
        invoice_bytes = await invoice_file.read()

        if not customer_bytes:
            raise ValueError("File customer đang rỗng.")

        if not invoice_bytes:
            raise ValueError("File invoice đang rỗng.")

        logger.info(
            "Customer file: %s - %s bytes",
            customer_file.filename,
            len(customer_bytes),
        )

        logger.info(
            "Invoice file: %s - %s bytes",
            invoice_file.filename,
            len(invoice_bytes),
        )

        # Đọc Excel và tự xác định dòng tiêu đề
        customer_raw = read_excel_upload(
            file_bytes=customer_bytes,
            column_config=CUSTOMER_COLUMNS,
            file_label="customer",
        )

        invoice_raw = read_excel_upload(
            file_bytes=invoice_bytes,
            column_config=INVOICE_COLUMNS,
            file_label="invoice",
        )

        logger.info(
            "CUSTOMER COLUMNS: %s",
            customer_raw.columns.tolist(),
        )

        logger.info(
            "INVOICE COLUMNS: %s",
            invoice_raw.columns.tolist(),
        )

        # Chuẩn hóa dữ liệu
        customer_df, customer_invalid, customer_cols = prepare_customer(
            customer_raw
        )

        invoice_df, invoice_invalid, invoice_cols = prepare_invoice(
            invoice_raw
        )

        logger.info(
            "Customer valid rows: %s",
            len(customer_df),
        )

        logger.info(
            "Invoice valid rows: %s",
            len(invoice_df),
        )

        # Đối chiếu FIFO
        result_df, remain_df, error_df = fifo_match(
            customer_df,
            invoice_df,
        )

        # Gom các dòng không hợp lệ vào sheet lỗi
        invalid_frames = []

        if customer_invalid is not None and not customer_invalid.empty:
            customer_invalid = customer_invalid.copy()
            customer_invalid["source_file"] = "customer"
            customer_invalid["error_type"] = "invalid_input"
            invalid_frames.append(customer_invalid)

        if invoice_invalid is not None and not invoice_invalid.empty:
            invoice_invalid = invoice_invalid.copy()
            invoice_invalid["source_file"] = "invoice"
            invoice_invalid["error_type"] = "invalid_input"
            invalid_frames.append(invoice_invalid)

        if invalid_frames:
            invalid_df = pd.concat(
                invalid_frames,
                ignore_index=True,
                sort=False,
            )

            if error_df is None or error_df.empty:
                error_df = invalid_df
            else:
                error_df = pd.concat(
                    [error_df, invalid_df],
                    ignore_index=True,
                    sort=False,
                )

        # Bảo đảm các DataFrame không bị None
        if result_df is None:
            result_df = pd.DataFrame()

        if remain_df is None:
            remain_df = pd.DataFrame()

        if error_df is None:
            error_df = pd.DataFrame()

        logger.info(
            "Matched rows: %s | Remaining rows: %s | Error rows: %s",
            len(result_df),
            len(remain_df),
            len(error_df),
        )

        # Xuất file Excel kết quả
        result_bytes = write_result_excel(
            result_df=result_df,
            remain_df=remain_df,
            error_df=error_df,
            customer_cols=customer_cols,
            invoice_cols=invoice_cols,
        )

        return StreamingResponse(
            BytesIO(result_bytes),
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": (
                    'attachment; filename="fifo_match_result.xlsx"'
                )
            },
        )

    except ValueError as exc:
        logger.warning("Dữ liệu đầu vào không hợp lệ: %s", exc)

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Lỗi khi xử lý đối chiếu Excel")

        raise HTTPException(
            status_code=500,
            detail=f"Lỗi hệ thống: {type(exc).__name__}: {exc}",
        ) from exc