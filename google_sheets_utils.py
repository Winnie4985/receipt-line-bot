import json
import os

import gspread
import pandas as pd
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials


load_dotenv(override=True)


SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "會計發票紀錄")
WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "發票明細")


EXPECTED_COLUMNS = [
    "日期",
    "上傳時間",
    "上傳月份",
    "類型",
    "類別",
    "摘要",
    "店家名稱",
    "店家統編",
    "發票號碼",
    "銷售額合計",
    "營業稅",
    "總計",
    "付款方式",
    "憑證圖片路徑",
    "資料來源",
    "需人工確認",
    "LINE使用者ID",
]


def get_gspread_client():
    """建立 Google Sheets client。"""

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not credentials_json:
        raise ValueError("缺少 GOOGLE_SERVICE_ACCOUNT_JSON，請檢查 .env。")

    service_account_info = json.loads(credentials_json)

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes,
    )

    return gspread.authorize(credentials)


def get_worksheet():
    """取得 Google Sheet 工作表。"""

    client = get_gspread_client()
    spreadsheet = client.open(SHEET_NAME)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME,
            rows=1000,
            cols=len(EXPECTED_COLUMNS),
        )

    return worksheet


def ensure_header(worksheet):
    """確認第一列是欄位名稱。"""

    first_row = worksheet.row_values(1)

    if first_row != EXPECTED_COLUMNS:
        worksheet.clear()
        worksheet.append_row(EXPECTED_COLUMNS)


def load_existing_data_from_sheet() -> pd.DataFrame:
    """從 Google Sheets 讀取既有資料。"""

    worksheet = get_worksheet()
    ensure_header(worksheet)

    records = worksheet.get_all_records()

    if not records:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    invoice_data = pd.DataFrame(records)

    for column in EXPECTED_COLUMNS:
        if column not in invoice_data.columns:
            invoice_data[column] = ""

    invoice_data = invoice_data[EXPECTED_COLUMNS]

    return invoice_data


def append_invoice_to_sheet(invoice: dict):
    """新增一筆發票資料到 Google Sheets。"""

    worksheet = get_worksheet()
    ensure_header(worksheet)

    row = []

    for column in EXPECTED_COLUMNS:
        value = invoice.get(column, "")

        if pd.isna(value):
            value = ""

        row.append(value)

    worksheet.append_row(row, value_input_option="USER_ENTERED")