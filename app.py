import base64
import json
import requests
import streamlit as st
from PIL import Image
from openai import OpenAI


# =========================================================
# 1. 基本設定
# =========================================================

st.set_page_config(
    page_title="托嬰中心 財產清冊",
    page_icon="🧸",
    layout="centered",
)

st.title("🧸 托嬰中心 財產清冊")

st.write(
    "上傳物品照片後會自動辨識品名、規格、數量、金額、用途及備註，"
    "確認後可直接將資料與照片同步到 Notion 財產清冊。"
)


# =========================================================
# 2. Session State 初始化
# =========================================================

if "ai_result" not in st.session_state:
    st.session_state.ai_result = None

if "last_uploaded_name" not in st.session_state:
    st.session_state.last_uploaded_name = None


# =========================================================
# 3. 側邊欄設定
# =========================================================

with st.sidebar:

    st.header("⚙️ API 設定")

    openai_api_key = st.text_input(
        "OpenAI API Key",
        type="password",
    )

    notion_token = st.text_input(
        "Notion Integration Token",
        type="password",
    )

    notion_database_id = st.text_input(
        "Notion Database ID",
        value="2b41493c6fe646d2a3dea2b0b8f37a3b",
    )

    st.divider()

    st.caption(
        "Notion 資料庫需包含以下欄位：\n"
        "品名、規格、數量、金額、用途、備註、照片"
    )


# =========================================================
# 4. 共用函式
# =========================================================


def encode_image(uploaded_file):
    """
    將 Streamlit UploadedFile 轉成 Base64。
    """
    return base64.b64encode(
        uploaded_file.getvalue()
    ).decode("utf-8")


def notion_headers(notion_token, json_content=True):
    """
    建立 Notion API Header。
    """
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2026-03-11",
    }

    if json_content:
        headers["Content-Type"] = "application/json"

    return headers


def clean_notion_id(raw_id):
    """
    清理 Notion ID。
    可以接受：
    - 32字元ID
    - 含 - 的 UUID
    - 貼入完整 Notion URL
    """

    raw_id = raw_id.strip()

    # 如果使用者貼的是完整網址
    if "notion.so" in raw_id or "notion.site" in raw_id:
        raw_id = raw_id.split("?")[0]
        raw_id = raw_id.rstrip("/").split("/")[-1]

        # 有些 Notion URL 前面會包含名稱
        # 最後 32 字元通常為 database id
        if len(raw_id) > 32:
            raw_id = raw_id[-32:]

    return raw_id


# =========================================================
# 5. 取得 Notion Data Source ID
# =========================================================


def get_notion_data_source_id(
    notion_token,
    database_id,
):

    database_id = clean_notion_id(database_id)

    url = (
        "https://api.notion.com/v1/databases/"
        f"{database_id}"
    )

    response = requests.get(
        url,
        headers=notion_headers(notion_token),
        timeout=30,
    )

    if not response.ok:
        raise Exception(
            "無法讀取 Notion Database。\n\n"
            f"HTTP {response.status_code}\n"
            f"{response.text}"
        )

    result = response.json()

    data_sources = result.get(
        "data_sources",
        [],
    )

    if not data_sources:
        raise Exception(
            "此 Notion Database 找不到 Data Source。\n"
            "請確認 Integration 已經連接此資料庫。"
        )

    # 一般資料庫通常只有一個 Data Source
    return data_sources[0]["id"]


# =========================================================
# 6. 直接上傳照片到 Notion
# =========================================================


def upload_image_to_notion(
    notion_token,
    uploaded_file,
):

    filename = uploaded_file.name

    content_type = (
        uploaded_file.type
        or "image/jpeg"
    )

    # -----------------------------------------------------
    # Step 1：建立 File Upload
    # -----------------------------------------------------

    create_url = (
        "https://api.notion.com/v1/file_uploads"
    )

    create_payload = {
        "mode": "single_part",
        "filename": filename,
        "content_type": content_type,
    }

    create_response = requests.post(
        create_url,
        headers=notion_headers(notion_token),
        json=create_payload,
        timeout=30,
    )

    if not create_response.ok:
        raise Exception(
            "建立 Notion 圖片上傳任務失敗。\n\n"
            f"HTTP {create_response.status_code}\n"
            f"{create_response.text}"
        )

    create_result = create_response.json()

    file_upload_id = create_result["id"]

    # -----------------------------------------------------
    # Step 2：傳送圖片實體檔案
    # -----------------------------------------------------

    send_url = (
        "https://api.notion.com/v1/"
        f"file_uploads/{file_upload_id}/send"
    )

    upload_headers = {
        "Authorization": (
            f"Bearer {notion_token}"
        ),
        "Notion-Version": "2026-03-11",
    }

    files = {
        "file": (
            filename,
            uploaded_file.getvalue(),
            content_type,
        )
    }

    send_response = requests.post(
        send_url,
        headers=upload_headers,
        files=files,
        timeout=60,
    )

    if not send_response.ok:
        raise Exception(
            "圖片傳送到 Notion 失敗。\n\n"
            f"HTTP {send_response.status_code}\n"
            f"{send_response.text}"
        )

    return file_upload_id


# =========================================================
# 7. 建立 Notion 財產資料
# =========================================================


def create_notion_item(
    notion_token,
    data_source_id,
    data,
    file_upload_id=None,
    uploaded_file=None,
):

    properties = {

        "品名": {
            "title": [
                {
                    "type": "text",
                    "text": {
                        "content": str(
                            data["name"]
                        )
                    },
                }
            ]
        },

        "規格": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": str(
                            data["spec"]
                        )
                    },
                }
            ]
        },

        "數量": {
            "number": int(
                data["qty"]
            )
        },

        "金額": {
            "number": float(
                data["price"]
            )
        },

        "用途": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": str(
                            data["purpose"]
                        )
                    },
                }
            ]
        },

        "備註": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": str(
                            data["remark"]
                        )
                    },
                }
            ]
        },
    }

    # -----------------------------------------------------
    # 如果照片上傳成功
    # -----------------------------------------------------

    if (
        file_upload_id
        and uploaded_file
    ):

        properties["照片"] = {
            "files": [
                {
                    "name": uploaded_file.name,
                    "type": "file_upload",
                    "file_upload": {
                        "id": file_upload_id
                    },
                }
            ]
        }

    # -----------------------------------------------------
    # 建立 Page
    # -----------------------------------------------------

    payload = {

        "parent": {
            "type": "data_source_id",
            "data_source_id": (
                data_source_id
            ),
        },

        "properties": properties,
    }

    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=notion_headers(
            notion_token
        ),
        json=payload,
        timeout=30,
    )

    if not response.ok:
        raise Exception(
            "建立 Notion 財產資料失敗。\n\n"
            f"HTTP {response.status_code}\n"
            f"{response.text}"
        )

    return response.json()


# =========================================================
# 8. OpenAI AI 圖片辨識
# =========================================================


def analyze_image(
    openai_api_key,
    uploaded_file,
):

    client = OpenAI(
        api_key=openai_api_key
    )

    base64_image = encode_image(
        uploaded_file
    )

    mime_type = (
        uploaded_file.type
        or "image/jpeg"
    )

    response = (
        client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一名專業的托嬰中心行政、"
                        "財產管理及採購助手。"
                        "\n\n"
                        "請根據照片辨識主要物品，"
                        "並估計合理的台灣市場價格。"
                        "\n\n"
                        "請嚴格只輸出 JSON，"
                        "不要加入 ```json 或其他說明。"
                        "\n\n"
                        "格式："
                        "\n"
                        "{"
                        '\n  "品名": "物品名稱",'
                        '\n  "規格": "品牌、型號、尺寸或材質",'
                        '\n  "數量": 1,'
                        '\n  "金額": 1000,'
                        '\n  "用途": "托嬰中心實際用途",'
                        '\n  "備註": "安全、使用或採購注意事項"'
                        "\n}"
                        "\n\n"
                        "規則："
                        "\n1. 無法確認品牌時，不要亂猜品牌。"
                        "\n2. 無法確認型號時，可描述尺寸、材質或外觀。"
                        "\n3. 金額只回傳數字，不要加入元或NT$。"
                        "\n4. 數量必須為整數。"
                        "\n5. 用途請以0-3歲托嬰中心情境描述。"
                        "\n6. 不確定資訊請在備註中註明。"
                    ),
                },

                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "請辨識照片中的主要財產物品。"
                            ),
                        },

                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{mime_type};"
                                    f"base64,{base64_image}"
                                )
                            },
                        },
                    ],
                },
            ],
            max_tokens=500,
            temperature=0.2,
        )
    )

    result_text = (
        response.choices[0]
        .message.content
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    return json.loads(
        result_text
    )


# =========================================================
# 9. 圖片上傳
# =========================================================


st.subheader("📷 1. 上傳物品照片")

uploaded_file = st.file_uploader(
    "選擇照片",
    type=[
        "jpg",
        "jpeg",
        "png",
        "webp",
    ],
)


# =========================================================
# 10. 如果換圖片，清除上一筆 AI 結果
# =========================================================

if uploaded_file is not None:

    if (
        st.session_state.last_uploaded_name
        != uploaded_file.name
    ):

        st.session_state.ai_result = None

        st.session_state.last_uploaded_name = (
            uploaded_file.name
        )


# =========================================================
# 11. 顯示圖片
# =========================================================

if uploaded_file is not None:

    try:

        image = Image.open(
            uploaded_file
        )

        st.image(
            image,
            caption="目前上傳照片",
            use_container_width=True,
        )

    except Exception:

        st.warning(
            "圖片預覽失敗，但仍可嘗試 AI 辨識。"
        )


# =========================================================
# 12. AI 辨識按鈕
# =========================================================

if uploaded_file is not None:

    if st.button(
        "🚀 開始 AI 辨識",
        type="primary",
        use_container_width=True,
    ):

        if not openai_api_key:

            st.error(
                "請先在左側輸入 OpenAI API Key。"
            )

        else:

            with st.spinner(
                "AI 正在分析物品..."
            ):

                try:

                    result = analyze_image(
                        openai_api_key,
                        uploaded_file,
                    )

                    st.session_state.ai_result = (
                        result
                    )

                    st.success(
                        "✅ AI 辨識完成！"
                    )

                except json.JSONDecodeError:

                    st.error(
                        "AI 回傳格式解析失敗，"
                        "請再按一次 AI 辨識。"
                    )

                except Exception as e:

                    st.error(
                        f"AI 辨識失敗：{e}"
                    )


# =========================================================
# 13. 辨識結果編輯區
# =========================================================

if st.session_state.ai_result:

    st.divider()

    st.subheader(
        "✏️ 2. 確認／修改資料"
    )

    result = (
        st.session_state.ai_result
    )

    edited_name = st.text_input(
        "品名",
        value=str(
            result.get(
                "品名",
                "",
            )
        ),
        key="edited_name",
    )

    edited_spec = st.text_input(
        "規格",
        value=str(
            result.get(
                "規格",
                "",
            )
        ),
        key="edited_spec",
    )

    col1, col2 = st.columns(2)

    with col1:

        try:
            default_qty = int(
                result.get(
                    "數量",
                    1,
                )
            )
        except Exception:
            default_qty = 1

        edited_qty = st.number_input(
            "數量",
            min_value=1,
            step=1,
            value=max(
                1,
                default_qty,
            ),
            key="edited_qty",
        )

    with col2:

        try:
            default_price = float(
                result.get(
                    "金額",
                    0,
                )
            )
        except Exception:
            default_price = 0.0

        edited_price = st.number_input(
            "金額",
            min_value=0.0,
            step=1.0,
            value=max(
                0.0,
                default_price,
            ),
            key="edited_price",
        )

    edited_purpose = st.text_area(
        "用途",
        value=str(
            result.get(
                "用途",
                "",
            )
        ),
        height=90,
        key="edited_purpose",
    )

    edited_remark = st.text_area(
        "備註",
        value=str(
            result.get(
                "備註",
                "",
            )
        ),
        height=90,
        key="edited_remark",
    )


    # =====================================================
    # 14. 預覽資料
    # =====================================================

    st.subheader(
        "👀 3. 資料預覽"
    )

    preview_data = {
        "品名": edited_name,
        "規格": edited_spec,
        "數量": int(
            edited_qty
        ),
        "金額": float(
            edited_price
        ),
        "用途": edited_purpose,
        "備註": edited_remark,
    }

    st.json(
        preview_data
    )


    # =====================================================
    # 15. 同步 Notion
    # =====================================================

    st.subheader(
        "📤 4. 同步 Notion"
    )

    sync_button = st.button(
        "📤 一鍵同步資料與照片至 Notion",
        type="primary",
        use_container_width=True,
    )

    if sync_button:

        # -------------------------------------------------
        # 檢查設定
        # -------------------------------------------------

        if not notion_token:

            st.error(
                "請先輸入 Notion Integration Token。"
            )

        elif not notion_database_id:

            st.error(
                "請先輸入 Notion Database ID。"
            )

        elif not edited_name.strip():

            st.error(
                "品名不可空白。"
            )

        elif uploaded_file is None:

            st.error(
                "找不到目前上傳的照片。"
            )

        else:

            with st.spinner(
                "正在上傳照片並建立 Notion 財產資料..."
            ):

                try:

                    # -------------------------------------
                    # Step 1
                    # Database ID → Data Source ID
                    # -------------------------------------

                    data_source_id = (
                        get_notion_data_source_id(
                            notion_token,
                            notion_database_id,
                        )
                    )

                    # -------------------------------------
                    # Step 2
                    # 圖片直接上傳 Notion
                    # -------------------------------------

                    file_upload_id = (
                        upload_image_to_notion(
                            notion_token,
                            uploaded_file,
                        )
                    )

                    # -------------------------------------
                    # Step 3
                    # 整理財產資料
                    # -------------------------------------

                    data = {
                        "name": edited_name,
                        "spec": edited_spec,
                        "qty": edited_qty,
                        "price": edited_price,
                        "purpose": edited_purpose,
                        "remark": edited_remark,
                    }

                    # -------------------------------------
                    # Step 4
                    # 建立 Notion Page
                    # -------------------------------------

                    page_result = (
                        create_notion_item(
                            notion_token=(
                                notion_token
                            ),
                            data_source_id=(
                                data_source_id
                            ),
                            data=data,
                            file_upload_id=(
                                file_upload_id
                            ),
                            uploaded_file=(
                                uploaded_file
                            ),
                        )
                    )

                    st.success(
                        "🎉 同步成功！"
                    )

                    st.success(
                        "資料與照片都已直接寫入 "
                        "Notion 財產清冊。"
                    )

                    # -------------------------------------
                    # Notion 頁面網址
                    # -------------------------------------

                    page_url = (
                        page_result.get(
                            "url"
                        )
                    )

                    if page_url:

                        st.link_button(
                            "🔗 開啟 Notion 資料",
                            page_url,
                            use_container_width=True,
                        )

                except Exception as e:

                    st.error(
                        "❌ Notion 同步失敗"
                    )

                    st.code(
                        str(e)
                    )


# =========================================================
# 16. 尚未上傳照片提示
# =========================================================

else:

    st.info(
        "👆 請先上傳一張物品照片開始盤點。"
    )
