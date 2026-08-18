import base64
import json
import os
from notion_client import Client
from openai import OpenAI
from PIL import Image
import streamlit as st

# 1. 頁面設定
st.set_page_config(
    page_title="托嬰中心 AI 盤點與採購助手", page_icon="🧸", layout="centered"
)

st.title("🧸 托嬰中心 AI 智慧盤點與 Notion 同步工具 (OpenAI 版)")
st.write("上傳物品照片，AI 將自動辨識欄位並一鍵同步至您的 Notion 資料庫！")

# 2. 手動輸入 API 金鑰與資料庫 ID
with st.sidebar:
  st.header("⚙️ 設定 API 金鑰")
  openai_api_key = st.text_input("OpenAI API Key", type="password")
  notion_token = st.text_input("Notion Integration Token", type="password")
  notion_database_id = st.text_input("Notion Database ID", type="text")


# 輔助函式：將圖片轉為 base64
def encode_image(uploaded_file):
  return base64.b64encode(uploaded_file.getvalue()).decode("utf-8")


# 3. 圖片上傳區
uploaded_file = st.file_uploader(
    "上傳物品照片", type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
  image = Image.open(uploaded_file)
  st.image(image, caption="已上傳的物品", use_column_width=True)

  if st.button("🚀 開始 AI 辨識 (OpenAI)"):
    if not openai_api_key:
      st.error("請先在左側欄位輸入 OpenAI API Key！")
    else:
      with st.spinner("OpenAI 正在分析物品中..."):
        try:
          client = OpenAI(api_key=openai_api_key)
          base64_image = encode_image(uploaded_file)

          response = client.chat.completions.create(
              model="gpt-4o",
              messages=[
                  {
                      "role": "system",
                      "content": (
                          "你是一個專業的托嬰中心行政與採購助手，請精準分析圖片中的物品，並嚴格以純"
                          " JSON 格式回傳（不要包含任何 markdown 程式碼區塊語法如 ```json），"
                          "格式如下：\n{\n  \"品名\": \"物品名稱\",\n "
                          ' "規格": "品牌、型號或尺寸規格",\n  "數量": 1,\n '
                          ' "金額": 預估合理市價數字（僅填數字）, \n '
                          ' "用途": "在托嬰中心的教育或照顧用途",\n  "備註":'
                          ' "其他注意事項"\n}'
                      ),
                  },
                  {
                      "role": "user",
                      "content": [
                          {
                              "type": "text",
                              "text": "請分析這張托嬰中心物品的照片並填寫對應欄位：",
                          },
                          {
                              "type": "image_url",
                              "image_url": {
                                  "url": (
                                      f"data:image/jpeg;base64,{base64_image}"
                                  )
                              },
                          },
                      ],
                  },
              ],
              max_tokens=300,
          )

          result_text = (
              response.choices[0]
              .message.content.replace("```json", "")
              .replace("```", "")
              .strip()
          )
          item_data = json.loads(result_text)

          st.success("辨識成功！請確認下方欄位內容：")

          edited_name = st.text_input("品名", item_data.get("品名", ""))
          edited_spec = st.text_input("規格", item_data.get("規格", ""))
          edited_qty = st.number_input(
              "數量", value=int(item_data.get("數量", 1))
          )
          edited_price = st.number_input(
              "金額", value=int(item_data.get("金額", 0))
          )
          edited_purpose = st.text_input("用途", item_data.get("用途", ""))
          edited_remark = st.text_input("備註", item_data.get("備註", ""))

          st.session_state["item_data"] = {
              "name": edited_name,
              "spec": edited_spec,
              "qty": edited_qty,
              "price": edited_price,
              "purpose": edited_purpose,
              "remark": edited_remark,
          }

        except Exception as e:
          st.error(f"辨識發生錯誤: {e}")

# 4. 同步到 Notion 按鈕
if "item_data" in st.session_state:
  if st.button("📤 一鍵同步至 Notion 資料庫"):
    if not notion_token or not notion_database_id:
      st.error("請先在左側欄位輸入 Notion Token 與 Database ID！")
    else:
      try:
        notion = Client(auth=notion_token)
        data = st.session_state["item_data"]

        notion.pages.create(
            parent={"database_id": notion_database_id},
            properties={
                "名稱": {
                    "title": [{"text": {"content": data["name"]}}]
                },
                "規格": {
                    "rich_text": [{"text": {"content": data["spec"]}}]
                },
                "數量": {"number": data["qty"]},
                "金額": {"number": data["price"]},
                "用途": {
                    "rich_text": [{"text": {"content": data["purpose"]}}]
                },
                "備註": {
                    "rich_text": [{"text": {"content": data["remark"]}}]
                },
            },
        )
        st.success("🎉 成功同步至 Notion！請至您的 Notion 資料庫查看。")
      except Exception as e:
        st.error(f"Notion 同步失敗: {e}")
