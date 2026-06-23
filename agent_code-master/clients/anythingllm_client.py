import os
from typing import Any, Dict, Optional

import httpx


class AnythingLLMClient:
    """Client for the local AnythingLLM workspace chat endpoint."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        workspace_slug: Optional[str] = None,
        timeout: int = 60,
    ):
        self.base_url = (base_url or os.getenv("ANYTHINGLLM_BASE_URL", "")).rstrip("/")
        self.token = token or os.getenv("ANYTHINGLLM_API_KEY", "")
        self.workspace_slug = workspace_slug or os.getenv("ANYTHINGLLM_WORKSPACE_SLUG", "")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.token and self.workspace_slug)

    async def chat(
        self,
        message: str,
        mode: str = "chat",
        session_id: Optional[str] = None,
        reset: bool = False,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "success": False,
                "text": "AnythingLLM 未启用，请检查环境变量配置。",
                "sources": [],
                "raw": {},
            }

        url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        headers = {
            "Authorization": "Bearer " + self.token,
            "Content-Type": "application/json",
        }
        payload = {
            "message": message,
            "mode": mode,
            "sessionId": session_id or "low-altitude-orchestrator",
            "reset": reset,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            return {
                "enabled": True,
                "success": not bool(data.get("error")),
                "text": data.get("textResponse") or data.get("response") or "",
                "sources": data.get("sources", []),
                "raw": data,
            }
        except Exception as exc:
            return {
                "enabled": True,
                "success": False,
                "text": f"AnythingLLM 调用失败：{exc}",
                "sources": [],
                "raw": {},
            }
