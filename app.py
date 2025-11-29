# main.py
import ast
import logging
import os
import asyncio
import json
import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from contextlib import asynccontextmanager, AsyncExitStack

# FastAPI Imports
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks

# LangChain / LangGraph Imports
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langfuse.langchain import CallbackHandler
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import aiosqlite

# Import từ file agent_graph
import agent_graph
from agent_graph import build_agent_graph, background_safety_check

# Import Rag Service để init global
from rag_service import initialize_rag_retriever
from config import OPTIMIZED_QUERY_PROMPT

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# ==========================================
# CẤU HÌNH MCP
# ==========================================
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


# Schema chặt chẽ cho Notion (để sửa lỗi model)
class StrictPageCreateArgs(BaseModel):
    parent: Dict[str, str] = Field(..., description="Parent object")
    properties: Dict[str, Any] = Field(..., description="Properties object")
    children: Optional[List[Dict[str, Any]]] = Field(default=None, description="Block children")

# ==========================================
# SERVER LIFESPAN & API
# ==========================================

app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- Khởi động Lifespan: Bắt đầu kết nối MCP song song... ---")
    global RAG_RETRIEVER, LLM_QUERY_REWRITER
    stack = AsyncExitStack()
    app_state["stack"] = stack

    # 1. Setup SQLite Checkpointer (Async)
    # Dùng context manager để tự động đóng kết nối khi tắt app
    # conn_string=":memory:" nếu muốn test, hoặc "path/to/db.sqlite" để lưu file
    db_path = "./memory/chat_history.db" 
    checkpointer = await stack.enter_async_context(
        AsyncSqliteSaver.from_conn_string(db_path)
    )

    # [Best Practice] Cấu hình SQLite để chạy nhanh hơn và ít bị lock (WAL Mode)
    # AsyncSqliteSaver.from_conn_string tự quản lý connection, nhưng ta có thể tối ưu sau
    # Hiện tại mặc định thư viện đã xử lý khá tốt.

    # 2. Load RAG
    try:
        RAG_RETRIEVER, LLM_QUERY_REWRITER = initialize_rag_retriever(OPTIMIZED_QUERY_PROMPT)
        agent_graph.RAG_RETRIEVER = RAG_RETRIEVER
        agent_graph.LLM_QUERY_REWRITER = LLM_QUERY_REWRITER
    except Exception as e:
        logger.warning(f"RAG Error: {e}")

    # 3. Load MCP Song Song
    loaded_mcp_tools = []
    
    async def load_notion():
        try:
            (nr, nw) = await stack.enter_async_context(stdio_client(notion_mcp_params))
            ns = await stack.enter_async_context(ClientSession(nr, nw))
            await ns.initialize()
            tools = await load_mcp_tools(ns)
            for t in tools:
                if t.name == "API-post-page": t.args_schema = StrictPageCreateArgs
            return tools
        except Exception as e:
            logger.error(f"Notion Fail: {e}")
            return []

    async def load_google():
        try:
            (gr, gw) = await stack.enter_async_context(stdio_client(google_mcp_params))
            gs = await stack.enter_async_context(ClientSession(gr, gw))
            await gs.initialize()
            # return await load_mcp_tools(gs)
            # 1. Load TẤT CẢ công cụ từ Google MCP
            all_google_tools = await load_mcp_tools(gs)
            
            # 2. Định nghĩa danh sách đen (Blacklist) các tool muốn bỏ
            ignored_prefixes = [
                "google_gmail",  # Bỏ Gmail
                "google_tasks"   # Bỏ Tasks
            ]
            
            # 3. Lọc: Chỉ giữ lại tool nào KHÔNG bắt đầu bằng các tiền tố trên
            filtered_tools = [
                t for t in all_google_tools 
                if not any(t.name.startswith(prefix) for prefix in ignored_prefixes)
            ]
            
            logger.info(f"Google MCP: Load {len(filtered_tools)}/{len(all_google_tools)} tools (Đã lọc Gmail & Tasks)")
            
            return filtered_tools
        except Exception as e:
            logger.error(f"Google Fail: {e}")
            return []

    results = await asyncio.gather(load_notion(), load_google())
    loaded_mcp_tools.extend(results[0])
    loaded_mcp_tools.extend(results[1])
    
    logger.info(f"--- Đã load tổng cộng {len(loaded_mcp_tools)} MCP tools ---")

    agent = build_agent_graph(loaded_mcp_tools, checkpointer)
    app_state["agent"] = agent
    yield
    await stack.aclose()


app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = "default_thread"


@app.post("/chat")
async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks):
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=503, detail="Agent chưa được khởi tạo.")
    
    # Init Handler
    langfuse_handler = CallbackHandler()
    thread_id = request.thread_id or "default_thread"

    try:
        config = {
            "configurable": {"thread_id": thread_id},
            "callbacks": [langfuse_handler],
            "metadata": {
                "langfuse_user_id": "userv1",
                "langfuse_session_id": thread_id
            }
        }
        

        # Chạy Agent
        async for _ in agent.astream(
            {"messages": [HumanMessage(content=request.message)]},
            config,
            stream_mode="values"
        ):
            pass

        # Lấy state cuối
        final_state = await agent.aget_state(config)
        all_messages = final_state.values["messages"]

        # ==================================================================================
        # 1. TRÍCH XUẤT DỮ LIỆU TỪ TOOL OUTPUT (FIXED LOGIC)
        # ==================================================================================
        # Thay vì dùng slicing dựa trên độ dài cũ (dễ lỗi nếu tin nhắn bị xóa),
        # ta luôn lấy tối đa 10 tin nhắn cuối cùng để quét tìm Tool Output vừa sinh ra.
        
        # [FIX] Tìm vị trí tin nhắn Human cuối cùng để xác định phạm vi lượt hiện tại
        last_human_index = -1
        for i in range(len(all_messages) - 1, -1, -1):
            if isinstance(all_messages[i], HumanMessage):
                last_human_index = i
                break
            
        # Chỉ quét các tin nhắn sinh ra SAU câu hỏi cuối cùng của user
        if last_human_index != -1:
            messages_to_scan = all_messages[last_human_index:]
        else:
            messages_to_scan = all_messages[-10:] # Fallback
        
        # ==================================================================================
        # 1. TRÍCH XUẤT DỮ LIỆU TỪ TOOL OUTPUT (RAG & PRACTICE)
        # ==================================================================================
        
        rag_tool_output = []      # List chứa 5 chunk kết quả từ RAG (JSON gốc)
        action_payload = None     # Action từ Practice Tool (nếu có)
        
        # Quét ngược tin nhắn để lấy output mới nhất của các tool
        for msg in reversed(messages_to_scan):
            if isinstance(msg, ToolMessage):
                # A. Lấy kết quả tìm kiếm (RAG)
                if msg.name == "search_sign_language_knowledge":
                    try:
                        rag_tool_output = json.loads(msg.content)
                    except Exception:
                        rag_tool_output = []
                
                # B. Lấy action luyện tập
                elif msg.name == "start_practice_tool":
                    try:
                        data = json.loads(msg.content)
                        if data.get("action") == "START_PRACTICE":
                            action_payload = data
                    except Exception:
                        pass

        # ==================================================================================
        # 2. XỬ LÝ TEXT & LÀM SẠCH ARTIFACTS CỦA GEMINI
        # ==================================================================================

        # last_msg = all_messages[-1]
        # response_content = last_msg.content if isinstance(last_msg, AIMessage) else ""
        response_content = ""
        for msg in reversed(all_messages):
            # Chỉ tìm AIMessage và bỏ qua các tin nhắn rỗng (chỉ gọi tool)
            if isinstance(msg, AIMessage) and msg.content:
                raw_content = msg.content
                
                # Xử lý nếu content là List[dict] (do Gemini/LangChain đôi khi trả về)
                if isinstance(raw_content, list):
                    text_parts = []
                    for item in raw_content:
                        if isinstance(item, dict) and "text" in item:
                            text_parts.append(item["text"])
                        elif isinstance(item, str):
                            text_parts.append(item)
                    if text_parts:
                        response_content = "\n".join(text_parts)
                
                # Xử lý nếu content là String (hoặc string dạng list do artifact)
                elif isinstance(raw_content, str):
                    # Thử parse nếu chuỗi bắt đầu bằng '[' (trường hợp Gemini trả string dạng list)
                    if raw_content.strip().startswith("["):
                        try:
                            parsed = ast.literal_eval(raw_content)
                            if isinstance(parsed, list):
                                text_parts = []
                                for item in parsed:
                                    if isinstance(item, dict) and "text" in item:
                                        text_parts.append(item["text"])
                                    elif isinstance(item, str):
                                        text_parts.append(item)
                                if text_parts:
                                    response_content = "\n".join(text_parts)
                                else:
                                    response_content = raw_content
                            else:
                                response_content = raw_content
                        except Exception:
                            response_content = raw_content # Parse lỗi thì giữ nguyên
                    else:
                        response_content = raw_content
                
                # Nếu đã tìm thấy nội dung, dừng vòng lặp ngay
                if response_content.strip():
                    break
        

        # # Logic làm sạch: Gemini đôi khi trả về List[dict] hoặc String dạng List
        # if isinstance(response_content, list):
        #     text_parts = []
        #     for item in response_content:
        #         if isinstance(item, dict) and "text" in item:
        #             text_parts.append(item["text"])
        #         elif isinstance(item, str):
        #             text_parts.append(item)
        #     if text_parts:
        #         response_content = "\n".join(text_parts)

        # elif isinstance(response_content, str) and response_content.strip().startswith("["):
        #     try:
        #         parsed = ast.literal_eval(response_content)
        #         if isinstance(parsed, list):
        #             text_parts = []
        #             for item in parsed:
        #                 if isinstance(item, dict) and "text" in item:
        #                     text_parts.append(item["text"])
        #                 elif isinstance(item, str):
        #                     text_parts.append(item)
        #             if text_parts:
        #                 response_content = "\n".join(text_parts)
        #     except Exception:
        #         pass # Parse lỗi thì giữ nguyên string gốc

        # ==================================================================================
        # 3. [CORE LOGIC] REFERENCE ID PATTERN (XỬ LÝ METADATA)
        # ==================================================================================
        
        extracted_media = {"image": None, "video": None}
        selected_id = None
        
        # Bước A: Tìm thẻ [[ID:x]] do LLM sinh ra
        # Regex tìm chuỗi [[ID:số]]
        match = re.search(r"\[\[ID:(\d+)\]\]", str(response_content))
        
        if match:
            selected_id = int(match.group(1))
            # Xóa thẻ ID khỏi câu trả lời để user không thấy (Làm sạch UI)
            response_content = str(response_content).replace(match.group(0), "").strip()

        # Bước B: Đối chiếu ID với Tool Output để lấy Metadata chính xác
        if selected_id is not None and rag_tool_output and isinstance(rag_tool_output, list):
            for item in rag_tool_output:
                # Tìm item có id trùng khớp
                if isinstance(item, dict) and item.get("id") == selected_id:
                    media_data = item.get("metadata", {})
                    extracted_media["image"] = media_data.get("image")
                    extracted_media["video"] = media_data.get("video")
                    logger.info(f"[Reference Pattern] LLM chọn ID {selected_id}. Media retrieved.")
                    break
        
        # Bước C: Fallback (Dự phòng)
        # Nếu LLM quên gắn thẻ ID hoặc ID không tồn tại, lấy kết quả đầu tiên (Top 1 Rerank)
        if (extracted_media["image"] is None and extracted_media["video"] is None) and rag_tool_output:
            if isinstance(rag_tool_output, list) and len(rag_tool_output) > 0:
                first_item = rag_tool_output[0]
                if isinstance(first_item, dict):
                    media_data = first_item.get("metadata", {})
                    extracted_media["image"] = media_data.get("image")
                    extracted_media["video"] = media_data.get("video")
                    logger.info("[Reference Pattern] Fallback to Top 1 Rerank result.")

        # ==================================================================================
        # 4. SAFETY CHECK BACKGROUND TASK
        # ==================================================================================
        
        current_trace_id = None
        if hasattr(langfuse_handler, "trace") and langfuse_handler.trace:
            current_trace_id = langfuse_handler.trace.id
        elif hasattr(langfuse_handler, "get_trace_id"):
            current_trace_id = langfuse_handler.get_trace_id()
        elif hasattr(langfuse_handler, "last_trace_id"):
             current_trace_id = langfuse_handler.last_trace_id

        if current_trace_id and response_content:
            background_tasks.add_task(
                background_safety_check,
                trace_id=current_trace_id,
                user_input=request.message,
                agent_response=str(response_content)
            )

        # ==================================================================================
        # 5. TRẢ VỀ KẾT QUẢ
        # ==================================================================================
        return {
            "response": response_content,
            "media": extracted_media,
            "action": action_payload
        }

    except Exception as e:
        logger.error("LỖI chat_endpoint: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"System Error: {str(e)}")
    
@app.delete("/delete_thread/{thread_id}")
async def delete_thread_endpoint(thread_id: str):
    """
    API để xóa hoàn toàn lịch sử chat của một thread khỏi SQLite.
    """
    db_path = "./memory/chat_history.db" # Đảm bảo đường dẫn đúng với cấu hình checkpointer của bạn
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # LangGraph lưu dữ liệu trong bảng 'checkpoints' và 'checkpoint_writes'
            # Cần xóa cả 2 bảng dựa trên thread_id
            await db.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            await db.execute("DELETE FROM checkpoint_writes WHERE thread_id = ?", (thread_id,))
            await db.commit()
            
        logger.info(f"Đã xóa thread_id: {thread_id} khỏi Database.")
        return {"status": "success", "message": f"Thread {thread_id} deleted"}
        
    except Exception as e:
        logger.error(f"Lỗi khi xóa thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)