import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, request

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import ImageMessage, MessageEvent, TextMessage, TextSendMessage

from ai_invoice_parser import parse_invoice_image

from app import clean_invoice_data

from google_sheets_utils import (
    append_invoice_to_sheet,
    load_existing_data_from_sheet,
)

from report_utils import build_line_reply_text


load_dotenv(override=True)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")


if not LINE_CHANNEL_ACCESS_TOKEN:
    raise ValueError("缺少 LINE_CHANNEL_ACCESS_TOKEN，請檢查 .env")

if not LINE_CHANNEL_SECRET:
    raise ValueError("缺少 LINE_CHANNEL_SECRET，請檢查 .env")


app = Flask(__name__)

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


@app.route("/", methods=["GET"])
def home():
    return "LINE Receipt Bot is running."


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="請直接拍照或上傳發票圖片。")
    )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        Path("receipts").mkdir(parents=True, exist_ok=True)

        image_file_name = f"line_{uuid.uuid4().hex}.jpg"
        image_path = Path("receipts") / image_file_name

        message_content = line_bot_api.get_message_content(event.message.id)

        with open(image_path, "wb") as file:
            for chunk in message_content.iter_content():
                file.write(chunk)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="✅ 已收到發票圖片\n🔄 正在辨識並寫入 Excel，請稍等～")
        )

        new_invoice = parse_invoice_image(str(image_path))
        new_invoice = clean_invoice_data(new_invoice)

        # 記錄 LINE 使用者 ID，之後可以分業務統計
        new_invoice["LINE使用者ID"] = event.source.user_id

        # 寫入 Google Sheets
        append_invoice_to_sheet(new_invoice)

        # 從 Google Sheets 重新讀取資料，用來計算 LINE 回覆統計
        invoice_data = load_existing_data_from_sheet()

        reply_text = build_line_reply_text(invoice_data, new_invoice)

        line_bot_api.push_message(
            event.source.user_id,
            TextSendMessage(text=reply_text)
        )

    except Exception as error:
        line_bot_api.push_message(
            event.source.user_id,
            TextSendMessage(text=f"處理失敗：{error}")
        )


if __name__ == "__main__":
    app.run(port=5000, debug=False)