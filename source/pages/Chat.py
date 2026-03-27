# import streamlit as st
# import requests
# import time
# from configs.page_config import setup_page
# from utils.image_util import load_image_base64
# from utils.motivations import get_motivation

# # --- Cấu hình trang ---
# setup_page()
# logo_image = load_image_base64("asset/logo.png")
# icon_user = load_image_base64("asset/user.png")
# icon_assistant = load_image_base64("asset/logo2.png")

# logo_image = load_image_base64("asset/logo.png")

# st.markdown(f"""
# <link href="https://fonts.googleapis.com/css2?family=Alice&display=swap" rel="stylesheet">
# <style>
# .fixed-header {{
#     position: relative;
#     top: 35px;
#     width: calc(100% - 30px);
#     background-color: white;
#     z-index: 9999;
#     display: flex;
#     align-items: center;
# }}
# </style>

# <div class="fixed-header">
#     <img src="data:image/png;base64,{logo_image}" width="100" style="margin-right:15px;" />
#     <div>
#         <h1 style="
#             font-size: 40px;
#             margin-bottom:0px;
#         ">Chat với VSignChat</h1>
#         <p style="
#             font-size: 16px; color: #626262;">Hệ thống trả lời thông minh với dữ liệu chính xác.</p>
#     </div>
# </div>

# <!-- Thêm khoảng trắng để nội dung không bị header che khuất -->
# <div style="height:65px;"></div>
# """, unsafe_allow_html=True)

# # --- CẤU HÌNH ---
# AGENT_SERVER_URL = "http://127.0.0.1:8000/chat"
# PRACTICE_PAGE_NAME = "Recognition"

# # --- KHỞI TẠO SESSION STATE ---
# if "messages" not in st.session_state:
#     st.session_state.messages = []

# if "sign_to_practice" not in st.session_state:
#     st.session_state.sign_to_practice = None

# # --- HÀM HELPER HIỂN THỊ MEDIA ---
# def render_media_from_metadata(media_data):
#     """
#     Hiển thị media từ object {image: url, video: url}.
#     Chỉ hiển thị những gì Backend đã xác nhận là đúng chunk.
#     """
#     if not media_data:
#         return

#     image_url = media_data.get("image")
#     video_url = media_data.get("video")

#     # Container cho media để giao diện gọn gàng
#     with st.container():
#         if video_url:
#             st.video(video_url, format="video/mp4", start_time=0)
#             if image_url:
#                 # Nếu có video thì ảnh chỉ là phụ, cho vào expander hoặc hiển thị nhỏ
#                 with st.expander("Xem hình ảnh minh họa"):
#                     st.image(image_url, width=400)
#         elif image_url:
#             # Nếu không có video thì hiển thị ảnh to
#             st.image(image_url, caption="Hình minh họa", width=400)

# # --- 1. HIỂN THỊ LỊCH SỬ CHAT ---
# for message in st.session_state.messages:
#     with st.chat_message(message["role"], avatar=message["avatar"]):
#         st.markdown(message["content"])
#         # Nếu tin nhắn là của AI và có media đính kèm, hiển thị nó
#         if message["role"] == "assistant" and "media" in message:
#             render_media_from_metadata(message["media"])

# # --- 2. XỬ LÝ INPUT NGƯỜI DÙNG ---
# if prompt := st.chat_input("Hỏi về ký hiệu (ví dụ: 'Ký hiệu cảm ơn', 'Số 5')..."):
#     # Hiển thị câu hỏi
#     st.chat_message("user", avatar="data:image/png;base64," + icon_user).markdown(prompt)
#     st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "data:image/png;base64," + icon_user})

#     # Xử lý trả lời
#     with st.chat_message("assistant", avatar="data:image/png;base64," + icon_assistant):
#         message_placeholder = st.empty()
#         message_placeholder.markdown("Đang tìm kiếm thông tin chính xác...")
        
#         try:
#             # Gửi request
#             response = requests.post(
#                 AGENT_SERVER_URL,
#                 json={"message": prompt, "thread_id": "session_v1"},
#                 timeout=60
#             )
            
#             if response.status_code == 200:
#                 data = response.json()
                
#                 ai_response_text = data.get("response", "")
#                 media_data = data.get("media", {}) 
#                 action_payload = data.get("action")

#                 # --- Xử lý Action Luyện tập ---
#                 if action_payload and action_payload.get("action") == "START_PRACTICE":
#                     sign_name = action_payload.get("sign")
#                     display_name = f"'{sign_name}'" if sign_name else "này"
#                     st.session_state.sign_to_practice = sign_name
                    
#                     link_md = (
#                         f"\n\n---\n**Thực hành ngay:** "
#                         f"[Mở Camera để luyện tập {display_name}](/{PRACTICE_PAGE_NAME})"
#                     )
#                     ai_response_text += link_md

#                 # --- Hiển thị ---
#                 message_placeholder.empty()
#                 st.markdown(ai_response_text)
                
#                 # Gọi hàm hiển thị media (Logic Strict Mapping từ backend đảm bảo media này là chuẩn)
#                 if media_data and (media_data.get("video") or media_data.get("image")):
#                     st.info("Tài liệu minh họa:")
#                     render_media_from_metadata(media_data)
                
#                 # --- Lưu State ---
#                 st.session_state.messages.append({
#                     "role": "assistant", 
#                     "content": ai_response_text,
#                     "avatar": "data:image/png;base64," + icon_assistant,
#                     "media": media_data # Lưu media để hiển thị lại khi reload
#                 })
                
#             else:
#                 err = f"Lỗi Server: {response.status_code}"
#                 message_placeholder.error(err)
#                 st.session_state.messages.append({"role": "assistant", "content": err, "avatar": "data:image/png;base64," + icon_assistant})

#         except Exception as e:
#             err = f"Không thể kết nối: {str(e)}"
#             message_placeholder.error(err)
#             st.session_state.messages.append({"role": "assistant", "content": err, "avatar": "data:image/png;base64," + icon_assistant})

# # --- SIDEBAR ---
# with st.sidebar:
#     quote = get_motivation()
#     st.sidebar.markdown(
#         f"""
#         <div style="
#             padding: 15px;
#             border-radius: 10px;
#             background-color: #f1f3ff;
#             border-left: 5px solid #4851ba;
#             font-size: 16px;
#             ">
#             <b>💡 Động lực hôm nay</b><br>
#             {quote}
#         </div>
#         <div style="height:20px;"></div>
#         """,
#         unsafe_allow_html=True
#     )
#     if st.button("Xóa hội thoại"):
#         st.session_state.messages = []
#         st.rerun()
# import streamlit as st
# import requests
# import time
# from configs.page_config import setup_page
# from utils.image_util import load_image_base64
# from utils.motivations import get_motivation

# # --- Cấu hình trang ---
# setup_page()
# logo_image = load_image_base64("asset/logo.png")
# icon_user = load_image_base64("asset/user.png")
# icon_assistant = load_image_base64("asset/logo2.png")

# logo_image = load_image_base64("asset/logo.png")

# st.markdown(f"""
# <link href="https://fonts.googleapis.com/css2?family=Alice&display=swap" rel="stylesheet">
# <style>
# .fixed-header {{
#     position: relative;
#     top: 35px;
#     width: calc(100% - 30px);
#     background-color: white;
#     z-index: 9999;
#     display: flex;
#     align-items: center;
# }}
# </style>

# <div class="fixed-header">
#     <img src="data:image/png;base64,{logo_image}" width="100" style="margin-right:15px;" />
#     <div>
#         <h1 style="
#             font-size: 40px;
#             margin-bottom:0px;
#         ">Chat với VSignChat</h1>
#         <p style="
#             font-size: 16px; color: #626262;">Hệ thống trả lời thông minh với dữ liệu chính xác.</p>
#     </div>
# </div>

# <!-- Thêm khoảng trắng để nội dung không bị header che khuất -->
# <div style="height:65px;"></div>
# """, unsafe_allow_html=True)

# # --- CẤU HÌNH ---
# AGENT_SERVER_URL = "http://127.0.0.1:8000/chat"
# PRACTICE_PAGE_NAME = "Recognition"

# # --- KHỞI TẠO SESSION STATE ---
# if "messages" not in st.session_state:
#     st.session_state.messages = []

# if "sign_to_practice" not in st.session_state:
#     st.session_state.sign_to_practice = None

# # --- HÀM HELPER HIỂN THỊ MEDIA ---
# def render_media_from_metadata(media_data):
#     """
#     Hiển thị media từ object {image: url, video: url}.
#     Chỉ hiển thị những gì Backend đã xác nhận là đúng chunk.
#     """
#     if not media_data:
#         return

#     image_url = media_data.get("image")
#     video_url = media_data.get("video")

#     # Container cho media để giao diện gọn gàng
#     with st.container():
#         if video_url:
#             st.video(video_url, format="video/mp4", start_time=0)
#             if image_url:
#                 # Nếu có video thì ảnh chỉ là phụ, cho vào expander hoặc hiển thị nhỏ
#                 with st.expander("Xem hình ảnh minh họa"):
#                     st.image(image_url, width=400)
#         elif image_url:
#             # Nếu không có video thì hiển thị ảnh to
#             st.image(image_url, caption="Hình minh họa", width=400)

# # --- 1. HIỂN THỊ LỊCH SỬ CHAT ---
# for message in st.session_state.messages:
#     with st.chat_message(message["role"], avatar=message["avatar"]):
#         st.markdown(message["content"])
#         # Nếu tin nhắn là của AI và có media đính kèm, hiển thị nó
#         if message["role"] == "assistant" and "media" in message:
#             render_media_from_metadata(message["media"])

# # --- 2. XỬ LÝ INPUT NGƯỜI DÙNG ---
# if prompt := st.chat_input("Hỏi về ký hiệu (ví dụ: 'Ký hiệu cảm ơn', 'Số 5')..."):
#     # Hiển thị câu hỏi
#     st.chat_message("user", avatar="data:image/png;base64," + icon_user).markdown(prompt)
#     st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "data:image/png;base64," + icon_user})

#     # Xử lý trả lời
#     with st.chat_message("assistant", avatar="data:image/png;base64," + icon_assistant):
#         message_placeholder = st.empty()
#         message_placeholder.markdown("Đang tìm kiếm thông tin chính xác...")
        
#         try:
#             # Gửi request
#             response = requests.post(
#                 AGENT_SERVER_URL,
#                 json={"message": prompt, "thread_id": "session_v1"},
#                 timeout=60
#             )
            
#             if response.status_code == 200:
#                 data = response.json()
                
#                 ai_response_text = data.get("response", "")
#                 media_data = data.get("media", {}) 
#                 action_payload = data.get("action")

#                 # --- Xử lý Action Luyện tập ---
#                 if action_payload and action_payload.get("action") == "START_PRACTICE":
#                     sign_name = action_payload.get("sign")
#                     display_name = f"'{sign_name}'" if sign_name else "này"
#                     st.session_state.sign_to_practice = sign_name
                    
#                     link_md = (
#                         f"\n\n---\n**Thực hành ngay:** "
#                         f"[Mở Camera để luyện tập {display_name}](/{PRACTICE_PAGE_NAME})"
#                     )
#                     ai_response_text += link_md

#                 # --- Hiển thị ---
#                 message_placeholder.empty()
#                 st.markdown(ai_response_text)
                
#                 # Gọi hàm hiển thị media (Logic Strict Mapping từ backend đảm bảo media này là chuẩn)
#                 if media_data and (media_data.get("video") or media_data.get("image")):
#                     st.info("Tài liệu minh họa:")
#                     render_media_from_metadata(media_data)
                
#                 # --- Lưu State ---
#                 st.session_state.messages.append({
#                     "role": "assistant", 
#                     "content": ai_response_text,
#                     "avatar": "data:image/png;base64," + icon_assistant,
#                     "media": media_data # Lưu media để hiển thị lại khi reload
#                 })
                
#             else:
#                 err = f"Lỗi Server: {response.status_code}"
#                 message_placeholder.error(err)
#                 st.session_state.messages.append({"role": "assistant", "content": err, "avatar": "data:image/png;base64," + icon_assistant})

#         except Exception as e:
#             err = f"Không thể kết nối: {str(e)}"
#             message_placeholder.error(err)
#             st.session_state.messages.append({"role": "assistant", "content": err, "avatar": "data:image/png;base64," + icon_assistant})

# # --- SIDEBAR ---
# with st.sidebar:
#     quote = get_motivation()
#     st.sidebar.markdown(
#         f"""
#         <div style="
#             padding: 15px;
#             border-radius: 10px;
#             background-color: #f1f3ff;
#             border-left: 5px solid #4851ba;
#             font-size: 16px;
#             ">
#             <b>💡 Động lực hôm nay</b><br>
#             {quote}
#         </div>
#         <div style="height:20px;"></div>
#         """,
#         unsafe_allow_html=True
#     )
#     if st.button("Xóa hội thoại"):
#         st.session_state.messages = []
#         st.rerun()

import streamlit as st
import requests
import uuid
from configs.page_config import setup_page
from utils.image_util import load_image_base64
from utils.motivations import get_motivation

# --- CẤU HÌNH ---
AGENT_SERVER_URL = "http://127.0.0.1:8000/chat"
DELETE_THREAD_URL = "http://127.0.0.1:8000/delete_thread"
PRACTICE_PAGE_NAME = "Recognition"

# --- SETUP TRANG ---
setup_page()

# --- LOAD ASSETS ---
def safe_load_asset(path):
    try:
        return load_image_base64(path)
    except:
        return ""

# Load 3 assets quan trọng
logo_image = safe_load_asset("asset/logo.png")       # Avatar Bot
icon_user = safe_load_asset("asset/user.png")        # Avatar User
icon_new_chat = safe_load_asset("asset/NewChat.png") # Icon nút New Chat

# ==========================================
# 🎨 CSS TINH CHỈNH
# ==========================================
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}
    
    /* [FIX] KHOẢNG CÁCH GIỮA CÁC NÚT (QUAN TRỌNG) */
    /* Target vào wrapper bao ngoài của nút để triệt tiêu khoảng cách mặc định của Streamlit */
    section[data-testid="stSidebar"] .stButton {{
        padding-bottom: 0px !important;
        /* Dùng số âm để kéo các nút lại gần nhau. 
           -17px là khá sát, bạn có thể chỉnh thành -10px nếu muốn thưa hơn xíu */
        margin-bottom: -17px !important; 
    }}

    /* 1. NÚT 'CUỘC HỘI THOẠI MỚI' */
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {{
        width: 100%;
        background-color: #f0f4f9 !important;
        color: #1f1f1f !important;
        border: none !important;
        border-radius: 20px !important;
        padding: 10px 20px 10px 45px !important; 
        font-size: 14px !important;
        font-weight: 500 !important;
        box-shadow: none !important;
        text-align: left !important;
        display: flex !important;
        align-items: center !important;
        position: relative !important;
    }}
    
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover {{
        background-color: #e2e6ea !important;
        color: #000 !important;
    }}

    /* ICON PNG CHO NÚT NEW CHAT */
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"]::before {{
        content: "";
        position: absolute;
        left: 15px;
        top: 50%;
        transform: translateY(-50%);
        width: 27px;
        height: 27px;
        background-image: url("data:image/png;base64,{icon_new_chat}");
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
        opacity: 0.7;
    }}

    /* 2. DANH SÁCH LỊCH SỬ CHAT */
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"] {{
        width: 100%;
        border: none;
        background: transparent;
        color: #444746; 
        font-size: 14px;
        text-align: left !important;
        display: flex !important;
        justify-content: flex-start !important;
    
        /* Chỉnh độ dày của bản thân cái nút */
        padding-left: 10px !important;
        padding-top: 4px !important;
        padding-bottom: 4px !important;

        margin-top: 0px !important;
        border-radius: 8px;
        font-weight: 400;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        box-shadow: none !important;
    }}
    
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover {{
        background-color: #f0f4f9;
        color: #1f1f1f;
    }}

    /* 3. NÚT XÓA HỘI THOẠI */
    .delete-btn-wrapper div.stButton > button {{
        background-color: #f1f3f4 !important;
        color: #444746 !important;
        border: 1px solid #e0e0e0 !important;
        border-radius: 12px !important;
        width: 100%;
        padding: 8px 15px !important;
        font-size: 13px !important;
        display: flex !important;
        justify-content: center !important;
    }}
    
    .delete-btn-wrapper div.stButton > button:hover {{
        background-color: #e2e6ea !important;
        color: #000 !important;
    }}

    .sidebar-label {{
        font-size: 13px;
        font-weight: 600;
        color: #444746;
        margin-top: 20px;
        margin-bottom: 5px;
        padding-left: 10px;
    }}

    .fixed-header {{
        position: sticky;
        top: 0;
        background-color: rgba(255, 255, 255, 0.98);
        z-index: 999;
        display: flex;
        align-items: center;
        padding: 10px 0;
        border-bottom: 1px solid #f0f0f0;
        margin-bottom: 1rem;
    }}
    
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    
</style>
""", unsafe_allow_html=True)

# --- HEADER UI ---
st.markdown(f"""
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
""", unsafe_allow_html=True)

# ==========================================
# STATE LOGIC
# ==========================================
if "chat_sessions" not in st.session_state:
    new_id = str(uuid.uuid4())
    st.session_state.chat_sessions = {
        new_id: {"title": "Cuộc hội thoại mới", "messages": []}
    }
    st.session_state.active_session_id = new_id

if "sign_to_practice" not in st.session_state:
    st.session_state.sign_to_practice = None

# ==========================================
# SIDEBAR UI
# ==========================================
with st.sidebar:
    # 1. NÚT CHAT MỚI
    if st.button("Cuộc hội thoại mới", type="primary", use_container_width=True):
        new_id = str(uuid.uuid4())
        st.session_state.chat_sessions[new_id] = {"title": "Cuộc hội thoại mới", "messages": []}
        st.session_state.active_session_id = new_id
        st.rerun()

    st.markdown('<p class="sidebar-label">Gần đây</p>', unsafe_allow_html=True)

    # 2. DANH SÁCH LỊCH SỬ
    session_ids = list(st.session_state.chat_sessions.keys())[::-1]
    
    with st.container():
        for sess_id in session_ids:
            sess_data = st.session_state.chat_sessions[sess_id]
            title = sess_data["title"]
            display_title = title if len(title) < 35 else title[:32] + "..."
            
            if sess_id == st.session_state.active_session_id:
                label = display_title 
            else:
                label = display_title

            if st.button(label, key=f"sess_{sess_id}", type="secondary", use_container_width=True):
                st.session_state.active_session_id = sess_id
                st.rerun()

    # --- ĐƯỜNG GẠCH NGANG PHÂN CÁCH ---
    st.markdown("""
        <div style="margin-top: 20px;"></div>
        <hr style="border: 0; border-top: 1px solid #e0e0e0; margin-bottom: 20px;">
    """, unsafe_allow_html=True)
    
    # 3. NÚT XÓA
    st.markdown('<div class="delete-btn-wrapper">', unsafe_allow_html=True)
    if st.button("Xóa hội thoại này", use_container_width=True):
        current_id = st.session_state.active_session_id
        try: requests.delete(f"{DELETE_THREAD_URL}/{current_id}", timeout=1)
        except: pass
        
        if current_id in st.session_state.chat_sessions:
            del st.session_state.chat_sessions[current_id]
        
        remaining_ids = list(st.session_state.chat_sessions.keys())
        if not remaining_ids:
            new_new_id = str(uuid.uuid4())
            st.session_state.chat_sessions = {new_new_id: {"title": "Cuộc hội thoại mới", "messages": []}}
            st.session_state.active_session_id = new_new_id
        else:
            st.session_state.active_session_id = remaining_ids[0]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
        
    st.markdown(f"<div style='font-size:11px; color:#aaa; margin-top:10px; font-style:italic; text-align:center;'>{get_motivation()}</div>", unsafe_allow_html=True)

# ==========================================
# MAIN CHAT (XỬ LÝ AVATAR ĐÚNG CÁCH)
# ==========================================
active_id = st.session_state.active_session_id
if active_id not in st.session_state.chat_sessions:
    st.session_state.active_session_id = list(st.session_state.chat_sessions.keys())[0]
    st.rerun()

current_session = st.session_state.chat_sessions[active_id]
current_messages = current_session["messages"]

# --- HÀM HELPER HIỂN THỊ MEDIA ---
def render_media(media_data):
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



# [FIX] Vòng lặp hiển thị tin nhắn cũ
for msg in current_messages:
    avatar = None 
    # Xác định avatar dựa trên role
    if msg["role"] == "user":
        # Nếu có icon_user thì dùng, không thì để None
        avatar = f"data:image/png;base64,{icon_user}" if icon_user else None
    else:
        # Nếu có logo_image (bot) thì dùng
        avatar = f"data:image/png;base64,{logo_image}" if logo_image else None

    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg.get("media"): render_media(msg["media"])

# [FIX] Xử lý input mới
if prompt := st.chat_input("Nhập tin nhắn..."):
    if current_session["title"] == "Cuộc hội thoại mới":
        new_title = " ".join(prompt.split()[:5])
        if len(prompt) > 25: new_title += "..."
        st.session_state.chat_sessions[active_id]["title"] = new_title.capitalize()

    # Chuẩn bị avatar cho User ngay tại đây
    user_avatar_str = f"data:image/png;base64,{icon_user}" if icon_user else None

    # Hiển thị tin nhắn user với avatar tùy chỉnh
    st.chat_message("user", avatar=user_avatar_str).markdown(prompt)
    current_messages.append({"role": "user", "content": prompt})

    # Xử lý Bot trả lời
    bot_avatar_str = f"data:image/png;base64,{logo_image}" if logo_image else None
    
    with st.chat_message("assistant", avatar=bot_avatar_str):
        placeholder = st.empty()
        placeholder.markdown("Đang xử lý câu trả lời từ VSignChat...")
        try:
            resp = requests.post(AGENT_SERVER_URL, json={"message": prompt, "thread_id": active_id}, timeout=60)
            if resp.status_code == 200:
                d = resp.json()
                txt = d.get("response", "")
                med = d.get("media", {})
                act = d.get("action")
                
                if act and act.get("action") == "START_PRACTICE":
                    st.session_state.sign_to_practice = act.get("sign")
                    txt += f"\n\n👉 [Mở Camera Luyện tập](/{PRACTICE_PAGE_NAME})"
                
                placeholder.markdown(txt)
                if med and (med.get("video") or med.get("image")): 
                    render_media(med)
                
                current_messages.append({"role": "assistant", "content": txt, "media": med})
                if len(current_messages) == 2: st.rerun()
            else:
                placeholder.error(f"Lỗi server: {resp.status_code}")
        except Exception as e:
            placeholder.error(f"Lỗi kết nối: {e}")