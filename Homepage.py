import streamlit as st

st.set_page_config(
    page_title="Trang chủ - Ứng dụng Ngôn ngữ Ký hiệu",
    layout="wide"
)

st.title("Chào mừng đến với Ứng dụng Hỗ trợ Ngôn ngữ Ký hiệu!")
st.sidebar.success("Chọn một chức năng ở trên.")

st.markdown(
    """
    Ứng dụng này bao gồm 2 chức năng chính:

    - **Chat:**
      Hỏi đáp về lộ trình học, ý nghĩa các ký hiệu, 
      hoặc dùng các tiện ích (Notion, Google Calendar)
      thông qua agent AI.

    - **Luyện Tập:**
      Chứa các video minh hoa các ký hiệu.
    - **Nhận diện:**
      Sử dụng camera để thực hành và nhận diện 
      ký hiệu real-time.

    **Hãy chọn một chức năng từ thanh bên (sidebar) để bắt đầu!**
    """
)