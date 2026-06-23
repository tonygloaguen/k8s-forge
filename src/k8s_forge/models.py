"""Pydantic models for application configuration."""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


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


class AutoscalingConfig(BaseModel):
    """Horizontal Pod Autoscaler configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    minReplicas: int = Field(default=2, ge=1)
    maxReplicas: int = Field(default=6, ge=1)
    targetCPUUtilizationPercentage: int = Field(default=70, ge=1, le=100)

    @model_validator(mode="after")
    def validate_replica_bounds(self) -> "AutoscalingConfig":
        """Ensure HPA maximum replicas is not lower than minimum replicas."""
        if self.maxReplicas < self.minReplicas:
            msg = "maxReplicas must be greater than or equal to minReplicas"
            raise ValueError(msg)
        return self


class IngressTlsConfig(BaseModel):
    """Optional Ingress TLS configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    secretName: str | None = None

    @model_validator(mode="after")
    def validate_tls_secret(self) -> "IngressTlsConfig":
        """Require a secret name when TLS is enabled."""
        if self.enabled and not self.secretName:
            msg = "secretName is required when ingress.tls.enabled is true"
            raise ValueError(msg)
        return self


class IngressCertManagerConfig(BaseModel):
    """Optional cert-manager integration for Ingress TLS."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    clusterIssuer: str | None = None

    @model_validator(mode="after")
    def validate_cluster_issuer(self) -> "IngressCertManagerConfig":
        """Require a ClusterIssuer when cert-manager integration is enabled."""
        if self.enabled and not self.clusterIssuer:
            msg = "clusterIssuer is required when ingress.certManager.enabled is true"
            raise ValueError(msg)
        return self


class IngressConfig(BaseModel):
    """Ingress-NGINX and optional cert-manager configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    host: str | None = None
    className: str = Field(default="nginx", min_length=1)
    path: str = "/"
    pathType: Literal["Prefix", "Exact", "ImplementationSpecific"] = "Prefix"
    tls: IngressTlsConfig = Field(default_factory=IngressTlsConfig)
    certManager: IngressCertManagerConfig = Field(
        default_factory=IngressCertManagerConfig
    )
    annotations: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ingress(self) -> "IngressConfig":
        """Validate required fields for enabled Ingress routing."""
        if self.enabled and not self.host:
            msg = "host is required when ingress.enabled is true"
            raise ValueError(msg)
        if not self.path.startswith("/"):
            msg = "ingress.path must start with '/'"
            raise ValueError(msg)
        return self


class MeshConfig(BaseModel):
    """Service mesh readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    provider: Literal["linkerd"] = "linkerd"
    inject: StrictBool = False
    annotations: dict[str, str] = Field(
        default_factory=lambda: {"linkerd.io/inject": "enabled"}
    )


class NetworkPolicyIngressConfig(BaseModel):
    """Ingress rules for the educational NetworkPolicy profile."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    fromNamespaces: list[str] = Field(default_factory=lambda: ["ingress-nginx"])
    ports: list[int] = Field(default_factory=list)

    @field_validator("fromNamespaces")
    @classmethod
    def validate_from_namespaces(cls, value: list[str]) -> list[str]:
        """Require non-empty namespace names when provided."""
        if any(not namespace for namespace in value):
            msg = "networkPolicy.ingress.fromNamespaces values must be non-empty"
            raise ValueError(msg)
        return value

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, value: list[int]) -> list[int]:
        """Ensure NetworkPolicy ports are valid TCP ports."""
        if any(port < 1 or port > 65535 for port in value):
            msg = "networkPolicy.ingress.ports values must be between 1 and 65535"
            raise ValueError(msg)
        return value


class NetworkPolicyEgressConfig(BaseModel):
    """Future egress policy switch. Not rendered in v0.6.0."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False


class NetworkPolicyConfig(BaseModel):
    """NetworkPolicy readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    profile: Literal["ingress-only"] = "ingress-only"
    ingress: NetworkPolicyIngressConfig = Field(
        default_factory=NetworkPolicyIngressConfig
    )
    egress: NetworkPolicyEgressConfig = Field(default_factory=NetworkPolicyEgressConfig)


class PolicyRulesConfig(BaseModel):
    """Baseline Kyverno policy rules."""

    model_config = ConfigDict(extra="forbid")

    requireRecommendedLabels: StrictBool = True
    disallowPrivilegedContainers: StrictBool = True
    requireRunAsNonRoot: StrictBool = True
    requireResources: StrictBool = True
    disallowLatestTag: StrictBool = True


class PolicyConfig(BaseModel):
    """Admission policy readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    provider: Literal["kyverno"] = "kyverno"
    profile: Literal["baseline"] = "baseline"
    validationFailureAction: Literal["Audit", "Enforce"] = "Audit"
    background: StrictBool = True
    rules: PolicyRulesConfig = Field(default_factory=PolicyRulesConfig)


class AppConfig(BaseModel):
    """Top-level user configuration."""

    model_config = ConfigDict(extra="forbid")

    app: AppSpec
    config: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    probes: ProbesConfig = Field(default_factory=ProbesConfig)
    autoscaling: AutoscalingConfig = Field(default_factory=AutoscalingConfig)
    ingress: IngressConfig = Field(default_factory=IngressConfig)
    mesh: MeshConfig = Field(default_factory=MeshConfig)
    networkPolicy: NetworkPolicyConfig = Field(default_factory=NetworkPolicyConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)

    @model_validator(mode="after")
    def validate_ingress_service(self) -> "AppConfig":
        """Ensure enabled Ingress has a Service backend to target."""
        if self.ingress.enabled and not self.service.enabled:
            msg = "service.enabled must be true when ingress.enabled is true"
            raise ValueError(msg)
        return self
