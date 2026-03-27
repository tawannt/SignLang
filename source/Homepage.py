import streamlit as st
from utils.image_util import load_image_base64
from configs.page_config import setup_page
from utils.motivations import get_motivation

setup_page()

logo_image = load_image_base64("asset/logo.png")

st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Alice&display=swap" rel="stylesheet">
<style>
.fixed-header {{
    position: fixed;
    top: 25px;
    width: calc(100% - 30px);
    background-color: white;
    z-index: 9999;
    display: flex;
    align-items: center;
    padding: 5px 5px;
}}
</style>

<div class="fixed-header">
    <img src="data:image/png;base64,{logo_image}" width="100" style="margin-right:20px; margin-bottom:20px;" />
    <div>
        <h1 style="
            font-family: 'Alice', serif;
            font-size: 40px;
            background: linear-gradient(to right, #4851ba, #4aa9ea);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        ">VSignChat</h1>
        <h3 style="
            font-size: 20px;
            background: linear-gradient(to right, #4851ba, #4aa9ea);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        ">Ứng dụng học Ngôn ngữ ký hiệu</h3>
    </div>
</div>

<!-- Thêm khoảng trắng để nội dung không bị header che khuất -->
<div style="height:80px;"></div>
""", unsafe_allow_html=True)

col1, col2 = st.columns([6, 4])

with col1:
    st.image(
        "asset/chatbot_review.png"
    )
with col2:
    st.markdown(
        """
        ### Chatbot thông minh VSignChat
        Hỏi đáp về lộ trình học, ý nghĩa các ký hiệu, 
        hoặc dùng các tiện ích (Notion, Google Calendar)
        thông qua agent AI.
        """
    )

col1, col2 = st.columns([5, 5])

with col1:
    st.markdown(
        """
        ### Học và ôn tập ký hiệu
        Kho chứa các video minh họa các ký hiệu được chia rõ ràng theo bài học
        giúp bạn vừa học vừa ôn tập dễ dàng.
        """
    )
with col2:
    
    st.image(
        "asset/practice_review.png"
    )

col1, col2 = st.columns([5, 5])

with col1:
    st.image(
        "asset/realtime_review.png"
    )
with col2:
    st.markdown(
        """
        ### Nhận diện ký hiệu real-time
        Sử dụng camera để thực hành và nhận diện 
        ký hiệu real-time.
        """
    )

st.markdown(
    """
    **Hãy chọn một chức năng từ thanh bên (sidebar) để bắt đầu!**
    """
)

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