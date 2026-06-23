import os


REQUIREMENT_XML_PATH = "data/requirement.xml"
OUTPUT_REPORT_PATH = "outputs/final_report.json"
HTTP_TIMEOUT = 30
QUALITY_THRESHOLD = 0.75

LOW_ALTITUDE_SERVICE_URL = os.getenv(
    "LOW_ALTITUDE_SERVICE_URL", "http://127.0.0.1:8888/infer"
)

# AnythingLLM is optional. Keep the key in .env or shell environment only.
ANYTHINGLLM_BASE_URL = os.getenv("ANYTHINGLLM_BASE_URL", "http://127.0.0.1:3001")
ANYTHINGLLM_WORKSPACE_SLUG = os.getenv(
    "ANYTHINGLLM_WORKSPACE_SLUG",
    "50053650-a316-4bf6-a991-17d5a22c1a3c",
)
ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "")
LLM_ANALYSIS_ENABLED = os.getenv("LLM_ANALYSIS_ENABLED", "true").lower() == "true"

TOOL_SERVICE_MAP = {
    "airspace_check_service": LOW_ALTITUDE_SERVICE_URL,
    "weather_check_service": LOW_ALTITUDE_SERVICE_URL,
    "uav_status_service": LOW_ALTITUDE_SERVICE_URL,
    "dock_status_service": LOW_ALTITUDE_SERVICE_URL,
    "compliance_route_service": LOW_ALTITUDE_SERVICE_URL,
    "weather_adaptive_dispatch_service": LOW_ALTITUDE_SERVICE_URL,
    "medical_time_window_scheduler_service": LOW_ALTITUDE_SERVICE_URL,
    "agentic_task_allocation_service": LOW_ALTITUDE_SERVICE_URL,
    "risk_assessment_service": LOW_ALTITUDE_SERVICE_URL,
    "dispatch_report_service": LOW_ALTITUDE_SERVICE_URL,
}
