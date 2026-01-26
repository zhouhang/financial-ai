"""
Dify API integration service
"""
import httpx
import re
from typing import Optional, AsyncGenerator
from config import settings
from fastapi import HTTPException, status


class DifyService:
    @staticmethod
    def detect_command(text: str) -> Optional[str]:
        """
        Detect special commands in Dify response

        Args:
            text: Response text from Dify

        Returns:
            Command name if detected, None otherwise
        """
        # Define command patterns
        commands = {
            r'\[create_schema\]': 'create_schema',
            r'\[update_schema\]': 'update_schema',
            r'\[schema_list\]': 'schema_list',
            r'\[login_form\]': 'login_form'
        }

        for pattern, command in commands.items():
            if re.search(pattern, text, re.IGNORECASE):
                return command

        return None

    @staticmethod
    async def chat_completion(
        query: str,
        user: str,
        conversation_id: Optional[str] = None
    ) -> dict:
        """
        Send chat request to Dify API

        Args:
            query: User query
            user: User identifier
            conversation_id: Optional conversation ID for context

        Returns:
            Response from Dify API with detected command
        """
        url = f"{settings.DIFY_API_URL}/chat-messages"

        headers = {
            "Authorization": f"Bearer {settings.DIFY_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": {},
            "query": query,
            "response_mode": "blocking",
            "user": user
        }

        if conversation_id:
            payload["conversation_id"] = conversation_id

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

                # Detect command in response
                answer = data.get("answer", "")
                detected_command = DifyService.detect_command(answer)

                # Add command to metadata
                if "metadata" not in data:
                    data["metadata"] = {}
                data["metadata"]["command"] = detected_command

                return data

        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Dify API error: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Dify API: {str(e)}"
            )

    @staticmethod
    async def chat_completion_stream(
        query: str,
        user: str,
        conversation_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Send streaming chat request to Dify API

        Args:
            query: User query
            user: User identifier
            conversation_id: Optional conversation ID for context

        Yields:
            Server-sent events from Dify API
        """
        url = f"{settings.DIFY_API_URL}/chat-messages"

        headers = {
            "Authorization": f"Bearer {settings.DIFY_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": {},
            "query": query,
            "response_mode": "streaming",
            "user": user
        }

        if conversation_id:
            payload["conversation_id"] = conversation_id

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()

                    full_answer = ""
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            # Forward the SSE event with proper format
                            yield f"data: {data}\n\n"

                            # Try to parse and accumulate answer for command detection
                            try:
                                import json
                                event_data = json.loads(data)
                                if event_data.get("event") == "message":
                                    full_answer += event_data.get("answer", "")
                            except:
                                pass

                    # Send final event with detected command
                    detected_command = DifyService.detect_command(full_answer)
                    if detected_command:
                        import json
                        command_event = {
                            "event": "command_detected",
                            "command": detected_command
                        }
                        yield f"data: {json.dumps(command_event)}\n\n"

        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Dify API error: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Dify API: {str(e)}"
            )
