from typing import Any, Dict

from fastapi import FastAPI

from services.low_altitude_service.algorithms import execute_tool


app = FastAPI(title="低空物流多算法服务")


def build_mcp_response(
    subtask_id: str,
    tool_name: str,
    code: int,
    message: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "subtask_id": subtask_id,
        "tool_name": tool_name,
        "success": code == 200,
        "output": data,
        "message": message,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "low-altitude-algorithms"}


@app.post("/infer")
def infer(payload: Dict[str, Any]):
    tool_name = payload.get("tool_name", "")
    subtask_id = payload.get("subtask_id", "")
    code, message, data = execute_tool(
        tool_name=tool_name,
        input_data=payload.get("input_data", {}),
        parameters=payload.get("parameters", {}),
        subtask_id=subtask_id,
    )
    return build_mcp_response(
        subtask_id, tool_name, code, message, data
    )
