"""Pydantic models for application configuration."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppMetadata(BaseModel):
    """Application identity and namespace."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    labels: dict[str, str] = Field(default_factory=dict)


class ImageConfig(BaseModel):
    """Container image configuration."""

    model_config = ConfigDict(extra="forbid")

    repository: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    pull_policy: Literal["Always", "IfNotPresent", "Never"] = "IfNotPresent"


class DeploymentConfig(BaseModel):
    """Deployment configuration."""

    model_config = ConfigDict(extra="forbid")

    replicas: int = Field(default=1, ge=1)
    container_port: int = Field(default=8080, ge=1, le=65535)


class ServiceConfig(BaseModel):
    """Service configuration."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["ClusterIP", "NodePort", "LoadBalancer"] = "ClusterIP"
    port: int = Field(default=80, ge=1, le=65535)
    target_port: int = Field(default=8080, ge=1, le=65535)


class AppConfig(BaseModel):
    """Top-level user configuration."""

    model_config = ConfigDict(extra="forbid")

    app: AppMetadata
    image: ImageConfig
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    config: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
