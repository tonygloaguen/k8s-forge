"""Plain text renderer for app.yaml explanations."""

from k8s_forge.explain import ExplanationReport


def render_explanation(report: ExplanationReport) -> str:
    """Render an explanation report as readable plain text."""
    lines: list[str] = []
    for section in report.sections:
        lines.append(section.title)
        for item in section.items:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("Warnings")
    if report.warnings:
        for warning in report.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("Next steps")
    for step in report.next_steps:
        lines.append(f"- {step}")

    return "\n".join(lines).rstrip() + "\n"
