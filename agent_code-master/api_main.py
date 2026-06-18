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
from agents.orchestrator_agent import OrchestratorAgent
from agents.postprocess_agent import PostprocessAgent
from agents.replan_agent import ReplanDecisionAgent
from agents.report_agent import ReportAgent
from config import HTTP_TIMEOUT, REQUIREMENT_XML_PATH, TOOL_SERVICE_MAP
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
        }
    )
    simulation_scenario: str = "normal"


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
    return ReportAgent().run(context)


@app.get("/", include_in_schema=False)
def web_console():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {
        "status": "frontend_not_found",
        "message": "请确认 frontend/index.html 已存在。",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "low-altitude-orchestrator"}


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
