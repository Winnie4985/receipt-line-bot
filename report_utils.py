import os

import pandas as pd
from dotenv import load_dotenv


load_dotenv()


def get_budget_from_env(name: str, default_value: int = 0) -> int:
    """從 .env 讀取預算額度。"""

    try:
        return int(os.getenv(name, default_value))
    except ValueError:
        return default_value


def get_upload_month(latest_invoice: dict) -> str:
    """根據最新一筆資料的上傳月份取得月份，例如 2026-06。"""

    upload_month = str(latest_invoice.get("上傳月份", "")).strip()

    if upload_month != "":
        return upload_month

    upload_time = pd.to_datetime(latest_invoice.get("上傳時間", ""), errors="coerce")

    if pd.isna(upload_time):
        return ""

    return upload_time.strftime("%Y-%m")


def filter_upload_month(invoice_data: pd.DataFrame, target_month: str) -> pd.DataFrame:
    """只保留指定上傳月份的資料。"""

    invoice_data = invoice_data.copy()

    if "上傳月份" not in invoice_data.columns:
        invoice_data["上傳月份"] = ""

    # 如果上傳月份是空的，就嘗試從上傳時間補
    invoice_data["上傳時間"] = pd.to_datetime(
        invoice_data.get("上傳時間", ""),
        errors="coerce"
    )

    missing_month = invoice_data["上傳月份"].isna() | (invoice_data["上傳月份"].astype(str).str.strip() == "")

    invoice_data.loc[missing_month, "上傳月份"] = (
        invoice_data.loc[missing_month, "上傳時間"].dt.strftime("%Y-%m")
    )

    return invoice_data[invoice_data["上傳月份"] == target_month]


def build_line_reply_text(invoice_data: pd.DataFrame, latest_invoice: dict) -> str:
    """產生 LINE 要回覆給使用者的統計文字。

    注意：
    Excel 記帳日期用憑證日期。
    LINE 統計月份用上傳月份。
    """

    target_month = get_upload_month(latest_invoice)

    if target_month == "":
        target_month_data = invoice_data.copy()
        month_title = "目前月份"
    else:
        target_month_data = filter_upload_month(invoice_data, target_month)
        month_title = target_month

    target_month_data["總計"] = pd.to_numeric(
        target_month_data["總計"],
        errors="coerce"
    ).fillna(0)

    # 各付款科目支出加總
    category_summary = (
        target_month_data.groupby("類別")["總計"]
        .sum()
        .sort_values(ascending=False)
    )

    category_lines = []

    if category_summary.empty:
        category_lines.append("目前該月份尚無資料")
    else:
        for category, amount in category_summary.items():
            category_lines.append(f"{category}：{int(amount):,} 元")

    # 額度設定
    entertainment_budget = get_budget_from_env("ENTERTAINMENT_BUDGET", 0)
    welfare_budget = get_budget_from_env("WELFARE_BUDGET", 0)

    entertainment_used = int(
        target_month_data.loc[
            target_month_data["類別"] == "交際費",
            "總計"
        ].sum()
    )

    welfare_used = int(
        target_month_data.loc[
            target_month_data["類別"] == "職工福利",
            "總計"
        ].sum()
    )

    entertainment_remaining = entertainment_budget - entertainment_used
    welfare_remaining = welfare_budget - welfare_used

    monthly_total = int(target_month_data["總計"].sum())

    reply_text = f"""發票已辨識並寫入會計 Excel。

本筆資料：
憑證日期：{latest_invoice.get("日期", "")}
上傳月份：{latest_invoice.get("上傳月份", "")}
類別：{latest_invoice.get("類別", "")}
摘要：{latest_invoice.get("摘要", "")}
總計：{int(latest_invoice.get("總計", 0)):,} 元

{month_title} 付款科目支出：
{chr(10).join(category_lines)}

交際費額度：
已使用：{entertainment_used:,} 元
額度上限：{entertainment_budget:,} 元
剩餘：{entertainment_remaining:,} 元

職工福利額度：
已使用：{welfare_used:,} 元
額度上限：{welfare_budget:,} 元
剩餘：{welfare_remaining:,} 元

{month_title} 總支出：{monthly_total:,} 元
"""

    return reply_text