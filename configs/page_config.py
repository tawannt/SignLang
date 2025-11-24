import streamlit as st
from utils.image_util import load_image_base64

logo_image = load_image_base64("asset/logo.png")

def setup_page():
    st.set_page_config(
        page_title="VSignChat",
        layout="wide",
        page_icon="data:image/png;base64," + logo_image,
    )