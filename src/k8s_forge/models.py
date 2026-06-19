"""Pydantic models for application configuration."""

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class AppSpec(BaseModel):
    """Application runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    image: str = Field(min_length=1)
    containerPort: int = Field(ge=1, le=65535)
    replicas: int = Field(ge=1)


class ServiceConfig(BaseModel):
    """Service exposure configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    port: int = Field(default=80, ge=1, le=65535)


class ResourceValues(BaseModel):
    """Optional CPU and memory resource values."""

    model_config = ConfigDict(extra="forbid")

    cpu: str | None = None
    memory: str | None = None


class ResourcesConfig(BaseModel):
    """Container resource requests and limits."""

    model_config = ConfigDict(extra="forbid")

    requests: ResourceValues = Field(default_factory=ResourceValues)
    limits: ResourceValues = Field(default_factory=ResourceValues)


class ProbesConfig(BaseModel):
    """Optional HTTP probe paths."""

    model_config = ConfigDict(extra="forbid")

    liveness: str | None = None
    readiness: str | None = None


class IngressConfig(BaseModel):
    """Ingress configuration reserved for a future renderer."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    host: str | None = None


class AppConfig(BaseModel):
    """Top-level user configuration."""

    model_config = ConfigDict(extra="forbid")

    app: AppSpec
    config: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    probes: ProbesConfig = Field(default_factory=ProbesConfig)
    ingress: IngressConfig = Field(default_factory=IngressConfig)
