import streamlit as st
import requests
import time
from configs.page_config import setup_page
from utils.image_util import load_image_base64
from utils.motivations import get_motivation

# --- Cấu hình trang ---
setup_page()
logo_image = load_image_base64("asset/logo.png")
icon_user = load_image_base64("asset/user.png")
icon_assistant = load_image_base64("asset/logo2.png")

logo_image = load_image_base64("asset/logo.png")

st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Alice&display=swap" rel="stylesheet">
<style>
.fixed-header {{
    position: relative;
    top: 35px;
    width: calc(100% - 30px);
    background-color: white;
    z-index: 9999;
    display: flex;
    align-items: center;
}}
</style>

<div class="fixed-header">
    <img src="data:image/png;base64,{logo_image}" width="100" style="margin-right:15px;" />
    <div>
        <h1 style="
            font-size: 40px;
            margin-bottom:0px;
        ">Chat với VSignChat</h1>
        <p style="
            font-size: 16px; color: #626262;">Hệ thống trả lời thông minh với dữ liệu chính xác.</p>
    </div>
</div>

<!-- Thêm khoảng trắng để nội dung không bị header che khuất -->
<div style="height:65px;"></div>
""", unsafe_allow_html=True)

# --- CẤU HÌNH ---
AGENT_SERVER_URL = "http://127.0.0.1:8000/chat"
PRACTICE_PAGE_NAME = "Recognition"

# --- KHỞI TẠO SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

if "sign_to_practice" not in st.session_state:
    st.session_state.sign_to_practice = None

# --- HÀM HELPER HIỂN THỊ MEDIA ---
def render_media_from_metadata(media_data):
    """
    Hiển thị media từ object {image: url, video: url}.
    Chỉ hiển thị những gì Backend đã xác nhận là đúng chunk.
    """
    if not media_data:
        return

    image_url = media_data.get("image")
    video_url = media_data.get("video")

    # Container cho media để giao diện gọn gàng
    with st.container():
        if video_url:
            st.video(video_url, format="video/mp4", start_time=0)
            if image_url:
                # Nếu có video thì ảnh chỉ là phụ, cho vào expander hoặc hiển thị nhỏ
                with st.expander("Xem hình ảnh minh họa"):
                    st.image(image_url, width=400)
        elif image_url:
            # Nếu không có video thì hiển thị ảnh to
            st.image(image_url, caption="Hình minh họa", width=400)

# --- 1. HIỂN THỊ LỊCH SỬ CHAT ---
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=message["avatar"]):
        st.markdown(message["content"])
        # Nếu tin nhắn là của AI và có media đính kèm, hiển thị nó
        if message["role"] == "assistant" and "media" in message:
            render_media_from_metadata(message["media"])

# --- 2. XỬ LÝ INPUT NGƯỜI DÙNG ---
if prompt := st.chat_input("Hỏi về ký hiệu (ví dụ: 'Ký hiệu cảm ơn', 'Số 5')..."):
    # Hiển thị câu hỏi
    st.chat_message("user", avatar="data:image/png;base64," + icon_user).markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "data:image/png;base64," + icon_user})

    # Xử lý trả lời
    with st.chat_message("assistant", avatar="data:image/png;base64," + icon_assistant):
        message_placeholder = st.empty()
        message_placeholder.markdown("Đang tìm kiếm thông tin chính xác...")
        
        try:
            # Gửi request
            response = requests.post(
                AGENT_SERVER_URL,
                json={"message": prompt, "thread_id": "session_v1"},
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                
                ai_response_text = data.get("response", "")
                media_data = data.get("media", {}) 
                action_payload = data.get("action")

                # --- Xử lý Action Luyện tập ---
                if action_payload and action_payload.get("action") == "START_PRACTICE":
                    sign_name = action_payload.get("sign")
                    display_name = f"'{sign_name}'" if sign_name else "này"
                    st.session_state.sign_to_practice = sign_name
                    
                    link_md = (
                        f"\n\n---\n**Thực hành ngay:** "
                        f"[Mở Camera để luyện tập {display_name}](/{PRACTICE_PAGE_NAME})"
                    )
                    ai_response_text += link_md

                # --- Hiển thị ---
                message_placeholder.empty()
                st.markdown(ai_response_text)
                
                # Gọi hàm hiển thị media (Logic Strict Mapping từ backend đảm bảo media này là chuẩn)
                if media_data and (media_data.get("video") or media_data.get("image")):
                    st.info("Tài liệu minh họa:")
                    render_media_from_metadata(media_data)
                
                # --- Lưu State ---
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": ai_response_text,
                    "avatar": "data:image/png;base64," + icon_assistant,
                    "media": media_data # Lưu media để hiển thị lại khi reload
                })
                
            else:
                err = f"Lỗi Server: {response.status_code}"
                message_placeholder.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err, "avatar": "data:image/png;base64," + icon_assistant})

        except Exception as e:
            err = f"Không thể kết nối: {str(e)}"
            message_placeholder.error(err)
            st.session_state.messages.append({"role": "assistant", "content": err, "avatar": "data:image/png;base64," + icon_assistant})

# --- SIDEBAR ---
with st.sidebar:
    quote = get_motivation()
    st.sidebar.markdown(
        f"""
        <div style="
            padding: 15px;
            border-radius: 10px;
            background-color: #f1f3ff;
            border-left: 5px solid #4851ba;
            font-size: 16px;
            ">
            <b>💡 Động lực hôm nay</b><br>
            {quote}
        </div>
        <div style="height:20px;"></div>
        """,
        unsafe_allow_html=True
    )
    if st.button("Xóa hội thoại"):
        st.session_state.messages = []
        st.rerun()