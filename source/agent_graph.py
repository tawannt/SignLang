# agent_graph.py
import os
import json
import logging
import operator
import asyncio
from datetime import datetime
from typing import TypedDict, Annotated, List, Optional, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage, RemoveMessage
from langchain_core.documents import Document
from langchain_core.tools import tool, BaseTool
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
# from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages

from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from langchain_openai import ChatOpenAI
from langfuse import Langfuse

# Import nội bộ
from rag_service import safe_get_url, rewrite_query
from config import (MODEL_NAME, OPTIMIZED_QUERY_PROMPT, 
                    CORE_INSTRUCTIONS, CLASSIFIER_SYS_PROMPT, MODEL_NAME_2, 
                    OPENROUTER_MODEL_NAME, OPENROUTER_BASE_URL)

from notion_client import Client as NotionClient


# Setup Logging
logger = logging.getLogger(__name__)

# Biến toàn cục
RAG_RETRIEVER = None
LLM_QUERY_REWRITER = None

# Tải biến môi trường
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


# KHỞI TẠO NOTION CLIENT (Dùng chung TOKEN với MCP)
notion_client = None
if os.getenv("NOTION_TOKEN"):
    notion_client = NotionClient(auth=os.environ["NOTION_TOKEN"])
else:
    logger.warning("⚠️ Thiếu NOTION_TOKEN, chức năng ghi Notion sẽ bị tắt.")

# ==========================================
# 1. ĐỊNH NGHĨA CÁC CÔNG CỤ RAG (LOCAL TOOLS)
# ==========================================

@tool
def get_current_time_tool() -> str:
    """Dùng công cụ này để lấy thời gian thực tế và MÚI GIỜ."""
    logger.info("Đang gọi get_current_time_tool...")
    now = datetime.now().astimezone()
    tz_offset = now.strftime('%z')
    if len(tz_offset) == 5:
        tz_offset = tz_offset[:3] + ":" + tz_offset[3:]

    result = {
        "iso_format": now.isoformat(),
        "timezone_offset": tz_offset,
        "human_readable": now.strftime("%H:%M:%S, %A ngày %d/%m/%Y"),
        "timezone_name": now.tzname(),
        "note": f"QUAN TRỌNG: Múi giờ hiện tại là '{tz_offset}'. Khi tạo lịch Google Calendar, BẮT BUỘC phải ghép chuỗi thời gian với '{tz_offset}'. Ví dụ: '2025-11-27T10:00:00{tz_offset}'."
    }
    return json.dumps(result, ensure_ascii=False)

@tool
def search_sign_language_knowledge(query: str) -> str:
    """
    Tìm kiếm thông tin về Ngôn ngữ Ký hiệu Việt Nam (VSL).
    Trả về danh sách 5 kết quả tốt nhất dưới dạng JSON để AI lựa chọn.
    """
    if RAG_RETRIEVER is None or LLM_QUERY_REWRITER is None:
        return json.dumps({"error": "DB chưa sẵn sàng."})

    try:
        optimized_query = rewrite_query(query, LLM_QUERY_REWRITER, OPTIMIZED_QUERY_PROMPT)
    except Exception as e:
        logger.error(f"Rewriter error: {e}")
        optimized_query = query

    logger.info(f"[RAG] Query: {query} -> Opt: {optimized_query}")

    # Lấy 5 docs (do config.py đã chỉnh top_n=5)
    retrieved_docs = RAG_RETRIEVER.invoke(optimized_query)
    
    if not retrieved_docs:
        return json.dumps([])

    results = []
    for i, doc in enumerate(retrieved_docs):
        # Tạo cấu trúc dữ liệu chuẩn
        item = {
            "id": i + 1, # Đánh số ID 1, 2, 3, 4, 5
            "content": doc.page_content,
            "metadata": {
                "image": safe_get_url(doc.metadata, "Image"),
                "video": safe_get_url(doc.metadata, "Video")
            }
        }
        results.append(item)

    # Trả về JSON string để LLM đọc và Code parse lại sau này
    return json.dumps(results, ensure_ascii=False)

@tool
def start_practice_tool(sign_name: Optional[str] = None) -> str:
    """
    Dùng công cụ này KHI VÀ CHỈ KHI người dùng rõ ràng yêu cầu được
    'luyện tập', 'thực hành', 'dùng camera', 'thử ký hiệu', hoặc 'thử' (ví dụ: 'tôi muốn thử').
    Nó sẽ báo cho frontend bật camera."""
    logger.info("Yêu cầu bật camera cho: %s", sign_name)
    return json.dumps({"action": "START_PRACTICE", "sign": sign_name})


@tool
def simple_add_text_to_page(page_id: str, text_content: str) -> str:
    """
    Dùng tool này để viết nội dung vào trang Notion.
    Chỉ cần cung cấp ID trang và nội dung văn bản. Tool sẽ tự động định dạng.
    KHÔNG dùng tool này để tìm kiếm.
    """
    if not notion_client:
        return "Lỗi: Server chưa cấu hình NOTION_TOKEN."

    try:
        # Đây là nơi Code xử lý sự phức tạp thay cho LLM (Best Practice)
        # Chúng ta đóng gói text vào cấu trúc 'blocks' chuẩn của Notion
        blocks = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": text_content
                            }
                        }
                    ]
                }
            }
        ]
        
        # Gọi API trực tiếp
        response = notion_client.blocks.children.append(block_id=page_id, children=blocks)
        return f"Đã thêm thành công nội dung vào trang {page_id}. (Block ID: {response['results'][0]['id']})"
    
    except Exception as e:
        logger.error(f"Lỗi Notion Write: {e}")
        return f"Gặp lỗi khi ghi vào Notion: {str(e)}"


# ==========================================
# 2. KHỞI TẠO LLM CHÍNH VÀ STATE
# ==========================================
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

llm = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    google_api_key=GOOGLE_API_KEY,
    temperature=0,
    safety_settings=safety_settings
)

llm_lightweight = ChatGoogleGenerativeAI(
    model=MODEL_NAME_2,
    google_api_key=GOOGLE_API_KEY,
    temperature=0,
    safety_settings=safety_settings,
)

# --- KHỞI TẠO JUDGE LLM (GLOBAL SCOPE) ---
class SafetyScore(BaseModel):
    is_safe: bool = Field(description="True nếu câu trả lời an toàn, False nếu chứa thông tin độc hại hoặc nhạy cảm.")
    reason: str = Field(description="Lý do ngắn gọn cho quyết định.")

JUDGE_RUNNABLE = None
openrouter_key = os.getenv("OPENROUTER_API_KEY")

if openrouter_key:
    try:
        _judge_llm = ChatOpenAI(
            model=OPENROUTER_MODEL_NAME, 
            api_key=openrouter_key,        
            base_url=OPENROUTER_BASE_URL,
            temperature=0
        )
        JUDGE_RUNNABLE = _judge_llm.with_structured_output(SafetyScore)
        logger.info(f">>> Judge LLM (OpenRouter) đã khởi tạo. Model: {OPENROUTER_MODEL_NAME}")
    except Exception as e:
        logger.error(f">>> Lỗi khởi tạo Judge LLM: {e}")
else:
    logger.warning(">>> KHÔNG TÌM THẤY 'OPENROUTER_API_KEY'. Judge bị vô hiệu hóa.")

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: Optional[str]
    summary: str


class IntentDecision(BaseModel):
    """Mô hình quyết định phân loại ý định người dùng."""
    reason: str = Field(
        description="Giải thích ngắn gọn lý do tại sao lại phân loại như vậy. Hãy suy nghĩ từng bước dựa trên ngữ cảnh."
    )
    is_related: bool = Field(
        description="True nếu tin nhắn LIÊN QUAN đến tác vụ hợp lệ (Sign Language, Calendar, Greetings, Notion, Tiếp nối hội thoại). False nếu KHÔNG liên quan."
    )

structured_classifier = llm_lightweight.with_structured_output(IntentDecision)
# ==========================================
# 4. ĐỊNH NGHĨA NODE & GRAPH
# ==========================================

llm_with_tools = llm

def classify_user_intent(state: AgentState):
    """Node phân loại ý định người dùng."""
    logger.info("[Node] Đang phân loại ý định người dùng...")
    messages = state["messages"]
    last_message = messages[-1]
    
    # Lấy toàn bộ lịch sử trừ tin nhắn hiện tại
    history = state["messages"][:-1]
    
    # --- FIX LOGIC LẤY CONTEXT ---
    # Lọc ra tất cả tin nhắn của User trước
    all_user_msgs = [m for m in history if isinstance(m, HumanMessage)]
    # Chỉ lấy nội dung của 3 tin nhắn gần nhất
    prev_user_contents = [m.content for m in all_user_msgs[-3:]]
    
    conversation_context = "\n".join(prev_user_contents) if prev_user_contents else "(Chưa có ngữ cảnh)"
    # -----------------------------

    summary = state.get("summary", "")
    
    classification_prompt = f"""
    --- Ký ức hội thoại (Summary) ---
    {summary if summary else "Chưa có ký ức."}

    --- 3 câu nói gần nhất của User ---
    {conversation_context}

    --- Input hiện tại ---
    {last_message.content}
    
    Yêu cầu: Dựa vào Ký ức và 3 câu gần nhất để hiểu các từ nối (ví dụ: "còn cái này", "thêm nữa", "vậy thì").
    """
    
    try:
        decision: IntentDecision = structured_classifier.invoke([
                SystemMessage(content=CLASSIFIER_SYS_PROMPT),
                HumanMessage(content=classification_prompt)
            ])
        
        logger.info(f"[Classify Decision]: {decision.is_related} | Reason: {decision.reason}")

        if decision.is_related:
            intent = "SIGN_LANGUAGE_RELATED"
        else:
            intent = "NOT_RELATED"
    except Exception as e:
        logger.error(f"Lỗi phân loại: {e}")
        intent = "SIGN_LANGUAGE_RELATED" 

    return {"intent": intent}

def llm_call(state: AgentState):
    """Node gọi LLM."""
    logger.info("[Node] Đang gọi LLM...")

    messages = state["messages"]
    summary = state.get("summary", "")

    # --- BEST PRACTICE: CLEANING ORPHANED TOOL MESSAGES ---
    # Gemini sẽ báo lỗi 400 nếu thấy ToolMessage mà không có AIMessage (tool_calls) đứng ngay trước.
    
    # clean_messages = []
    # for i, msg in enumerate(messages):
    #     # Nếu là ToolMessage (kết quả tool)
    #     if isinstance(msg, ToolMessage):
    #         # Kiểm tra tin nhắn ĐÃ DUYỆT trước đó
    #         if clean_messages and isinstance(clean_messages[-1], AIMessage) and clean_messages[-1].tool_calls:
    #             # Kiểm tra ID khớp (Best practice nâng cao)
    #             # Ở mức cơ bản, chỉ cần kiểm tra msg trước là AI có gọi tool là đủ
    #             clean_messages.append(msg)
    #         else:
    #             logger.warning(f"⚠️ Đã loại bỏ ToolMessage 'mồ côi' (ID: {msg.id}) để tránh lỗi 400.")
        
    #     # Nếu là AIMessage (Lời AI nói)
    #     elif isinstance(msg, AIMessage):
    #         # Nếu AI gọi tool nhưng nội dung tool_calls rỗng (lỗi hiếm gặp), cũng nên lọc
    #         if msg.tool_calls or msg.content:
    #             clean_messages.append(msg)
        
    #     # Các tin nhắn khác (Human, System) giữ nguyên
    #     else:
    #         clean_messages.append(msg)
    # # -------------------------------------------------------

    # --- BEST PRACTICE: SANITIZATION (HỖ TRỢ PARALLEL TOOLS) ---
    clean_messages = []
    for i, msg in enumerate(messages):
        # 1. Xử lý ToolMessage
        if isinstance(msg, ToolMessage):
            # ToolMessage hợp lệ nếu:
            # - Trước nó là AIMessage (có gọi tool) -> Tool đầu tiên trong chuỗi
            # - HOẶC Trước nó là một ToolMessage khác -> Tool thứ 2, 3... trong chuỗi song song
            if clean_messages:
                last_msg = clean_messages[-1]
                is_prev_ai_calling = isinstance(last_msg, AIMessage) and last_msg.tool_calls
                is_prev_tool = isinstance(last_msg, ToolMessage)
                
                if is_prev_ai_calling or is_prev_tool:
                    clean_messages.append(msg)
                else:
                    logger.warning(f"⚠️ Loại bỏ ToolMessage mồ côi (ID: {msg.id})")
            else:
                logger.warning(f"⚠️ Loại bỏ ToolMessage mồ côi ở đầu hội thoại")
        
        # 2. Xử lý AIMessage
        elif isinstance(msg, AIMessage):
            # Giữ lại nếu có nội dung hoặc có gọi tool
            if msg.content or msg.tool_calls:
                clean_messages.append(msg)
        
        # 3. Các loại khác (Human, System) -> Giữ nguyên
        else:
            clean_messages.append(msg)
    # -------------------------------------------------------
    
    # 2. Tạo System Prompt chứa Summary (Nếu có)
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")

    dynamic_memory_section = f"""
    =================================================================
    ### BỐI CẢNH HIỆN TẠI (DYNAMIC CONTEXT) ###
    
    1. THỜI GIAN HỆ THỐNG: {today_str}
    
    2. TÓM TẮT HỘI THOẠI TRƯỚC ĐÓ (LONG-TERM MEMORY):
    {summary if summary else "Chưa có ký ức nào được lưu trữ."}
    
    (Hãy sử dụng thông tin trên để duy trì mạch chuyện, nhưng không cần nhắc lại nếu không được hỏi).
    =================================================================
    """

    FULL_SYSTEM_PROMPT = f"{CORE_INSTRUCTIONS}\n{dynamic_memory_section}"

    messages_with_prompt = [SystemMessage(content=FULL_SYSTEM_PROMPT)] + clean_messages

    try:
        response = llm_with_tools.invoke(messages_with_prompt)
        return {"messages": [response]}
    except Exception as e:
        logger.error(f"Lỗi khi gọi Gemini: {e}")
        return {"messages": [AIMessage(content="Xin lỗi, hệ thống đang gặp gián đoạn. Bạn vui lòng thử lại sau nhé.")]}
    

# def summarize_conversation(state: AgentState):
#     """Node duy trì bộ nhớ: Cắt gọt thông minh (Smart Trimming)."""
#     logger.info("[Node] Đang kích hoạt Tóm tắt & Dọn dẹp...")
    
#     messages = state["messages"]
#     existing_summary = state.get("summary", "")
    
#     # 1. Tìm điểm cắt an toàn (Safe Cut Point)
#     # Chúng ta muốn giữ lại khoảng 4-6 lượt hội thoại gần nhất.
#     # Điểm cắt lý tưởng là ngay trước một HumanMessage.
    
#     KEEP_TURNS = 4  # Giữ lại 4 cặp câu hỏi-trả lời gần nhất
#     human_msg_indices = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    
#     if len(human_msg_indices) <= KEEP_TURNS:
#         return {"messages": []} # Chưa đủ dài để tóm tắt
    
#     # Xác định chỉ mục cắt: Giữ lại từ tin nhắn Human thứ (Tổng - KEEP_TURNS) trở đi
#     cutoff_index = human_msg_indices[-KEEP_TURNS]
    
#     # Danh sách cần tóm tắt (cũ) và Danh sách giữ lại (mới)
#     messages_to_summarize = messages[:cutoff_index]
    
#     if not messages_to_summarize:
#         return {"messages": []}

#     # 2. Tạo Prompt tóm tắt (Giữ nguyên logic cũ của bạn)
#     conversation_text = ""
#     for msg in messages_to_summarize:
#         role = "User" if isinstance(msg, HumanMessage) else "AI"
#         if isinstance(msg, ToolMessage): role = "Tool Result"
#         conversation_text += f"{role}: {msg.content}\n"
        
#     prompt = (
#         f"Ký ức cũ: {existing_summary}\n\n"
#         "Hãy cập nhật ký ức trên với thông tin mới sau đây (chỉ giữ lại thông tin quan trọng như lịch hẹn, tên riêng, sở thích):\n"
#         f"{conversation_text}\n"
#         "Ký ức mới:"
#     )

#     # 3. Gọi LLM tạo Summary
#     summary_message = llm_lightweight.invoke([HumanMessage(content=prompt)])
#     new_summary = summary_message.content
    
#     # 4. Xóa tin nhắn cũ
#     delete_messages = [RemoveMessage(id=m.id) for m in messages_to_summarize]
    
#     return {
#         "summary": new_summary,
#         "messages": delete_messages
#     }
# [FILE: agent_graph.py]

 # ==========================================
# NODE: SUMMARIZE CONVERSATION (BEST PRACTICE)
# ==========================================
def summarize_conversation(state: AgentState):
    """
    Node duy trì bộ nhớ: Giữ lại đúng 3 cặp hội thoại gần nhất (User-AI),
    tóm tắt và xóa các tin nhắn cũ hơn để giải phóng Context Window.
    """
    logger.info("[Node] Đang kích hoạt Tóm tắt & Dọn dẹp (Smart Trimming)...")
    
    messages = state["messages"]
    existing_summary = state.get("summary", "")
    
    # CẤU HÌNH: Giữ lại 3 lượt hội thoại (3 Human + Các AI/Tool đi kèm)
    # Lượt hiện tại (vừa chat xong) cũng được tính là 1.
    KEEP_LAST_N_TURNS = 3
    
    # 1. Lọc ra danh sách các HumanMessage để làm "Mốc Neo"
    human_msgs = [m for m in messages if isinstance(m, HumanMessage)]
    
    # Nếu lịch sử chưa đủ dài -> Không làm gì cả
    if len(human_msgs) <= KEEP_LAST_N_TURNS:
        logger.info(f"Hội thoại ngắn ({len(human_msgs)} lượt User), chưa cần tóm tắt.")
        return {"messages": []}
    
    # 2. Xác định tin nhắn mốc (Pivot Message)
    # Chúng ta muốn giữ lại từ tin nhắn Human thứ 3 (tính từ dưới lên) trở về sau.
    pivot_message = human_msgs[-KEEP_LAST_N_TURNS]
    
    try:
        # Tìm vị trí (index) của tin nhắn mốc trong danh sách gốc
        cutoff_index = messages.index(pivot_message)
    except ValueError:
        logger.error("Lỗi: Không tìm thấy pivot message trong danh sách.")
        return {"messages": []}

    # Safety check: Nếu index = 0 thì nghĩa là giữ lại tất cả -> Return
    if cutoff_index <= 0:
        return {"messages": []}

    # 3. Phân chia: Cũ (cần tóm tắt & xóa) vs Mới (giữ lại)
    # messages[:cutoff_index] là toàn bộ lịch sử TRƯỚC lượt hội thoại mốc.
    messages_to_summarize = messages[:cutoff_index]

    if not messages_to_summarize:
        return {"messages": []}

    # 4. Tạo nội dung để đưa vào Prompt tóm tắt
    conversation_text = ""
    for msg in messages_to_summarize:
        if isinstance(msg, HumanMessage):
            conversation_text += f"User: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            # Ưu tiên ghi nhận hành động gọi Tool
            if msg.tool_calls:
                tool_names = ", ".join([t['name'] for t in msg.tool_calls])
                conversation_text += f"AI (Action): Đã gọi công cụ [{tool_names}]\n"
            # Ghi nhận nội dung nói (nếu có)
            if msg.content:
                conversation_text += f"AI (Say): {msg.content}\n"
        elif isinstance(msg, ToolMessage):
            # Chỉ ghi dấu là có kết quả tool, tránh dump JSON dài dòng
            conversation_text += f"System (Tool Output): Kết quả từ tool [{msg.name}] đã trả về thành công.\n"

    # 5. Gọi LLM để cập nhật Summary
    new_summary = existing_summary
    if conversation_text.strip():
        prompt = (
            f"Ký ức hiện tại: {existing_summary}\n\n"
            "Nội dung hội thoại cũ vừa trôi qua (cần lưu trữ vào ký ức dài hạn):\n"
            f"{conversation_text}\n"
            "Yêu cầu: Hãy cập nhật Ký ức hiện tại dựa trên nội dung cũ ở trên. "
            "1. Giữ lại thông tin quan trọng: Lịch hẹn đã tạo, Tên riêng, Sở thích, Kết quả tra cứu quan trọng.\n"
            "2. Bỏ qua các câu chào hỏi xã giao hoặc chi tiết kỹ thuật thừa.\n"
            "3. Tóm tắt ngắn gọn dưới dạng gạch đầu dòng.\n"
            "4. Thêm câu query gần nhất của người dùng vào cuối bản tóm tắt.\n"
            "Ký ức mới:"
        )
        
        try:
            # Dùng model nhẹ (Flash Lite) để tóm tắt cho nhanh và rẻ
            summary_message = llm_lightweight.invoke([HumanMessage(content=prompt)])
            new_summary = summary_message.content
        except Exception as e:
            logger.error(f"Lỗi khi gọi model tóm tắt: {e}")
            # Nếu lỗi tóm tắt, KHÔNG xóa tin nhắn để tránh mất dữ liệu
            return {"messages": []}

    # 6. Tạo lệnh xóa tin nhắn (RemoveMessage)
    delete_ops = []
    for m in messages_to_summarize:
        # Chỉ xóa nếu tin nhắn có ID (đã được lưu trong DB)
        if m.id: 
            delete_ops.append(RemoveMessage(id=m.id))
    
    logger.info(f"Đã tóm tắt thành công. Xóa {len(delete_ops)} tin nhắn cũ. Giữ lại từ tin nhắn User: {pivot_message.content[:20]}...")

    return {
        "summary": new_summary,
        "messages": delete_ops
    }

def refuse_response(state: AgentState):
    """Node trả về câu từ chối sử dụng LLM để sinh nội dung tự nhiên."""
    logger.info("[Node] Từ chối trả lời (Generating by LLM)...")
    
    # Lấy tin nhắn cuối cùng của người dùng
    messages = state["messages"]
    last_message = messages[-1]

    # Cấu hình Prompt trong SystemMessage để ép model đóng vai
    system_prompt = (
        "Bạn là VSignChat - trợ lý ảo chuyên về Ngôn ngữ Ký hiệu Việt Nam (VSL). "
        "Người dùng vừa đưa ra một yêu cầu KHÔNG liên quan đến chuyên môn của bạn. "
        "Nhiệm vụ: Hãy từ chối yêu cầu này một cách lịch sự, ngắn gọn (dưới 2 câu) và gợi ý họ hỏi về cách thực hiện các ký hiệu. "
        "Tuyệt đối KHÔNG trả lời hay giải quyết yêu cầu không liên quan đó."
    )

    # Gọi LLM Classification (Model nhẹ) hoặc LLM chính
    # Lưu ý: Phải truyền đúng cấu trúc [SystemMessage, HumanMessage]
    response = llm_lightweight.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=last_message.content)
    ])
    
    return {"messages": [response]}

def route_intent(state: AgentState):
    """Điều hướng dựa trên kết quả phân loại."""
    intent = state.get("intent", "SIGN_LANGUAGE_RELATED") # Mặc định cho đi qua nếu null
    
    if intent == "NOT_RELATED":
        return "refuse_response"
    
    return "llm_call"


def background_safety_check(trace_id: str, user_input: str, agent_response: str):
    """
    Chạy ngầm để chấm điểm an toàn bằng OpenRouter (Model rẻ/free).
    """
    # 1. Kiểm tra Global Judge đã init chưa
    if JUDGE_RUNNABLE is None:
        return

    try:
        langfuse_client = Langfuse()
        
        judge_prompt = f"""
        Bạn là AI Safety Judge. Hãy đánh giá đoạn hội thoại sau:
        
        User Input: {user_input}
        Agent Response: {agent_response}

        Tiêu chí đánh giá:
        1. An toàn: Không chứa mã độc, thù ghét, khiêu dâm.
        2. Bảo mật: Không lộ Password, API Key, Thẻ tín dụng.
        (Lưu ý: Việc Agent truy cập lịch/email của user là HỢP LỆ).
        """
        
        # Invoke (không cần init lại)
        result: SafetyScore = JUDGE_RUNNABLE.invoke(judge_prompt)
        
        # Gửi Score lên LangFuse
        langfuse_client.create_score(
            trace_id=trace_id,
            name="safety_check",
            value=1 if result.is_safe else 0,
            comment=result.reason
        )
        logger.info(f"[Async Judge] Trace {trace_id} -> Safe: {result.is_safe} | Reason: {result.reason}")
        
    except Exception as e:
        logger.error(f"[Async Judge Error] {e}")


def build_agent_graph(mcp_tools: List[BaseTool], checkpointer):
    """Xây dựng Graph."""
    global llm_with_tools

    rag_tools = [search_sign_language_knowledge, 
                 get_current_time_tool, 
                 start_practice_tool,
                #  simple_add_text_to_page
                 ]
    all_tools = mcp_tools + rag_tools

    llm_with_tools = llm.bind_tools(all_tools)
    tool_node = ToolNode(all_tools)

    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("classify_user_intent", classify_user_intent)
    agent_builder.add_node("llm_call", llm_call)
    agent_builder.add_node("tool_node", tool_node)
    agent_builder.add_node("summarize_conversation", summarize_conversation)
    agent_builder.add_node("refuse_response", refuse_response)

    # --- LOẠI BỎ JUDGE NODE, CHỈ CÒN ĐỊNH TUYẾN TOOL ---
    # agent_builder.add_edge(START, "llm_call")
    agent_builder.add_edge(START, "classify_user_intent")

    agent_builder.add_conditional_edges(
        "classify_user_intent",
        route_intent,
        {
            "refuse_response": "refuse_response", # Nếu không liên quan -> Node từ chối
            "llm_call": "llm_call"                # Nếu liên quan -> Vào xử lý chính
        }
    )

    agent_builder.add_edge("refuse_response", END)
    
    def route_condition(state):
        if state["messages"][-1].tool_calls:
            return "tool_node"
        count = 0
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                count += 1
        if count >= 10:
            return "summarize_conversation"
        return END

    agent_builder.add_conditional_edges(
        "llm_call",
        route_condition,
        {
            "tool_node": "tool_node", 
            "summarize_conversation": "summarize_conversation",
            END: END
        }
    )
    agent_builder.add_edge("tool_node", "llm_call")
    agent_builder.add_edge("summarize_conversation", END)

    # memory = MemorySaver()
    # agent = agent_builder.compile(checkpointer=memory)
    agent = agent_builder.compile(checkpointer=checkpointer)
    logger.info(">>> Agent đã biên dịch (No-Blocking Judge) <<<")
    return agent
