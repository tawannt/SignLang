# app_sign_realtime.py
import streamlit as st
import cv2
import mediapipe as mp
import numpy as np
import torch
from sstcn_attention_model import SSTCN_Attention
from utils.sign_dict import SIGN_DICT_NO_ACCENT

# --- Config page ---
st.set_page_config(page_title="Sign Language Recognition", layout="wide")
st.title("Nhận diện ngôn ngữ ký hiệu (Real-time)")

# --- Load mô hình ---
NUM_CLASSES = 102
DEVICE = 'cpu'

@st.cache_resource
def load_model():
    model = SSTCN_Attention(num_classes=NUM_CLASSES).to(DEVICE)
    checkpoint = torch.load("sign_sstcn_attention_model.pth", map_location=DEVICE)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    return model

model = load_model()
sign_dict = SIGN_DICT_NO_ACCENT

# --- MediaPipe setup ---
mp_holistic = mp.solutions.holistic
holistic = mp_holistic.Holistic(min_detection_confidence=0.5,
                                min_tracking_confidence=0.5)

SEQ_LEN = 30
NUM_JOINTS = 75
threshold = 0.8

# --- Hàm trích xuất keypoints ---
def extract_keypoints(results):
    if results.pose_landmarks:
        pose = np.array([[lm.x, lm.y, lm.z] for lm in results.pose_landmarks.landmark])
    else:
        pose = np.zeros((33, 3))
    
    if results.left_hand_landmarks:
        left = np.array([[lm.x, lm.y, lm.z] for lm in results.left_hand_landmarks.landmark])
    else:
        left = np.zeros((21, 3))
    
    if results.right_hand_landmarks:
        right = np.array([[lm.x, lm.y, lm.z] for lm in results.right_hand_landmarks.landmark])
    else:
        right = np.zeros((21, 3))
    
    return np.concatenate([pose, left, right]).flatten()


# CSS để căn giữa FRAME_WINDOW và đặt nút Stop trong góc
st.markdown("""
    <style>
    .video-container {
        position: relative;
        display: flex;
        justify-content: center;
        align-items: center;
        height: 0vh;
    }
    </style>
""", unsafe_allow_html=True)
col1, col2, col3 = st.columns([3, 6, 1])
with col1:
    # Nút Start
    start_button = st.button("📷 Bắt đầu nhận diện")
    # Nút Stop
    stop_button = st.button("⛔ Dừng camera")
    # Các phần còn lại
    sequence_count_text = st.empty()
    pred_text = st.empty()

with col2:
    # Vùng chứa FRAME_WINDOW
    st.markdown('<div class="video-container">', unsafe_allow_html=True)

    FRAME_WINDOW = st.image([], channels="BGR", use_container_width=False)

    st.markdown('</div>', unsafe_allow_html=True)
if start_button:
    cap = cv2.VideoCapture(0)
    sequence = []
    pred = 102
    frame_skip = 2
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            st.warning("Không thể mở webcam!")
            break

        frame_count += 1
        if frame_count % frame_skip != 0:
            continue

        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = holistic.process(image)

        keypoints = extract_keypoints(results)
        sequence.append(keypoints)

        sequence_count_text.markdown(f"### Tiến trình: {len(sequence)}/{SEQ_LEN}")

        # --- Khi đủ 30 frames ---
        if len(sequence) == SEQ_LEN:
            seq = np.array(sequence).reshape(SEQ_LEN, NUM_JOINTS, 3)
            seq = seq.transpose(2, 0, 1)        # (3, 30, 75)
            seq = seq[np.newaxis, ...]          # (1, 3, 30, 75)
            seq = torch.tensor(seq, dtype=torch.float32).to(DEVICE)

            with torch.no_grad():
                out = model(seq)
                probs = torch.softmax(out, dim=1)
                max_prob, pred_idx = torch.max(probs, dim=1)
                if max_prob.item() >= threshold:
                    pred = pred_idx.item()
                else:
                    pred = 102
            sequence = []

        # --- Hiển thị kết quả ---
        FRAME_WINDOW.image(frame, channels="BGR")

        pred_text.markdown(f"### Dự đoán: **{sign_dict[pred]}**")

        # Nếu người dùng nhấn Dừng thì thoát
        if stop_button:
            break

    cap.release()
    st.success("📷 Camera đã tắt.")
