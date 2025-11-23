import streamlit as st
import json
from typing import List, Dict

SIGN_TERMS_PATH = "./data/sign_terms_updated_video.json"
LEARNING_PATH_PATH = "./data/learning_path.json"
LEARNING_SCHEDULE_PATH = "./data/learning_schedule.json"

# --- CẤU HÌNH TRANG ---
def setup_page():
    st.set_page_config(
        page_title="Sign Language Dictionary",
        layout="wide",
    )

def load_file_json(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)    

setup_page()

# --- LOAD DATA ---
def load_learning_data():
    # Giả định các hàm này lấy từ utils/config vẫn hoạt động bình thường
    learning_schedule = load_file_json(LEARNING_SCHEDULE_PATH)
    # learning_path = load_file_json(LEARNING_PATH_PATH) # Không cần dùng nữa
    sign_terms = load_file_json(SIGN_TERMS_PATH)
    return learning_schedule, sign_terms

# --- KHỞI TẠO STATE ---
def initialize_app():
    # Chỉ cần lưu bài hiện tại và thẻ hiện tại
    if 'current_day' not in st.session_state:
        st.session_state.current_day = 0
    if 'current_card_index' not in st.session_state:
        st.session_state.current_card_index = 0

# --- GIAO DIỆN HIỂN THỊ THẺ TỪ (VIEWER) ---
def render_card_viewer(current_lesson, sign_terms):
    signs = current_lesson.get('Signs', [])
    
    if not signs:
        st.warning("Bài học này chưa có dữ liệu ký hiệu.")
        return

    total_cards = len(signs)
    
    # Đảm bảo index hợp lệ
    if st.session_state.current_card_index >= total_cards:
        st.session_state.current_card_index = 0
    if st.session_state.current_card_index < 0:
        st.session_state.current_card_index = 0
        
    current_index = st.session_state.current_card_index
    current_sign = signs[current_index]
    
    # Tìm thông tin chi tiết của từ (video, mô tả)
    sign_data = next((item for item in sign_terms if item.get("term") == current_sign), None)

    # --- HEADER VÀ MÔ TẢ ---
    col_header, col_desc = st.columns([1, 2])
    
    with col_header:
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 15px; border-radius: 12px; text-align: center; color: white;'>            
            <div style='font-size: 1.5rem; font-weight: bold;'>{current_sign}</div>
            <div style='margin-top: 5px; opacity: 0.9;'>Thẻ {current_index + 1} / {total_cards}</div>
        </div>
        """, unsafe_allow_html=True)

    with col_desc:
        description = sign_data.get("description", "Chưa có mô tả.") if sign_data else "..."
        st.markdown(f"""
        <div style='background: rgba(255,255,255,0.05); padding: 15px; 
                    border-radius: 12px; border: 1px solid #e0e0e0; height: 100%; display: flex; align-items: center;'>
            <div style='font-size: 1rem; color: #333;'>{description}</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("") # Spacer

    # --- VIDEO PLAYER ---
    if sign_data and sign_data.get('videos'):
        video_url = sign_data['videos']
        # Key unique để force reload video khi đổi từ
        video_key = f"vid_{st.session_state.current_day}_{current_index}_{current_sign}"

        video_html = f"""
            <div style="display: flex; justify-content: center; margin: 10px 0;">
                <video controls autoplay loop muted playsinline key="{video_key}"
                       style="width: 100%; max-width: 800px; border-radius: 16px;
                              box-shadow: 0 4px 20px rgba(0,0,0,0.15);">
                    <source src="{video_url}" type="video/mp4">
                </video>
            </div>
            """
        st.markdown(video_html, unsafe_allow_html=True)
    else:
        st.info("Không tìm thấy video cho ký hiệu này.")

    st.write("---")

    # --- CÁC NÚT ĐIỀU HƯỚNG ---
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c1:
        if st.button("Trước", use_container_width=True, disabled=(current_index == 0)):
            st.session_state.current_card_index -= 1
            st.rerun()

    with c2:
        # Danh sách chọn nhanh (Dropdown)
        selected_sign_nav = st.selectbox(
            "Chọn nhanh ký hiệu trong bài:", 
            options=signs, 
            index=current_index,
            label_visibility="collapsed"
        )
        # Nếu người dùng chọn từ dropdown, cập nhật index
        if selected_sign_nav != current_sign:
            st.session_state.current_card_index = signs.index(selected_sign_nav)
            st.rerun()

    with c3:
        if st.button("Sau", use_container_width=True, disabled=(current_index == total_cards - 1)):
            st.session_state.current_card_index += 1
            st.rerun()

# --- HÀM MAIN ---
def __main__():
    initialize_app()
    
    # CSS Tùy chỉnh nhẹ
    st.markdown("""
    <style>
        .block-container { padding-top: 2rem; }
        div.stButton > button { border-radius: 8px; height: 3em; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

    learning_schedule, sign_terms = load_learning_data()

    if not learning_schedule:
        st.error("Không có dữ liệu bài học.")
        return

    # --- THANH CHỌN BÀI HỌC (SIDEBAR HOẶC TOP) ---
    # Để ở Sidebar cho gọn
    with st.sidebar:
        st.header("Danh sách bài học")
        lesson_options = [f"Ngày {day['Day']}: {day['Lesson']}" for day in learning_schedule]
        
        selected_lesson_str = st.selectbox(
            "Chọn ngày học:",
            lesson_options,
            index=st.session_state.current_day
        )
        
        # Xử lý khi đổi bài học
        new_day_index = lesson_options.index(selected_lesson_str)
        if new_day_index != st.session_state.current_day:
            st.session_state.current_day = new_day_index
            st.session_state.current_card_index = 0 # Reset về từ đầu tiên
            st.rerun()

        # Hiển thị mục tiêu bài học (Chỉ xem)
        current_lesson_data = learning_schedule[st.session_state.current_day]
        goal_vn = "Học từ mới" if current_lesson_data.get('Goal') == "Study new signs" else "Ôn tập"
        st.info(f"**Mục tiêu:** {goal_vn}")

    # --- RENDER MAIN CONTENT ---
    current_lesson_data = learning_schedule[st.session_state.current_day]
    
    st.title(f"📖 {current_lesson_data['Lesson']}")
    
    render_card_viewer(current_lesson_data, sign_terms)

if __name__ == "__main__":
    __main__()