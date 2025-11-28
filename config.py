import os
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# CHROMA_PATH = os.path.join(os.path.dirname(BASE_DIR), "vectorstore", "chroma") 
# DOCS_PATH = os.path.join(os.path.dirname(BASE_DIR), "data", "docs.pkl")
CHROMA_PATH = os.path.join(BASE_DIR, "vectorstore", "chroma") 
DOCS_PATH = os.path.join(BASE_DIR, "data", "docs_chroma.pkl")
MODEL_NAME = "gemini-2.5-flash"
MODEL_NAME_2 = "gemini-2.5-flash-lite"

# --- MODEL PHỤ (OpenRouter - Rewrite Query & Judge) ---
# Dùng model free/cheap trên OpenRouter để tiết kiệm và nhanh
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") # Nhớ thêm vào .env
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# OPENROUTER_MODEL_NAME = "google/gemini-2.0-flash-exp:free"
OPENROUTER_MODEL_NAME = "meta-llama/llama-3.3-70b-instruct:free"


EMBEDDING_MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

RERANK_MODEL = HuggingFaceCrossEncoder(model_name=RERANK_MODEL_NAME)
COMPRESSOR = CrossEncoderReranker(model=RERANK_MODEL, top_n=5)

# Model choices
AVAILABLE_MODELS = [
    "gemini-2.5-flash-exp",
]
OPTIMIZED_QUERY_PROMPT = """
Bạn là Query Reformulator cho hệ thống RAG về Ngôn ngữ ký hiệu.

Bạn có 2 loại tài liệu:
1) SIGN_TERM: name, description, lesson, videos
2) LEARNING_PATH: lesson, objectives, activities

Nhiệm vụ của bạn:
- Phân tích truy vấn của người dùng và rút ra đúng 1 từ khóa chính là:
    • tên ký hiệu (nếu hỏi về ký hiệu)
    • hoặc tên bài học + từ khóa liên quan (nếu hỏi về bài học)
- Truy vấn tối ưu phải ngắn nhất có thể (1–4 từ).
- Không thêm thông tin mới.
- Không trả lời câu hỏi.
- Không được giải thích, không được mô tả quy tắc, không dùng dấu “:”.
- Nếu không thể tối ưu → trả về nguyên văn truy vấn gốc.
- **Chỉ trả về đúng một dòng duy nhất là truy vấn tối ưu**.

Ví dụ đúng:
cách làm dấu bác sĩ → bác sĩ
mục tiêu của bài 3 là gì → Bài 3 mục tiêu
Trong bài 1 học về chữ cái, làm sao tôi ký hiệu chữ Đ? → Chữ Đ
Tôi muốn tìm hiểu thêm về ngôn ngữ ký hiệu → Tôi muốn tìm hiểu thêm về ngôn ngữ ký hiệu

Truy vấn của người dùng:
{query}

Truy vấn tối ưu (chỉ 1 dòng):
"""