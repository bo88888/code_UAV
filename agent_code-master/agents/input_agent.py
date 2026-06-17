from pathlib import Path

from core.schema import ExecutionContext


class InputAgent:
    """Validate low-altitude mission input files and direct request fields."""

    def run(self, context: ExecutionContext) -> ExecutionContext:
        xml_path = Path(context.request.requirement_xml_path)
        issues = []

        if not xml_path.exists():
            issues.append(f"requirement XML does not exist: {xml_path}")
        if context.request.cargo_weight_kg < 0:
            issues.append("cargo_weight_kg cannot be negative")
        if not 1 <= context.request.priority <= 5:
            issues.append("priority must be between 1 and 5")

        context.metadata["requirement_xml_exists"] = xml_path.exists()
        context.metadata["requirement_xml_path"] = str(xml_path)
        context.metadata["input_validation_issues"] = issues
        context.metadata["input_stage"] = "validated"
        return context
