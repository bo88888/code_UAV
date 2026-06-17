from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class MCPRequest:
    """Protocol request sent to a low-altitude algorithm service."""

    task_id: str
    subtask_id: str
    tool_name: str
    input_data: Dict[str, Any]
    parameters: Dict[str, Any]
    output_schema: List[str]


@dataclass
class MCPResponse:
    """Normalized protocol response returned by an algorithm service."""

    subtask_id: str
    tool_name: str
    success: bool
    output: Dict[str, Any]
    message: str = ""
    confidence: Optional[float] = None
