# rag_service.py
import os
import pickle
from dotenv import load_dotenv

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.messages import HumanMessage
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_core.documents import Document
from langfuse import observe
from typing import Optional

from config import (CHROMA_PATH, DOCS_PATH, MODEL_NAME, 
                    EMBEDDING_MODEL_NAME, RERANK_MODEL_NAME, RERANK_MODEL, COMPRESSOR)
# --- CẤU HÌNH (Đã lấy từ config.py gốc) ---
load_dotenv()



# LLM để viết lại query
def get_llm(model="gemini-2.0-flash-lite", max_output_tokens=256):
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        max_output_tokens=max_output_tokens,
    )

# --- CHỨC NĂNG LOAD DB VÀ RETRIEVER ---

def load_docs(docs_path=DOCS_PATH):
    """Load tài liệu thô cho BM25."""
    try:
        with open(docs_path, "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return []

def load_vectorstore_chroma():
    """Tải database Chroma đã được tạo trước đó."""
    if not os.path.exists(CHROMA_PATH):
        raise FileNotFoundError(f"Vectorstore not found at {CHROMA_PATH}.")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME
    )

    db = Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embeddings,
        collection_name="sign_language_collection"
    )
    return db

def get_retriever(vector_store, documents):
    """Tạo Hybrid Retriever (Chroma + BM25)."""
    retriever_dense = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 5}
    )

    retriever_sparse = BM25Retriever.from_documents(documents)
    retriever_sparse.k = 5

    hybrid_retriever = EnsembleRetriever(
        retrievers=[retriever_dense, retriever_sparse],
        weights=[0.5, 0.5],
    )
    return retriever_dense, retriever_sparse, hybrid_retriever # Trả về cả 3 cho rõ ràng

def rerank_result(ensemble_retriever, compressor=COMPRESSOR):
    """Áp dụng Reranker lên kết quả truy xuất."""
    compression_retriever = ContextualCompressionRetriever(
        base_compressor=compressor,
        base_retriever=ensemble_retriever
    )
    return compression_retriever

@observe(as_type="generation") # Đánh dấu đây là một bước "Generation" trên Langfuse
def rewrite_query(query: str, llm, prompt_template: str):
    """
    Tối ưu hóa truy vấn người dùng bằng LLM.
    Có tích hợp Langfuse để theo dõi input/output.
    """
    # Nếu prompt chưa format, ta format tại đây
    prompt = prompt_template.format(query=query)
    
    # Gọi LLM
    resp = llm.invoke([HumanMessage(content=prompt)])
    
    return resp.content.strip()


# Hàm chính để khởi tạo và trả về Reranked Retriever
@observe()
def initialize_rag_retriever(prompt_template: str):
    """
    Load Chroma, Docs, xây dựng Hybrid Retriever, và áp dụng Reranker.
    Trả về Reranked Retriever và LLM để dùng cho Query Rewriting.
    """
    try:
        # Load Components
        try: 
            chroma_db = load_vectorstore_chroma()
            documents = load_docs()
        except Exception as e:
            raise Exception(f"LỖI khi tải dữ liệu hoặc vectorstore: {e}")

        # Build Retriever
        try:
            _, _, hybrid_retriever = get_retriever(chroma_db, documents)
        except Exception as e:
            raise Exception(f"LỖI khi xây dựng Retriever: {e}")
        
        # Apply Reranker
        try:
            final_retriever = rerank_result(hybrid_retriever, COMPRESSOR)
        except Exception as e:
            raise Exception(f"LỖI khi áp dụng Reranker: {e}")
        
        # LLM để viết lại query (tạo instance mới cho mỗi lần gọi)
        try :
            llm_query_rewriter = get_llm()
        except Exception as e:
            raise Exception(f"LỖI khi khởi tạo LLM cho Query Rewriting: {e}")

        
        return final_retriever, llm_query_rewriter
    
    except FileNotFoundError as e:
        raise FileNotFoundError(f"LỖI KHỞI TẠO RAG: {e}. Vui lòng kiểm tra đường dẫn và chạy data_ingestion.py.")
    except Exception as e:
        raise Exception(f"LỖI NGHIÊM TRỌNG khi khởi tạo RAG: {e}")



def safe_get_url(metadata: dict, key: str) -> Optional[str]:
    """Helper: Lấy URL an toàn từ metadata, xử lý cả trường hợp list và string."""
    val = metadata.get(key) or metadata.get(key.lower())
    if not val:
        return None
    
    # Trường hợp là List (do Chroma lưu)
    if isinstance(val, list):
        return val[0] if val and isinstance(val[0], str) and "http" in val[0] else None
    
    # Trường hợp là String
    if isinstance(val, str):
        if val.startswith("['") and val.endswith("']"): # Fix lỗi format cũ
            val = val[2:-2]
        return val if "http" in val else None
    return None