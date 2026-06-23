import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents.invoker_agent import InvokerAgent
from agents.llm_analysis_agent import LLMAnalysisAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.postprocess_agent import PostprocessAgent
from agents.replan_agent import ReplanDecisionAgent
from agents.report_agent import ReportAgent
from clients.anythingllm_client import AnythingLLMClient
from config import (
    HTTP_TIMEOUT,
    LLM_ANALYSIS_ENABLED,
    REQUIREMENT_XML_PATH,
    TOOL_SERVICE_MAP,
)
from core.schema import ExecutionContext, TaskRequest
from mcp.registry import ToolRegistry
from scheduler.scheduler_center import IntelligentScheduler


app = FastAPI(title="低空任务智能体调度中心 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

if FRONTEND_DIR.exists():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="frontend",
    )


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_name, service_url in TOOL_SERVICE_MAP.items():
        registry.register(tool_name, service_url)
    return registry


class PipelineRequest(BaseModel):
    task_id: str = ""
    requirement_xml_path: str = REQUIREMENT_XML_PATH
    mission_type: Optional[str] = None
    delivery_points: List[Dict[str, Any]] = Field(default_factory=list)
    cargo_weight_kg: float = 0.0
    priority: int = 1
    environmental_constraints: Dict[str, Any] = Field(default_factory=dict)
    output_requirements: Dict[str, Any] = Field(
        default_factory=lambda: {
            "format": "json",
            "need_risk_assessment": True,
            "need_orchestration_trace": True,
            "need_llm_analysis": True,
        }
    )
    simulation_scenario: str = "normal"


class LLMChatRequest(BaseModel):
    message: str
    mode: str = "chat"
    session_id: Optional[str] = None
    reset: bool = False


async def execute_pipeline(
    request: TaskRequest,
    simulation_scenario: str = "normal",
    registry: Optional[ToolRegistry] = None,
) -> ExecutionContext:
    context = ExecutionContext(request=request)
    registry = registry or build_registry()
    context = OrchestratorAgent(registry).prepare(
        context,
        overrides={"simulation_scenario": simulation_scenario},
    )
    invoker = InvokerAgent(registry, timeout=HTTP_TIMEOUT)
    scheduler = IntelligentScheduler(invoker, ReplanDecisionAgent())
    context = await scheduler.run_async(context)
    context = PostprocessAgent().run(context)
    context = ReportAgent().run(context)

    need_llm = bool(request.output_requirements.get("need_llm_analysis", True))
    if LLM_ANALYSIS_ENABLED and need_llm:
        context = await LLMAnalysisAgent().run_async(context)
        context = ReportAgent().run(context)

    return context


@app.get("/", include_in_schema=False)
def web_console():
    index_path = FRONTEND_DIR / "index_llm.html"
    if index_path.exists():
        return FileResponse(index_path)
    fallback_path = FRONTEND_DIR / "index.html"
    if fallback_path.exists():
        return FileResponse(fallback_path)
    return {
        "status": "frontend_not_found",
        "message": "请确认 frontend/index_llm.html 已存在。",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "low-altitude-orchestrator"}


@app.get("/api/v1/llm/status")
def llm_status():
    client = AnythingLLMClient()
    return {
        "enabled": client.enabled,
        "base_url_configured": bool(client.base_url),
        "workspace_configured": bool(client.workspace_slug),
        "credential_configured": bool(client.token),
        "llm_analysis_enabled": LLM_ANALYSIS_ENABLED,
    }


@app.post("/api/v1/llm/chat")
async def llm_chat(req: LLMChatRequest):
    client = AnythingLLMClient()
    return await client.chat(
        message=req.message,
        mode=req.mode,
        session_id=req.session_id or "frontend-llm-panel",
        reset=req.reset,
    )


@app.post("/api/v1/task/submit")
async def submit_task(req: PipelineRequest):
    started_at = time.perf_counter()
    task_id = req.task_id.strip() or f"MISSION_{uuid.uuid4().hex[:8]}"
    request = TaskRequest(
        task_id=task_id,
        requirement_xml_path=req.requirement_xml_path,
        mission_type=req.mission_type or "emergency_medical",
        delivery_points=req.delivery_points,
        cargo_weight_kg=req.cargo_weight_kg,
        priority=req.priority,
        environmental_constraints=req.environmental_constraints,
        output_requirements=req.output_requirements,
    )
    context = await execute_pipeline(
        request, simulation_scenario=req.simulation_scenario
    )

    response = dict(context.final_report)
    response["llm_used"] = bool(context.metadata.get("llm_analysis"))
    response["llm_analysis"] = context.metadata.get("llm_analysis", {})
    response["completed_at"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    response["time_cost_seconds"] = round(
        time.perf_counter() - started_at, 4
    )

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"report_{task_id}.json"
    report_path.write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    response["report_path"] = str(report_path)
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)
