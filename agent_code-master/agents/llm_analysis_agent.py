import json
from typing import Any, Dict

from clients.anythingllm_client import AnythingLLMClient
from core.schema import ExecutionContext


class LLMAnalysisAgent:
    """Generate human-readable scheduling analysis through AnythingLLM.

    This agent never decides whether to dispatch the mission. It only explains
    the already computed scheduling result and gives safe replanning advice.
    """

    def __init__(self, client: AnythingLLMClient | None = None):
        self.client = client or AnythingLLMClient()

    def _compact_context(self, context: ExecutionContext) -> Dict[str, Any]:
        risk_result = context.tool_results.get("RISK_01")
        return {
            "task_id": context.request.task_id,
            "mission": context.parsed_requirement,
            "recommended_solution": context.metadata.get("final_dispatch_solution", {}),
            "candidate_solutions": context.metadata.get("candidate_dispatch_solutions", []),
            "risk_assessment": risk_result.output if risk_result and risk_result.success else {},
            "execution_status": context.quality_report,
            "recent_execution_trace": context.execution_trace[-20:],
            "replan_events": context.replan_events,
            "skipped_tools": context.skipped_tools,
        }

    def _fallback_text(self, context: ExecutionContext) -> str:
        solution = context.metadata.get("final_dispatch_solution", {})
        risk_result = context.tool_results.get("RISK_01")
        risk = risk_result.output if risk_result and risk_result.success else {}
        mode = solution.get("operational_mode") or solution.get("assigned_vehicle_type") or "未知"
        algorithm = solution.get("algorithm_used") or solution.get("algorithm") or "综合调度"
        risk_level = risk.get("risk_level", "UNKNOWN")
        risk_factors = ", ".join(risk.get("risk_factors", [])) or "未发现显著风险因子"
        duration = solution.get("estimated_duration_mins", "--")
        energy = solution.get("estimated_energy_kj", "--")
        distance = solution.get("flight_distance_km", "--")
        dispatch_allowed = risk.get("dispatch_allowed", False)
        return (
            "1. 任务理解：系统已解析配送点、载重、优先级、环境约束和时间窗，并完成空域、气象、无人机、机巢资源检查。\n"
            f"2. 推荐理由：当前推荐采用 {mode}，对应策略为 {algorithm}，预计距离 {distance} km、耗时 {duration} min、能耗 {energy} kJ。\n"
            f"3. 风险分析：综合风险等级为 {risk_level}，主要风险因子为：{risk_factors}。\n"
            f"4. 重规划建议：{'风险评估允许派发，可按推荐方案执行并持续监测气象与资源状态。' if dispatch_allowed else '风险评估未授权派发，建议保持任务待命并进行人工复核。'}"
        )

    async def run_async(self, context: ExecutionContext) -> ExecutionContext:
        compact = self._compact_context(context)
        prompt = f"""
你是低空无人机任务智能体调度专家。请基于下面的调度上下文，输出中文分析，适合展示在前端“大模型调度分析”面板中。

请严格分成四部分：
1. 任务理解：概括任务类型、载重、时间窗和环境约束。
2. 推荐理由：解释为什么选择当前 recommended_solution。
3. 风险分析：说明空域、气象、资源、时间窗、能耗中的主要风险。
4. 重规划建议：给出环境恶化或资源不可用时的后续调度建议。

要求：
- 不要编造上下文中没有的数据。
- 不要覆盖系统风险评估结果。
- 如果风险评估不允许派发，要明确建议人工复核。
- 用专业但简洁的中文表达。

调度上下文：
{json.dumps(compact, ensure_ascii=False, indent=2)}
""".strip()

        result = await self.client.chat(
            message=prompt,
            mode="chat",
            session_id=context.request.task_id,
        )

        text = result.get("text") or ""
        if not text:
            text = self._fallback_text(context)

        context.metadata["llm_api_used"] = result.get("enabled", False)
        context.metadata["llm_analysis"] = {
            "success": result.get("success", False),
            "text": text,
            "sources": result.get("sources", []),
        }
        return context
