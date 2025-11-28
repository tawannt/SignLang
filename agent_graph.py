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
from config import MODEL_NAME, OPTIMIZED_QUERY_PROMPT, MODEL_NAME_2, OPENROUTER_MODEL_NAME, OPENROUTER_BASE_URL

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


#@tool
#def simple_add_text_to_page(page_id: str, text_content: str) -> str:
#    """
#    Dùng tool này để viết nội dung vào trang Notion.
#    Chỉ cần cung cấp ID trang và nội dung văn bản. Tool sẽ tự động định dạng.
#    KHÔNG dùng tool này để tìm kiếm.
#    """
#    if not notion_client:
#        return "Lỗi: Server chưa cấu hình NOTION_TOKEN."
#
#    try:
#        # Đây là nơi Code xử lý sự phức tạp thay cho LLM (Best Practice)
#        # Chúng ta đóng gói text vào cấu trúc 'blocks' chuẩn của Notion
#        blocks = [
#            {
#                "object": "block",
#                "type": "paragraph",
#                "paragraph": {
#                    "rich_text": [
#                        {
#                            "type": "text",
#                            "text": {
#                                "content": text_content
#                            }
#                        }
#                    ]
#                }
#            }
#        ]
#        
#        # Gọi API trực tiếp
#        response = notion_client.blocks.children.append(block_id=page_id, children=blocks)
#        return f"Đã thêm thành công nội dung vào trang {page_id}. (Block ID: {response['results'][0]['id']})"
    
#    except Exception as e:
#        logger.error(f"Lỗi Notion Write: {e}")
#        return f"Gặp lỗi khi ghi vào Notion: {str(e)}"


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

llm_classification = ChatGoogleGenerativeAI(
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

# ==========================================
# 4. ĐỊNH NGHĨA NODE & GRAPH
# ==========================================

llm_with_tools = llm

def classify_user_intent(state: AgentState):
    """Node phân loại ý định người dùng."""
    logger.info("[Node] Đang phân loại ý định người dùng...")
    messages = state["messages"]
    last_message = messages[-1]

    # --- SỬA LẠI PROMPT NÀY ---
    classification_prompt = (
        "Bạn là một chuyên gia phân loại ý định người dùng.\n"
        "Nhiệm vụ: Xác định xem tin nhắn người dùng có nên được Trợ lý ảo Ngôn ngữ ký hiệu xử lý hay không.\n\n"
        "Quy tắc phân loại:\n"
        "1. Trả lời 'YES' nếu:\n"
        "   - Yêu cầu liên quan đến Ngôn ngữ ký hiệu (học, tra cứu, luyện tập).\n"
        "   - **Là các câu chào hỏi, giao tiếp xã giao thông thường** (Ví dụ: 'chào bạn', 'bạn tên gì', 'giúp tôi').\n"
        "   - Lịch trình, bài học,... (các chức năng của Notion, Google Drive, Google Calendar,...).\n"
        "2. Trả lời 'NO' nếu:\n"
        "   - Yêu cầu về code, toán học phức tạp, chính trị, hoặc các chủ đề hoàn toàn không liên quan (Ví dụ: 'viết code python', 'giải phương trình').\n\n"
        f"Tin nhắn người dùng: {last_message.content}\n\n"
        "Phân loại (chỉ trả lời đúng 1 từ YES hoặc NO):"
    )

    response = llm_classification.invoke([HumanMessage(content=classification_prompt)])
    classification = response.content.strip().upper()

    if classification == "YES":
        intent = "SIGN_LANGUAGE_RELATED"
    else:
        intent = "NOT_RELATED"

    logger.info(f"[Node] Phân loại xong: {intent}")
    return {"intent": intent}

def llm_call(state: AgentState):
    """Node gọi LLM."""
    logger.info("[Node] Đang gọi LLM...")

    messages = state["messages"]
    summary = state.get("summary", "")

    valid_messages = []
    for m in messages:
        if isinstance(m, (HumanMessage, AIMessage, SystemMessage, ToolMessage)):
            valid_messages.append(m)
    
    # 2. Tạo System Prompt chứa Summary (Nếu có)
    summary_context = f"\n\n### TÓM TẮT KÝ ỨC DÀI HẠN:\n{summary}" if summary else ""
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")

    DYNAMIC_SYSTEM_PROMPT = (
        f"Bạn là trợ lý ảo thông minh đa năng. Hôm nay là ngày {today_str}.\n{summary_context}.\n"
        "Bạn được trang bị hệ thống công cụ mạnh mẽ (MCP & RAG). Dưới đây là danh sách khả năng của bạn:\n\n"
        "1. **GIA SƯ NGÔN NGỮ KÝ HIỆU (QUAN TRỌNG)**:\n"
        "   - Khi dùng tool `search_sign_language_knowledge`, bạn sẽ nhận được một danh sách JSON gồm 5 mục (ID: 1 đến 5).\n"
        "   - **Nhiệm vụ của bạn**:\n"
        "     1. Đọc kỹ nội dung của cả 5 mục.\n"
        "     2. Chọn ra **MỘT** mục có nội dung phù hợp nhất để trả lời user.\n"
        "     3. Trả lời user dựa trên nội dung mục đó.\n"
        "     4. **BẮT BUỘC**: Kết thúc câu trả lời bằng thẻ tham chiếu ID theo định dạng: `[[ID:x]]` (với x là số ID bạn chọn).\n"
        "   - Ví dụ: 'Ký hiệu Bác sĩ được thực hiện bằng cách nắm tay lại... [[ID:2]]'\n"
        "   - **Lưu ý**: Không tự bịa link ảnh/video. Chỉ cần đưa thẻ ID, hệ thống sẽ tự hiển thị ảnh/video.\n"
        "2. **QUẢN LÝ NOTION (Tư duy và Kiến thức công cụ)**:\n"
        "   - **Cơ chế định danh**: Notion API thao tác dựa trên `UUID` (ID), trong khi người dùng giao tiếp bằng `Tên trang`. Do đó, công cụ `API-post-search` đóng vai trò là 'cầu nối' quan trọng để chuyển đổi từ Tên sang ID khi cần thiết.\n"
        "   - **Phân biệt chức năng ĐỌC**:\n"
        "     + `API-retrieve-a-page`: Chỉ trả về thông tin meta (tiêu đề, người tạo, ngày tạo...), KHÔNG chứa nội dung bài viết.\n"
        "     + `API-get-block-children`: Đây mới là công cụ dùng để **đọc nội dung chi tiết** (văn bản, hình ảnh) bên trong một trang.\n"
        "   - **Phân biệt chức năng VIẾT**:\n"
        "     + `API-post-page`: Dùng để **tạo mới hoàn toàn** một trang (Create New).\n"
        "     + `API-patch-block-children`: Dùng để **viết thêm/chèn nội dung** vào cuối một trang đã tồn tại (Append/Update).\n"
        "   - **QUY TẮC JSON NGHIÊM NGẶT CHO `API-patch-block-children`**:\n"
        "     Tham số `children` PHẢI là một danh sách các block. Bạn KHÔNG được sáng tạo cấu trúc. Hãy copy y nguyên mẫu dưới đây và chỉ thay đổi phần nội dung:\n"
        "     - Để viết nội dung vào một trang, bạn PHẢI dùng tool `API-patch-block-children`.\n"
        "     Tool này yêu cầu tham số `children` là một danh sách JSON. Cấu trúc của Notion rất phức tạp, bạn KHÔNG ĐƯỢC tự sáng tạo.\n"
        "     **MẪU CHUẨN (Copy y nguyên và chỉ thay nội dung):**\n"
        "     Dưới đây là cấu trúc để viết đoạn văn bản: 'Nội dung của tôi'.\n"
        "     ```json\n"
        "     [\n"
        "       {\n"
        "         \"object\": \"block\",\n"
        "         \"type\": \"paragraph\",\n"
        "         \"paragraph\": {\n"
        "           \"rich_text\": [\n"
        "             {\n"
        "               \"type\": \"text\",\n"
        "               \"text\": {\n"
        "                 \"content\": \"Nội dung của tôi\"\n" 
        "               }\n"
        "             }\n"
        "           ]\n"
        "         }\n"
        "       }\n"
        "     ]\n"
        "     ```\n"
        "     **Lưu ý kỹ thuật**: \n"
        "     + Tuyệt đối không được bỏ bớt các lớp `rich_text` hay `paragraph`.\n"
        "     + Nếu nội dung có dấu ngoặc kép, hãy escape nó (ví dụ: \\\").\n"
        "     *Giải thích: Bạn phải bọc nội dung trong `text` -> `rich_text` -> `paragraph` -> `block`.*\n\n"
        "   - **HƯỚNG DẪN ĐẶC BIỆT CHO `API-post-search`**:\n"
        "     Model thường gặp lỗi khi tạo filter cho tool này. Hãy tuân thủ quy tắc:\n"
        "     1. CHỈ sử dụng tham số `query`.\n"
        "     2. KHÔNG BAO GIỜ thêm tham số `filter` hoặc `sort`.\n"
        "     3. Ví dụ gọi đúng: `{\"query\": \"Ký hiệu xin lỗi\"}`\n"
        "     4. Ví dụ SAI (Cấm dùng): `{\"query\": \"...\", \"filter\": {\"property\": ...}}`\n\n"
        "   - **Quy tắc ứng xử**: Hãy tự đánh giá ngữ cảnh. Nếu THIẾU ID, hãy TỰ TÌM. Nếu cần đọc nội dung, hãy chọn đúng công cụ đọc block."
        "   ĐỪNG hỏi lại người dùng những thứ bạn có thể tự tra cứu.\n\n"

        "3. **QUẢN LÝ GOOGLE WORKSPACE**:\n"
        "   - **Calendar (Tạo lịch)**: \n"
        "     + BƯỚC 1: Gọi `get_current_time_tool`(Để biết thời gian + múi giờ hiện tại)\n"
        "     + BƯỚC 2: Tự tính toán danh sách các ngày giờ cần tạo.\n"
        "     + BƯỚC 3: **BẮT BUỘC** phải gọi tool `google_calendar_create_event` cho TỪNG sự kiện.\n"
        "     + **CẢNH BÁO**: Tuyệt đối KHÔNG được trả lời là 'Đã tạo lịch' nếu bạn chưa thực sự gọi tool `google_calendar_create_event` và nhận được kết quả 'success' từ tool đó. Nếu chưa gọi tool, hãy gọi tool ngay."
        "     + **QUAN TRỌNG**: Trường `start_time` và `end_time` PHẢI có múi giờ. Ví dụ ĐÚNG: `2025-11-27T10:00:00+07:00`\n"
        "   - **Drive**: Dùng các tool tương ứng.\n\n"
        "4. **QUY TẮC AN TOÀN**: Bạn được phép xử lý dữ liệu cá nhân (Lịch, Email) của user. KHÔNG tiết lộ API Key/Pass."
    )

    # messages_with_prompt = [HumanMessage(content=DYNAMIC_SYSTEM_PROMPT)]
    # for msg in messages:
    #     if isinstance(msg, HumanMessage) and "Bạn là trợ lý ảo" in msg.content:
    #         continue
    #     messages_with_prompt.append(msg)
    # messages_with_prompt = [HumanMessage(content=DYNAMIC_SYSTEM_PROMPT)] + trimmed_history
    messages_with_prompt = [SystemMessage(content=DYNAMIC_SYSTEM_PROMPT)] + valid_messages

    response = llm_with_tools.invoke(messages_with_prompt)
    return {"messages": [response]}

def summarize_conversation(state: AgentState):
    """
    Node duy trì bộ nhớ: Nén tin nhắn cũ vào summary và xóa chúng khỏi DB.
    """
    logger.info("[Node] Đang kích hoạt Tóm tắt & Dọn dẹp...")
    
    # 1. Cấu hình
    messages = state["messages"]
    existing_summary = state.get("summary", "")
    
    # Chúng ta muốn giữ lại 6 tin nhắn mới nhất (3 cặp hỏi-đáp) để hội thoại tự nhiên
    # Các tin nhắn cũ hơn sẽ bị đem đi tóm tắt
    KEEP_LAST_N = 6 
    
    if len(messages) <= KEEP_LAST_N:
        # Nếu chưa đủ dài thì không làm gì cả (phòng hờ)
        return {"messages": []}

    # Tách danh sách: Cũ (cần tóm tắt) vs Mới (giữ lại)
    messages_to_summarize = messages[:-KEEP_LAST_N] 
    
    # 2. Tạo Prompt tóm tắt
    # Ghép summary cũ + nội dung tin nhắn cần nén
    prompt = (
        "Hãy đóng vai một chuyên gia lưu trữ thông tin. \n"
        f"Ký ức hiện tại: {existing_summary}\n\n"
        "Hãy cập nhật Ký ức trên bằng cách thêm vào các thông tin quan trọng từ đoạn hội thoại mới sau đây:\n"
    )
    
    # Format tin nhắn cũ thành dạng text để LLM đọc
    conversation_text = ""
    for msg in messages_to_summarize:
        role = "User" if isinstance(msg, HumanMessage) else "AI"
        conversation_text += f"{role}: {msg.content}\n"
        
    prompt += conversation_text
    prompt += "\nKý ức mới (ngắn gọn, súc tích, giữ lại tên riêng/thông tin chính):"

    # 3. Gọi LLM để sinh Summary mới
    # Nên dùng model nhẹ (Flash Lite) ở đây để tiết kiệm tiền/thời gian
    summary_message = llm.invoke([HumanMessage(content=prompt)])
    new_summary = summary_message.content
    
    # 4. XÓA TIN NHẮN CŨ KHỎI SQLITE
    # Tạo danh sách lệnh xóa tương ứng với các tin nhắn đã tóm tắt
    delete_messages = [RemoveMessage(id=m.id) for m in messages_to_summarize]
    
    logger.info(f"Đã nén {len(messages_to_summarize)} tin nhắn cũ thành Summary.")
    
    # Trả về: Summary mới VÀ Lệnh xóa tin nhắn cũ
    return {
        "summary": new_summary,
        "messages": delete_messages
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
    response = llm_classification.invoke([
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
        if len(state["messages"]) > 12:
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
