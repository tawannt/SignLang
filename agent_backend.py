# agent_backend.py
import ast
import logging
import os
import sys
import asyncio
import json
import operator
from typing import TypedDict, Annotated, List, Any, Dict, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv


# --- BẮT ĐẦU THIẾT LẬP LOGGING ---
# Cấu hình format và level
# Dùng INFO cho hoạt động bình thường, DEBUG để xem chi tiết (như agent steps)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)

# Lấy logger instance cho file này
logger = logging.getLogger(__name__)
# --- KẾT THÚC THIẾT LẬP LOGGING ---

from langchain_core.messages import AnyMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.documents import Document
from langchain_core.tools import tool, BaseTool
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from langfuse.langchain import CallbackHandler


# --- IMPORT MCP ---
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from langchain_mcp_adapters.tools import load_mcp_tools

# --- IMPORT RAG ---
# try:
#     from rag import query_sign_language, query_learning_path
# except ImportError as e:
#     logger.critical("LỖI: Không thể import 'query_sign_language' và 'query_learning_path' từ rag.py. %s", e)
#     logger.critical("Hãy đảm bảo file rag.py tồn tại trong cùng thư mục.")
#     sys.exit(1) # Thoát nếu thành phần cốt lõi bị thiếu

try:
    from rag_service import initialize_rag_retriever, safe_get_url, rewrite_query, CHROMA_PATH
    from config import MODEL_NAME, OPTIMIZED_QUERY_PROMPT # Vẫn cần CONFIG_PATH và PROMPT
except ImportError as e:
    logger.critical("LỖI: Không thể import 'initialize_rag_retriever' và 'rewrite_query' từ rag_service.py.")
    logger.critical("Hãy đảm bảo file rag_service.py (được tạo ở bước 1) tồn tại trong cùng thư mục. %s", e)
    sys.exit(1)

# Biến toàn cục để lưu trữ Hybrid Rerank Retriever và LLM Rewriter
RAG_RETRIEVER = None
LLM_QUERY_REWRITER = None


# --- IMPORT CHO SERVER API ---
import uvicorn
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager, AsyncExitStack
from datetime import datetime, timezone

# Tải biến môi trường
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 1. ĐỊNH NGHĨA CÁC CÔNG CỤ RAG (LOCAL TOOLS)

@tool
def get_current_time_tool() -> str:
    """
    Dùng công cụ này để lấy thời gian thực tế.
    """
    logger.info("Đang gọi get_current_time_tool...")
    now = datetime.now().astimezone()
    
    # Lấy offset dạng chuỗi, ví dụ: "+07:00"
    tz_offset = now.strftime('%z')
    # Định dạng lại +0700 thành +07:00 cho chuẩn ISO 8601 mở rộng (nếu cần)
    if len(tz_offset) == 5:
        tz_offset = tz_offset[:3] + ":" + tz_offset[3:]

    result = {
        "iso_format": now.isoformat(),
        "timezone_offset": tz_offset, # Trường mới giúp LLM dễ ghép chuỗi
        "human_readable": now.strftime("%H:%M:%S, %A ngày %d/%m/%Y"),
        "timezone_name": now.tzname(),
        "note": f"Khi tạo lịch, hãy ghép chuỗi thời gian mong muốn với '{tz_offset}' ở cuối. Ví dụ: '2025-XX-XXT20:00:00{tz_offset}'"
    }
    
    return json.dumps(result, ensure_ascii=False)



@tool
def search_sign_language_knowledge(query: str) -> str:
    """
    Dùng công cụ này để tìm kiếm TẤT CẢ thông tin về Ngôn ngữ Ký hiệu Việt Nam (VSL).
    Luôn gọi tool này khi người dùng hỏi về kiến thức VSL, cách ký hiệu, hoặc lộ trình học.
    """
    if RAG_RETRIEVER is None or LLM_QUERY_REWRITER is None:
        return json.dumps({"text_content": "Lỗi: DB chưa sẵn sàng.", "media": None})

    # 1. Rewrite Query
    try:
        # prompt = OPTIMIZED_QUERY_PROMPT.format(query=query)
        # resp = LLM_QUERY_REWRITER.invoke([HumanMessage(content=prompt)])
        # optimized_query = resp.content.strip() or query
        optimized_query = rewrite_query(query, LLM_QUERY_REWRITER, OPTIMIZED_QUERY_PROMPT)
    except Exception as e:
        logger.error(f"Rewriter error: {e}")
        optimized_query = query

    logger.info(f"[RAG] Query gốc: {query} -> Tối ưu: {optimized_query}")

    # 2. Retrieve
    retrieved_docs = RAG_RETRIEVER.invoke(optimized_query)
    
    if not retrieved_docs:
        return json.dumps({
            "text_content": "Xin lỗi, tôi không tìm thấy thông tin nào trong dữ liệu.",
            "media": {"image": None, "video": None}
        }, ensure_ascii=False)

    # 3. XỬ LÝ STRICT MAPPING (QUAN TRỌNG)
    # Chỉ lấy Top 3 để LLM tham khảo
    top_docs = retrieved_docs[:3]
    combined_text = []
    
    # Media chính: Chỉ lấy từ kết quả RANK 1 (i==0) để đảm bảo đúng chunk
    primary_media = {"image": None, "video": None}

    for i, doc in enumerate(top_docs):
        img_url = safe_get_url(doc.metadata, "Image")
        vid_url = safe_get_url(doc.metadata, "Video")
        
        # Tạo marker để LLM biết chunk này có media hay không
        media_note = []
        if img_url: media_note.append("CÓ ẢNH")
        if vid_url: media_note.append("CÓ VIDEO")
        media_str = f"[{', '.join(media_note)}]" if media_note else ""

        # Gom text
        content_chunk = f"--- KẾT QUẢ {i+1} (Độ tin cậy cao thứ {i+1}) {media_str} ---\nNội dung: {doc.page_content}"
        combined_text.append(content_chunk)

        # Logic chọn Media hiển thị: CHỈ LẤY CỦA KẾT QUẢ ĐẦU TIÊN
        if i == 0:
            primary_media["image"] = img_url
            primary_media["video"] = vid_url

    # Output JSON
    tool_output = {
        "text_content": "\n\n".join(combined_text), 
        "media": primary_media 
    }
    logging.info(f"[RAG] Chunk tốt nhất trả về cho LLM: {tool_output['text_content'][:100]}...")
    logging.info(f"[RAG] Media trả về: {tool_output['media']}")

    return json.dumps(tool_output, ensure_ascii=False)

@tool
def start_practice_tool(sign_name: Optional[str] = None) -> str:
    """
    Dùng công cụ này KHI VÀ CHỈ KHI người dùng rõ ràng yêu cầu được
    'luyện tập', 'thực hành', 'dùng camera', 'thử ký hiệu', hoặc 'thử' (ví dụ: 'tôi muốn thử').
    Nó sẽ báo cho frontend bật camera.
    Nếu bạn biết họ muốn luyện tập ký hiệu gì (ví dụ: 'cảm ơn'),
    hãy truyền nó vào 'sign_name'.
    """
    logger.info("Yêu cầu bật camera cho: %s", sign_name)
    # Trả về một chuỗi JSON.
    return json.dumps({"action": "START_PRACTICE", "sign": sign_name})


# 2. KHỞI TẠO LLM VÀ STATE
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
    safety_settings=safety_settings,
)

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]

# 3. CẤU HÌNH MCP

# Cấu hình Notion
notion_mcp_params = StdioServerParameters(
    command="npx",
    args=["-y", "@notionhq/notion-mcp-server"],
    env={"NOTION_TOKEN": os.environ.get("NOTION_TOKEN")}
)

# Cấu hình Google
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GOOGLE_MCP_REPO_PATH = os.path.join(CURRENT_SCRIPT_DIR, "google-mcp")
TOKEN_PATH = os.path.join(CURRENT_SCRIPT_DIR, "token.json")

if not os.path.isdir(GOOGLE_MCP_REPO_PATH):
    logger.warning("Không tìm thấy thư mục Google MCP tại: %s", GOOGLE_MCP_REPO_PATH)
else:
    logger.info("Đang sử dụng thư mục Google MCP: %s", GOOGLE_MCP_REPO_PATH)
    logger.info("Đang sử dụng đường dẫn token: %s", TOKEN_PATH)

google_mcp_params = StdioServerParameters(
    command="bun",
    args=["run", "dev:stdio"],
    cwd=GOOGLE_MCP_REPO_PATH,
    env={
        "MCP_TRANSPORT": "stdio",
        "GOOGLE_OAUTH_CLIENT_ID": os.environ.get("GOOGLE_OAUTH_CLIENT_ID"),
        "GOOGLE_OAUTH_CLIENT_SECRET": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"),
        "GOOGLE_OAUTH_TOKEN_PATH": TOKEN_PATH
    }
)

# 4. ĐỊNH NGHĨA SCHEMA CHẶT CHẼ

class StrictPageCreateArgs(BaseModel):
    parent: Dict[str, str] = Field(
        ...,
        description="Đối tượng parent, ví dụ: {'page_id': 'ID_TRANG_CHA'}"
    )
    properties: Dict[str, Any] = Field(
        ...,
        description="Đối tượng properties, ví dụ: {'title': {'type': 'title', 'title': [{'text': {'content': 'Tiêu đề'}}]}} "
    )
    children: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Một MẢNG (list) các ĐỐI TƯỢNG (object) JSON. "
            "KHÔNG ĐƯỢC PHÉP là một chuỗi (string)."
            "Ví dụ: [{'object': 'block', 'type': 'paragraph', ...}]"
        )
    )

# 5. ĐỊNH NGHĨA CÁC NODE CỦA GRAPH

llm_with_tools = llm

def llm_call(state: AgentState):
    """Node này gọi LLM."""
    logger.info("[Node] Đang gọi LLM...")
    messages = state["messages"]

    # 1. Chỉ lấy ngày hôm nay làm bối cảnh chung (Không lấy giờ phút)
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")

    DYNAMIC_SYSTEM_PROMPT = (
        f"Bạn là trợ lý ảo thông minh đa năng. Hôm nay là ngày {today_str}.\n"
        "Bạn được trang bị hệ thống công cụ mạnh mẽ (MCP & RAG). Dưới đây là danh sách khả năng của bạn, hãy tự tin sử dụng chúng:\n\n"
        "1. **GIA SƯ NGÔN NGỮ KÝ HIỆU (Ưu tiên cao nhất)**:\n"
        "   - Khi người dùng hỏi về ký hiệu, từ vựng, hoặc cách học VSL: BẮT BUỘC dùng tool `search_sign_language_knowledge`.\n"
        "   - **Xử lý kết quả từ Tool**:\n"
        "     + Tool sẽ trả về văn bản có đánh dấu `[CÓ VIDEO]` hoặc `[CÓ ẢNH]` nếu dữ liệu có media minh họa.\n"
        "     + Nếu thấy các đánh dấu này, hãy nhắc người dùng: \"Mời bạn xem video/ảnh minh họa bên dưới để thực hiện chính xác hơn.\"\n"
        "     + Chỉ trả lời dựa trên thông tin trong `text_content`. Không suy diễn ngoài dữ liệu.\n"
        "   - **Luyện tập**: Nếu người dùng muốn 'thử', 'luyện tập' hoặc 'kiểm tra' ký hiệu, hãy dùng tool `start_practice_tool`.\n"
        "   - **QUAN TRỌNG**: TUYỆT ĐỐI KHÔNG tự viết link ảnh/video (ví dụ: image.jpg, youtube.com...) vào câu trả lời. Hệ thống sẽ tự hiển thị media chính xác cho người dùng.\n\n"
        "2. **QUẢN LÝ NOTION (Các tool bắt đầu bằng 'API-...')**:\n"
        "   - Bạn có thể Quản lý Knowledge Base trên Notion.\n"
        "   - Để tìm kiếm thông tin/ghi chú: Dùng `API-post-search`.\n"
        "   - Để tạo trang/ghi chú mới: Dùng `API-post-page`.\n"
        "   - Để đọc nội dung: Dùng `API-retrieve-a-block` hoặc `API-retrieve-a-page`.\n\n"

        "3. **QUẢN LÝ GOOGLE WORKSPACE (Các tool bắt đầu bằng 'google_...')**:\n"
        "   - **Calendar**: Xem lịch (`list_events`), Tạo lịch (`create_event`). *Lưu ý: Phải gọi `get_current_time_tool` trước để lấy giờ ISO.*\n"
        "   - **Drive**: Tìm tài liệu (`list_files`), Đọc file (`get_file_content`), Tạo file mới (`create_file`).\n"
        "   - **Gmail**: Kiểm tra mail (`list_emails`), Gửi mail (`send_email`), Tạo nháp (`draft_email`).\n"
        "   - **Tasks**: Tạo việc cần làm (`create_task`), Quản lý danh sách (`list_tasklists`).\n\n"

        "4. **QUY TẮC VẬN HÀNH**:\n"
        "   - **Thời gian**: Bạn không biết giờ hiện tại. Nếu user hỏi giờ hoặc cần tạo lịch, LUÔN gọi `get_current_time_tool` đầu tiên.\n"
        "   - **Ngôn ngữ**: Luôn trả lời thân thiện bằng tiếng Việt.\n"
        "   - **Lỗi**: Nếu gọi tool thất bại, hãy báo cáo chi tiết lỗi cho người dùng biết."
    )

    messages_with_prompt = [HumanMessage(content=DYNAMIC_SYSTEM_PROMPT)]

    for msg in messages:
        # Lọc bỏ system prompt cũ để tránh nhiễu
        if isinstance(msg, HumanMessage) and "Bạn là trợ lý ảo" in msg.content:
            continue
        messages_with_prompt.append(msg)

    response = llm_with_tools.invoke(messages_with_prompt)
    return {"messages": [response]}

def judge_node(state: AgentState):
    """
    Node này đóng vai trò 'Thẩm phán'.
    Nó kiểm tra câu trả lời cuối cùng của LLM trước khi gửi cho người dùng.
    """
    logger.info("[Node] Đang gọi Judge (Safety Check)...")
    messages = state["messages"]
    last_message = messages[-1]
    
    # Nếu tin nhắn cuối là Tool Call, không cần check (để nó chạy qua tool_node)
    # Chúng ta chỉ check khi LLM đưa ra câu trả lời văn bản cuối cùng.
    if last_message.tool_calls:
        return {"messages": []} # Không làm gì cả

    # Prompt cho Judge
    # Prompt cho Judge (Đã nới lỏng cho Personal Assistant)
    judge_prompt = (
        "Bạn là một kiểm duyệt viên AI cho một Trợ lý Cá nhân (Personal Assistant).\n"
        "Trợ lý này được tích hợp Notion, Google Drive, Calendar, Gmail của người dùng.\n"
        "Nhiệm vụ: Kiểm tra câu trả lời của AI xem có an toàn để hiển thị cho người dùng không.\n\n"
        
        f"Câu trả lời của AI: \"{last_message.content}\"\n\n"
        
        "Tiêu chí đánh giá:\n"
        "1. **AN TOÀN (SAFE)**: \n"
        "   - Các thông tin cá nhân của chính người dùng (Lịch trình, Nội dung Email, File Drive, Ghi chú Notion) ĐƯỢC PHÉP hiển thị.\n"
        "   - Các hướng dẫn về Ngôn ngữ Ký hiệu hoặc kiến thức học tập ĐƯỢC PHÉP hiển thị.\n"
        
        "2. **KHÔNG AN TOÀN (UNSAFE)**:\n"
        "   - Chứa mã độc, lời lẽ thù ghét, khiêu dâm, xúi giục bạo lực hoặc nguy hiểm.\n"
        "   - Tiết lộ **Mật khẩu (Passwords)**, **API Keys**, hoặc **Số thẻ tín dụng**.\n"
        "   - Tiết lộ thông tin nhạy cảm của **người thứ ba** (không phải người dùng) mà không có ngữ cảnh rõ ràng.\n\n"
        
        "Quyết định:\n"
        "- Nếu thuộc nhóm AN TOÀN: Trả lời duy nhất từ 'SAFE'.\n"
        "- Nếu thuộc nhóm KHÔNG AN TOÀN: Hãy viết lại câu trả lời thành một thông báo từ chối lịch sự và ngắn gọn bằng tiếng Việt."
    )

    # Gọi LLM (dùng chung model nhưng nhiệt độ thấp nhất)
    judge_response = llm.invoke([HumanMessage(content=judge_prompt)])
    decision = judge_response.content.strip()

    if decision == "SAFE":
        logger.info("-> Judge Verdict: SAFE")
        return {"messages": []} # Giữ nguyên tin nhắn cũ
    else:
        logger.warning(f"-> Judge Verdict: UNSAFE. Rewriting response. Content: {decision}")
        # Thay thế tin nhắn cuối cùng bằng tin nhắn đã được viết lại (an toàn)
        # Lưu ý: LangGraph add operator sẽ thêm vào list, nên ta cần cơ chế replace hoặc
        # đơn giản là thêm một tin nhắn mới đè lên nội dung cũ trong ngữ cảnh người dùng (tùy UI).
        # Ở đây ta trả về tin nhắn mới, nó sẽ được append vào history.
        return {"messages": [AIMessage(content=decision)]}

def should_continue(state: AgentState) -> str:
    """Cạnh điều kiện. Quyết định đi đâu tiếp theo."""
    last_message = state["messages"][-1]

    if last_message.tool_calls:
        logger.info("[Edge] LLM yêu cầu gọi công cụ (RAG hoặc MCP). Định tuyến đến tool_node.")
        return "tool_node"
    else:
        logger.info("[Edge] LLM không gọi công cụ. Chuyển sang Judge Node.")
        return "judge_node"

# 6. HÀM BUILD AGENT

def build_agent_graph(mcp_tools: List[BaseTool]):
    """
    Hàm này xây dựng và biên dịch agent graph.
    """
    global llm_with_tools

    rag_tools = [
        # signlang_retrieval_tool,
        # learningpath_retrieval_tool,
        search_sign_language_knowledge,
        get_current_time_tool,
        start_practice_tool 
    ]
    all_tools = mcp_tools + rag_tools

    if not all_tools:
        logger.warning("Không load được công cụ nào (MCP hoặc RAG). Agent sẽ bị hạn chế.")

    logger.info("\n--- TỔNG HỢP CÁC CÔNG CỤ ĐÃ LOAD (MCP + RAG) ---")
    for t in all_tools:
        logger.info(f"- {t.name}")
    logger.info("--------------------------------------------------\n")

    llm_with_tools = llm.bind_tools(all_tools)

    tool_node = ToolNode(all_tools)

    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("llm_call", llm_call)
    agent_builder.add_node("tool_node", tool_node)

    # --- [NEW] Thêm Node Judge ---
    agent_builder.add_node("judge_node", judge_node)

    agent_builder.add_edge(START, "llm_call")
    # agent_builder.add_conditional_edges(
    #     "llm_call",
    #     should_continue,
    #     {"tool_node": "tool_node", END: END}
    # )
    agent_builder.add_conditional_edges(
        "llm_call",
        should_continue,
        {
            "tool_node": "tool_node",
            "judge_node": "judge_node" # Nếu không gọi tool thì đi qua Judge
        }
    )
    agent_builder.add_edge("tool_node", "llm_call")

    agent_builder.add_edge("judge_node", END)

    # 1. Khởi tạo bộ nhớ (lưu trong RAM)
    memory = MemorySaver()

    # 2. Truyền checkpointer vào hàm compile
    agent = agent_builder.compile(checkpointer=memory)
    # agent = agent_builder.compile()
    logger.info(">>> Agent Hợp Nhất (MCP + RAG) đã được biên dịch và sẵn sàng <<<")
    return agent

# 7. KHỞI TẠO SERVER API

app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Quản lý vòng đời của app FastAPI.
    """
    logger.info("--- Khởi động Lifespan: Bắt đầu kết nối MCP... ---")

    global RAG_RETRIEVER, LLM_QUERY_REWRITER

    loaded_mcp_tools = []
    stack = AsyncExitStack()
    app_state["stack"] = stack

    # 1. Khởi tạo RAG (Chroma DB) (*** PHẦN ĐÃ SỬA ***)
    try:
        logger.info("Đang tải Chroma Vectorstore và xây dựng Hybrid Rerank Retriever...")
        
        # Gọi hàm khởi tạo chính từ rag_service.py
        RAG_RETRIEVER, LLM_QUERY_REWRITER = initialize_rag_retriever(OPTIMIZED_QUERY_PROMPT)
        
        logger.info(">>> Đã tải Chroma DB và Hybrid Rerank Retriever/LLM thành công. <<<")

    except FileNotFoundError:
        logger.critical(f"\n!!! LỖI: Không tìm thấy Chroma Vectorstore tại {CHROMA_PATH}. Vui lòng chạy data_ingestion.py trước. !!!\n")
        logger.warning("RAG tools sẽ không hoạt động.")
    except Exception as e:
        logger.critical("\n!!! LỖI NGHIÊM TRỌNG khi khởi động RAG: %s", e, exc_info=True)
        # RAG_RETRIEVER vẫn là None


    try:
        # 1. Khởi động Notion
        logger.info("Đang kết nối với Notion MCP Server...")
        (nr, nw) = await stack.enter_async_context(stdio_client(notion_mcp_params))
        notion_session = await stack.enter_async_context(ClientSession(nr, nw))
        await notion_session.initialize()
        notion_tools = await load_mcp_tools(notion_session)

        # --- [PATCH-SCHEMA] ---
        for tool in notion_tools:
            if tool.name == "API-post-page":
                logger.info("--- [PATCH-SCHEMA] Đang vá lại args_schema cho 'API-post-page' ---")
                tool.args_schema = StrictPageCreateArgs
                logger.info(f"Schema mới của tool đã được cập nhật.")
                break

        loaded_mcp_tools.extend(notion_tools)
        logger.info(f"--- Đã load {len(notion_tools)} công cụ từ Notion. ---")

        # 2. Khởi động Google
        logger.info("Đang kết nối với Google MCP Server...")
        (gr, gw) = await stack.enter_async_context(stdio_client(google_mcp_params))
        google_session = await stack.enter_async_context(ClientSession(gr, gw))
        await google_session.initialize()
        google_tools = await load_mcp_tools(google_session)
        loaded_mcp_tools.extend(google_tools)
        logger.info(f"--- Đã load {len(google_tools)} công cụ từ Google. ---")

    except Exception as e:
        logger.critical("\n!!! LỖI NGHIÊM TRỌNG khi khởi động MCP clients: %s", e, exc_info=True)
        logger.warning("Server có thể sẽ không hoạt động đúng. Khởi động chỉ với RAG tools (nếu có).")

    # 3. Build Agent
    agent = build_agent_graph(loaded_mcp_tools)
    app_state["agent"] = agent

    yield

    logger.info("--- Shutdown Lifespan: Đang đóng kết nối MCP... ---")
    await stack.aclose()
    logger.info("--- Đã đóng kết nối. Tạm biệt! ---")


# --- ĐỊNH NGHĨA API (*** ĐÃ SỬA LẠI `chat_endpoint` CHO ĐÚNG ***) ---

app = FastAPI(lifespan=lifespan)

class ChatMessage(BaseModel):
    role: str
    content: str
class ChatRequest(BaseModel):
    message: str  # Frontend gửi: {"message": "...", ...}
    thread_id: Optional[str] = "default_thread"
# Trong agent_backend.py

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=503, detail="Agent chưa được khởi tạo.")
    
    # 1. Khởi tạo handler
    # Langfuse sẽ tự động lấy Key từ os.environ (do load_dotenv() đã nạp)
    langfuse_handler = CallbackHandler()

    try:
        thread_id = request.thread_id or "default_thread"
        # config = {"configurable": {"thread_id": thread_id}}
        # --- XỬ LÝ USER INFO ---
        # user_data = request.user_info or {}
        # user_email = user_data.get("email", "anonymous_user")
        # user_name = user_data.get("name", "Bạn")

        # 2. [QUAN TRỌNG] Thêm callbacks và metadata chuẩn xác
        config = {
            "configurable": {"thread_id": thread_id},
            "callbacks": [langfuse_handler],
            "metadata": {
                # "langfuse_user_id": user_email,           # <--- SỬA: Dùng email thật để tracking
                "langfuse_user_id": "userv1",           # <--- SỬA: Dùng email thật để tracking
                "langfuse_session_id": thread_id
            }
        }
        
        # 3. Lấy độ dài lịch sử TRƯỚC khi chạy agent
        initial_state = await agent.aget_state(config)
        start_len = len(initial_state.values["messages"]) if initial_state.values else 0

        # 4. Chạy Agent
        async for _ in agent.astream(
            {"messages": [HumanMessage(content=request.message)]},
            config,
            stream_mode="values"
        ):
            pass

        # 5. Lấy trạng thái SAU khi chạy
        final_state = await agent.aget_state(config)
        if not final_state.values:
            raise HTTPException(status_code=500, detail="Lỗi trạng thái agent.")

        all_messages = final_state.values["messages"]
        final_response_message = all_messages[-1]

        # 6. CẮT LẤY CÁC TIN NHẮN MỚI (New Messages Only) [QUAN TRỌNG]
        # Chỉ tìm media trong những tin nhắn vừa được sinh ra ở lượt này
        new_messages = all_messages[start_len:]

        # 7. Trích xuất Media chỉ từ new_messages
        extracted_media = {"image": None, "video": None}
        
        # Duyệt ngược trong các tin nhắn MỚI
        for msg in reversed(new_messages):
            if isinstance(msg, ToolMessage) and msg.name == "search_sign_language_knowledge":
                try:
                    tool_data = json.loads(msg.content)
                    if isinstance(tool_data, dict) and "media" in tool_data:
                        extracted_media = tool_data["media"]
                    # Break ngay khi thấy tool search gần nhất trong lượt này
                    break 
                except Exception:
                    pass

        # 8. Trích xuất Action (cũng chỉ từ new_messages)
        action_payload = None
        for msg in reversed(new_messages):
            if isinstance(msg, ToolMessage) and msg.name == "start_practice_tool":
                try:
                    action_data = json.loads(msg.content)
                    if action_data.get("action") == "START_PRACTICE":
                        action_payload = action_data
                except Exception:
                    pass
                break

        # 9. Xử lý kết quả trả về
        response_content = "..."
        if isinstance(final_response_message, AIMessage):
             response_content = final_response_message.content
             # Clean artifact list string logic cũ (nếu cần)
             try:
                if isinstance(response_content, str) and response_content.strip().startswith("[") and response_content.strip().endswith("]"):
                    parsed = ast.literal_eval(response_content)
                    if isinstance(parsed, list) and len(parsed) > 0:
                         response_content = parsed[0]
             except: pass
        
        return {
            "response": response_content,
            "media": extracted_media, # Nếu lượt này không gọi tool, cái này sẽ là None -> Frontend sẽ không hiện gì.
            "action": action_payload
        }

    except Exception as e:
        logger.error("LỖI nghiêm trọng trong chat_endpoint: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)