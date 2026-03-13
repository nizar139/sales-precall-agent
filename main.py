import asyncio
import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from client import MCPClient



# Single shared client instance (MCP connection is persistent)
mcp_client = MCPClient()


async def verify_token(x_api_key: str = Header(...)):
    if x_api_key != os.environ["INTERNAL_API_KEY"]:
        raise HTTPException(status_code=403)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mcp_client.connect()
    yield
    await mcp_client.cleanup()


app = FastAPI(title="Sales Pre-Call Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResearchRequest(BaseModel):
    prompt: str  # full natural language prompt from the rep
 
 
class ChatRequest(BaseModel):
    message: str
 
 
@app.get("/health")
async def health():
    return {"status": "ok", "connected": mcp_client.session is not None}
 
 
# @app.post("/research")
# async def research(req: ResearchRequest):
#     if not req.prompt.strip():
#         raise HTTPException(status_code=400, detail="Prompt is required")
#     try:
#         brief = await mcp_client.research(req.prompt.strip())
#         return {"brief": brief}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
 
 
# @app.post("/chat")
# async def chat(req: ChatRequest):
#     if not req.message.strip():
#         raise HTTPException(status_code=400, detail="Message is required")
#     try:
#         response = await mcp_client.chat(req.message)
#         return {"response": response}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@app.post("/research")
async def research(req: ResearchRequest, _=Depends(verify_token)):
    """
    Streams SSE events:
      data: {"type": "tool_log", "tool": "company_firmographic", "input": {...}, "output": "...", "cached": false}
      data: {"type": "brief", "content": "# Stripe Inc..."}
    """
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
 
    async def event_stream():
        try:
            async for event in mcp_client.research_stream(req.prompt.strip()):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
 
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
 
 
@app.post("/chat")
async def chat(req: ChatRequest, _=Depends(verify_token)):
    """
    Streams SSE events:
      data: {"type": "tool_log", "tool": "contact_search", "input": {...}, "output": "...", "cached": true}
      data: {"type": "message", "content": "Here's what I found..."}
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
 
    async def event_stream():
        try:
            async for event in mcp_client.chat_stream(req.message.strip()):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
 
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
