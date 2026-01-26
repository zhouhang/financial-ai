"""
Dify integration router - No authentication required
"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from services.dify_service import DifyService

router = APIRouter(prefix="/dify", tags=["Dify"])


class ChatRequest(BaseModel):
    query: str = Field(..., description="User query")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    streaming: bool = Field(False, description="Enable streaming response")


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat with Dify API and detect commands
    No authentication required
    """
    # Use a default user identifier
    user_identifier = "anonymous_user"

    if request.streaming:
        # Return streaming response
        return StreamingResponse(
            DifyService.chat_completion_stream(
                query=request.query,
                user=user_identifier,
                conversation_id=request.conversation_id
            ),
            media_type="text/event-stream"
        )
    else:
        # Return blocking response
        response = await DifyService.chat_completion(
            query=request.query,
            user=user_identifier,
            conversation_id=request.conversation_id
        )
        return response
