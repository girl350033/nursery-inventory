import os
import streamlit as st
import google.generativeai as genai
from notion_client import Client
from PIL import Image

# 1. 頁面設定
st.set_page_config(
    page_title="托嬰中心 AI 盤點與採購助手", page_icon="🧸", layout="centered"
)

st.title("🧸 托嬰中心 AI 智慧盤點與 Notion 同步工具")
st.write("上傳物品照片，AI 將自動辨識欄位並一鍵同步至您的 Notion 資料庫！")

# 2. 設定 API 金鑰（您可以從 Streamlit Secrets 或介面輸入）
with st.sidebar:
  st.header("⚙️ 設定 API 金鑰")
  gemini_api_key = st.text_input("Gemini API Key", type="password")
  notion_token = st.text_input("Notion Integration Token", type="password")
  notion_database_id = st.text_input("Notion Database ID", type="text")

# 3. 圖片上傳區
uploaded_file = st.file_uploader(
    "上傳物品照片", type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
  image = Image.open(uploaded_file)
  st.image(image, caption="已上傳的物品", use_column_width=True)

  if st.button("🚀 開始 AI 辨識"):
    if not gemini_api_key:
      st.error("請先在左側欄位輸入 Gemini API Key！")
    else:
      with st.spinner("AI 正在分析物品中..."):
        try:
          # 初始化 Gemini
          genai.configure(api_key=gemini_api_key)
          # 使用支援多模態的模型 (例如 gemini-2.5-flash 或 gemini-1.5-flash)
          model = genai.GenerativeModel("gemini-1.5-flash")

          prompt = (
              "請分析這張托嬰中心物品的照片，並回傳以下格式的 JSON 資料（不要包含額外文字）："
              "{"
              '"品名": "物品名稱",'
              '"規格": "品牌、型號或尺寸規格",'
              '"數量": 1,'
              '"金額": 預估合理市價數字（僅填數字）,'
              '"用途": "在托嬰中心的教育或照顧用途",'
              '"備註": "其他注意事項"'
              "}"
          )

          response = model.generate_content([image, prompt])
          import json

          # 解析 AI 回傳的 JSON
          result_text = (
              response.text.replace("```json", "")
              .replace("```", "")
              .strip()
          )
          item_data = json.loads(result_text)

          st.success("辨識成功！請確認下方欄位內容：")

          # 讓使用者可以手動微調
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

          # 儲存到 Session State 以便下一步同步
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

        # 對應 Notion 資料庫的欄位結構寫入
        notion.pages.create(
            parent={"database_id": notion_database_id},
            properties={
                "名稱": {
                    "title": [{"text": {"content": data["name"]}}]
                },  # 假設 Notion 標題欄位叫「名稱」
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
