"""Project-specific exceptions."""


class K8sForgeError(Exception):
    """Base exception for k8s-forge errors."""


class ConfigLoadError(K8sForgeError):
    """Raised when an application configuration cannot be loaded."""


class RenderError(K8sForgeError):
    """Raised when rendering cannot be completed."""


class KubectlError(K8sForgeError):
    """Raised when a kubectl operation cannot be completed."""
