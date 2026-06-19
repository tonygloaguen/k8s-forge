"""Safe kubectl command entry points.

This module intentionally does not execute kubectl yet.
"""


def kubectl_not_implemented(command_name: str) -> str:
    """Return a consistent placeholder message for kubectl-backed commands."""
    return f"{command_name} is not implemented yet."
