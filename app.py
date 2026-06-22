import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from ai_invoice_parser import parse_invoice_image
from report_utils import build_line_reply_text

EXCEL_PATH = Path("exports") / "invoice_report.xlsx"


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
]


def load_existing_data():
    """讀取舊的 Excel 資料；如果 Excel 還不存在，就先建立一張空表格。"""

    if EXCEL_PATH.exists():
        invoice_data = pd.read_excel(EXCEL_PATH, sheet_name="發票明細")

        # 刪除舊 Excel 裡所有「編號」相關欄位，避免每次執行都多一欄
        invoice_data = invoice_data.loc[
            :, ~invoice_data.columns.astype(str).str.startswith("編號")
        ]

        # 如果舊檔案缺少新欄位，就補上
        for column in EXPECTED_COLUMNS:
            if column not in invoice_data.columns:
                invoice_data[column] = ""

        # 只保留目前需要的欄位，避免舊欄位殘留
        invoice_data = invoice_data[EXPECTED_COLUMNS]

        return invoice_data

    return pd.DataFrame(columns=EXPECTED_COLUMNS)


def clean_number(value) -> int:
    """把金額欄位轉成整數。看不懂就回傳 0。"""

    if pd.isna(value):
        return 0

    value_text = str(value)
    value_text = value_text.replace(",", "")
    value_text = value_text.replace("元", "")
    value_text = value_text.replace("NT$", "")
    value_text = value_text.strip()

    try:
        return int(float(value_text))
    except ValueError:
        return 0


def clean_invoice_data(invoice: dict) -> dict:
    """清理並檢查 AI 辨識結果。"""

    cleaned = {}

    for column in EXPECTED_COLUMNS:
        cleaned[column] = invoice.get(column, "")

    # 類型固定為支出
    cleaned["類型"] = "支出"

    # 類別限制在固定選項
    allowed_categories = [
    "進貨成本",
    "薪資支出",
    "租金支出",
    "水電瓦斯費",
    "旅費／交通費",
    "運費",
    "廣告費",
    "郵電費",
    "保險費",
    "職工福利",
    "交際費",
    "勞務費／專業服務費",
    "文具用品",
    "雜項購置",
    "修繕費",
    "稅捐",
    "銀行手續費",
    "利息支出",
    "折舊費用",
    "攤銷費用",
    "教育訓練費",
    "佣金支出",
    "會費",
    "捐贈",
    "呆帳損失",
    "其他",
]
    if cleaned["類別"] not in allowed_categories:
        cleaned["類別"] = "其他"

    # 發票號碼：2 個大寫英文字母 + 8 個數字
    invoice_number = str(cleaned["發票號碼"]).strip().upper()
    invoice_number = invoice_number.replace(" ", "").replace("-", "")

    if re.fullmatch(r"[A-Z]{2}\d{8}", invoice_number):
        cleaned["發票號碼"] = invoice_number
    else:
        cleaned["發票號碼"] = ""
        cleaned["需人工確認"] = "是"

    # 店家統編：只能是 8 個數字
    seller_tax_id = str(cleaned["店家統編"]).strip()
    seller_tax_id = re.sub(r"\D", "", seller_tax_id)

    if re.fullmatch(r"\d{8}", seller_tax_id):
        cleaned["店家統編"] = seller_tax_id
    else:
        cleaned["店家統編"] = ""
        cleaned["需人工確認"] = "是"

    # 金額欄位轉數字
    cleaned["銷售額合計"] = clean_number(cleaned["銷售額合計"])
    cleaned["營業稅"] = clean_number(cleaned["營業稅"])
    cleaned["總計"] = clean_number(cleaned["總計"])

    # 摘要不可為空
    if str(cleaned["摘要"]).strip() == "":
        cleaned["摘要"] = "未判斷"
        cleaned["需人工確認"] = "是"

    # 付款方式不可為空
    if str(cleaned["付款方式"]).strip() == "":
        cleaned["付款方式"] = "未知"

    # 資料來源固定
    cleaned["資料來源"] = "AI圖片辨識"

    upload_time = datetime.now()

    cleaned["上傳時間"] = upload_time.strftime("%Y-%m-%d %H:%M:%S")
    cleaned["上傳月份"] = upload_time.strftime("%Y-%m")

    # 預設仍需人工確認，因為發票最終要給會計核對
    if str(cleaned["需人工確認"]).strip() == "":
        cleaned["需人工確認"] = "是"

    return cleaned


def save_to_excel(invoice_data: pd.DataFrame):
    """把表格存成 Excel。"""

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 刪除所有「編號」相關欄位
    invoice_data = invoice_data.loc[
        :, ~invoice_data.columns.astype(str).str.startswith("編號")
    ]

    # 補齊欄位
    for column in EXPECTED_COLUMNS:
        if column not in invoice_data.columns:
            invoice_data[column] = ""

    invoice_data = invoice_data[EXPECTED_COLUMNS]

    # 金額欄位轉成數字，避免 Excel 統計錯誤
    invoice_data["銷售額合計"] = invoice_data["銷售額合計"].apply(clean_number)
    invoice_data["營業稅"] = invoice_data["營業稅"].apply(clean_number)
    invoice_data["總計"] = invoice_data["總計"].apply(clean_number)

    total_count = len(invoice_data)
    total_amount = invoice_data["銷售額合計"].sum()
    total_tax = invoice_data["營業稅"].sum()
    total = invoice_data["總計"].sum()

    summary_df = pd.DataFrame(
        {
            "項目": ["總筆數", "總銷售額合計", "總營業稅", "總額"],
            "數值": [total_count, total_amount, total_tax, total],
        }
    )

    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        invoice_data.to_excel(
            writer,
            sheet_name="發票明細",
            index=True,
            index_label="編號",
        )
        summary_df.to_excel(writer, sheet_name="統計摘要", index=False)


def main():
    Path("receipts").mkdir(parents=True, exist_ok=True)

    invoice_data = load_existing_data()

    image_name = input("請輸入發票圖片檔名，例如 test.jpg：")
    image_path = Path("receipts") / image_name

    if not image_path.exists():
        print(f"找不到圖片：{image_path}")
        print("請確認圖片已經放在 receipts 資料夾裡。")
        return

    print("正在使用 AI 辨識發票圖片，請稍等...")

    new_invoice = parse_invoice_image(str(image_path))

    # 清理與格式檢查 AI 辨識結果
    new_invoice = clean_invoice_data(new_invoice)

    new_row = pd.DataFrame([new_invoice])

    invoice_data = pd.concat([invoice_data, new_row], ignore_index=True)

    # 依照日期排序
    invoice_data["日期"] = pd.to_datetime(invoice_data["日期"], errors="coerce")
    invoice_data = invoice_data.sort_values(by="日期")

    # 日期轉回 YYYY-MM-DD 字串，避免 Excel 顯示 00:00:00
    invoice_data["日期"] = invoice_data["日期"].dt.strftime("%Y-%m-%d")

    # 排序後重新編號，從 1 開始
    invoice_data.index = range(1, len(invoice_data) + 1)

    save_to_excel(invoice_data)

    reply_text = build_line_reply_text(invoice_data, new_invoice)

    print(reply_text)

    print("已新增一筆發票資料")
    print(f"圖片路徑：{image_path}")
    print(f"目前總筆數：{len(invoice_data)}")
    print(f"已匯出 Excel：{EXCEL_PATH}")


if __name__ == "__main__":
    main()