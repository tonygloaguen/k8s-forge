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

SupplyChainSeverity = Literal["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _default_supply_chain_severity() -> list[SupplyChainSeverity]:
    return ["HIGH", "CRITICAL"]


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


class SupplyChainScanConfig(BaseModel):
    """Container image vulnerability scan configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    tool: Literal["trivy"] = "trivy"
    severity: list[SupplyChainSeverity] = Field(
        default_factory=_default_supply_chain_severity
    )


class SupplyChainSbomConfig(BaseModel):
    """Software Bill of Materials generation configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    tool: Literal["syft"] = "syft"
    format: Literal["cyclonedx-json", "spdx-json", "syft-json"] = "cyclonedx-json"


class SupplyChainSigningConfig(BaseModel):
    """Container image signing readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    tool: Literal["cosign"] = "cosign"
    keyless: StrictBool = True


class SupplyChainConfig(BaseModel):
    """Supply chain readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    image: str = ""
    scan: SupplyChainScanConfig = Field(default_factory=SupplyChainScanConfig)
    sbom: SupplyChainSbomConfig = Field(default_factory=SupplyChainSbomConfig)
    signing: SupplyChainSigningConfig = Field(default_factory=SupplyChainSigningConfig)


class CiPythonQualityConfig(BaseModel):
    """Python quality gates for generated CI workflows."""

    model_config = ConfigDict(extra="forbid")

    ruff: StrictBool = True
    mypy: StrictBool = True
    bandit: StrictBool = True
    pipAudit: StrictBool = True
    pytest: StrictBool = True
    build: StrictBool = True


class CiPythonConfig(BaseModel):
    """Python CI configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    version: str = Field(default="3.12", min_length=1)
    quality: CiPythonQualityConfig = Field(default_factory=CiPythonQualityConfig)


class CiContainerScanConfig(BaseModel):
    """Container image scan configuration for CI."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    tool: Literal["trivy"] = "trivy"
    severity: list[SupplyChainSeverity] = Field(
        default_factory=_default_supply_chain_severity
    )


class CiContainerSbomConfig(BaseModel):
    """Container SBOM generation configuration for CI."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    tool: Literal["syft"] = "syft"
    format: Literal["cyclonedx-json", "spdx-json", "syft-json"] = "cyclonedx-json"


class CiContainerConfig(BaseModel):
    """Container supply-chain checks for CI."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    image: str = ""
    dockerfile: str = Field(default="Dockerfile", min_length=1)
    context: str = Field(default=".", min_length=1)
    scan: CiContainerScanConfig = Field(default_factory=CiContainerScanConfig)
    sbom: CiContainerSbomConfig = Field(default_factory=CiContainerSbomConfig)


class CiArtifactsConfig(BaseModel):
    """Generated CI artifact upload switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CiConfig(BaseModel):
    """GitHub Actions readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    provider: Literal["github-actions"] = "github-actions"
    python: CiPythonConfig = Field(default_factory=CiPythonConfig)
    container: CiContainerConfig = Field(default_factory=CiContainerConfig)
    artifacts: CiArtifactsConfig = Field(default_factory=CiArtifactsConfig)


class GitOpsApplicationConfig(BaseModel):
    """ArgoCD Application metadata configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    namespace: str = Field(default="argocd", min_length=1)
    project: str = Field(default="default", min_length=1)


class GitOpsDestinationConfig(BaseModel):
    """ArgoCD Application destination configuration."""

    model_config = ConfigDict(extra="forbid")

    server: str = Field(default="https://kubernetes.default.svc", min_length=1)
    namespace: str = ""


class GitOpsSourceConfig(BaseModel):
    """ArgoCD Application source configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    repo_url: str = Field(default="", alias="repoURL")
    target_revision: str = Field(default="main", alias="targetRevision", min_length=1)
    path: str = ""
    type: Literal["helm"] = "helm"


class GitOpsSyncPolicyConfig(BaseModel):
    """ArgoCD synchronization policy readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    automated: StrictBool = False
    prune: StrictBool = False
    self_heal: StrictBool = Field(default=False, alias="selfHeal")


class GitOpsConfig(BaseModel):
    """ArgoCD GitOps readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: StrictBool = False
    provider: Literal["argocd"] = "argocd"
    application: GitOpsApplicationConfig = Field(
        default_factory=GitOpsApplicationConfig
    )
    destination: GitOpsDestinationConfig = Field(
        default_factory=GitOpsDestinationConfig
    )
    source: GitOpsSourceConfig = Field(default_factory=GitOpsSourceConfig)
    sync_policy: GitOpsSyncPolicyConfig = Field(
        default_factory=GitOpsSyncPolicyConfig, alias="syncPolicy"
    )

    @model_validator(mode="after")
    def validate_enabled_gitops(self) -> "GitOpsConfig":
        """Require source fields when GitOps readiness is enabled."""
        if self.enabled and not self.source.repo_url.strip():
            msg = "source.repoURL is required when gitops.enabled is true"
            raise ValueError(msg)
        if self.enabled and not self.source.path.strip():
            msg = "source.path is required when gitops.enabled is true"
            raise ValueError(msg)
        return self


class ObservabilityMetricsConfig(BaseModel):
    """Prometheus metrics scraping readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    path: str = "/metrics"
    portName: str = Field(default="http", min_length=1)
    interval: str = Field(default="30s", min_length=1)

    @field_validator("path")
    @classmethod
    def validate_metrics_path(cls, value: str) -> str:
        """Require HTTP metrics paths to be absolute."""
        if not value.startswith("/"):
            msg = "observability.metrics.path must start with '/'"
            raise ValueError(msg)
        return value

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, value: str) -> str:
        """Accept simple Prometheus-style intervals such as 30s, 1m, or 5m."""
        if (
            len(value) < 2
            or not value[:-1].isdigit()
            or value[-1] not in {"s", "m", "h"}
        ):
            msg = "observability.metrics.interval must look like 30s, 1m, or 5m"
            raise ValueError(msg)
        return value


class ObservabilityServiceMonitorConfig(BaseModel):
    """Prometheus Operator ServiceMonitor readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    namespace: str = ""
    labels: dict[str, str] = Field(default_factory=dict)


class ObservabilityGrafanaDashboardConfig(BaseModel):
    """Grafana dashboard readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    title: str = ""


class ObservabilityGrafanaConfig(BaseModel):
    """Grafana readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    dashboard: ObservabilityGrafanaDashboardConfig = Field(
        default_factory=ObservabilityGrafanaDashboardConfig
    )


class ObservabilityAlertsConfig(BaseModel):
    """Future PrometheusRule switch. Not rendered in v0.11.0."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False


class ObservabilityConfig(BaseModel):
    """Observability readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    provider: Literal["prometheus"] = "prometheus"
    metrics: ObservabilityMetricsConfig = Field(
        default_factory=ObservabilityMetricsConfig
    )
    serviceMonitor: ObservabilityServiceMonitorConfig = Field(
        default_factory=ObservabilityServiceMonitorConfig
    )
    grafana: ObservabilityGrafanaConfig = Field(
        default_factory=ObservabilityGrafanaConfig
    )
    alerts: ObservabilityAlertsConfig = Field(default_factory=ObservabilityAlertsConfig)


class LoggingApplicationLogsConfig(BaseModel):
    """Application log source readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    source: Literal["stdout"] = "stdout"


class LoggingLokiConfig(BaseModel):
    """Loki readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    namespace: str = Field(default="monitoring", min_length=1)
    datasource_name: str = Field(default="Loki", alias="datasourceName", min_length=1)


class LoggingCollectorConfig(BaseModel):
    """Log collector readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    type: Literal["promtail"] = "promtail"


class LoggingGrafanaDashboardConfig(BaseModel):
    """Grafana log dashboard readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    title: str = ""


class LoggingGrafanaConfig(BaseModel):
    """Grafana logging readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    dashboard: LoggingGrafanaDashboardConfig = Field(
        default_factory=LoggingGrafanaDashboardConfig
    )


class LoggingQueriesConfig(BaseModel):
    """LogQL query examples readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class LoggingConfig(BaseModel):
    """Logging readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: StrictBool = False
    provider: Literal["loki"] = "loki"
    application_logs: LoggingApplicationLogsConfig = Field(
        default_factory=LoggingApplicationLogsConfig, alias="applicationLogs"
    )
    loki: LoggingLokiConfig = Field(default_factory=LoggingLokiConfig)
    collector: LoggingCollectorConfig = Field(default_factory=LoggingCollectorConfig)
    grafana: LoggingGrafanaConfig = Field(default_factory=LoggingGrafanaConfig)
    queries: LoggingQueriesConfig = Field(default_factory=LoggingQueriesConfig)


class TracingBackendConfig(BaseModel):
    """Tracing backend readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["tempo"] = "tempo"
    namespace: str = Field(default="monitoring", min_length=1)
    datasource_name: str = Field(default="Tempo", alias="datasourceName", min_length=1)


class TracingCollectorConfig(BaseModel):
    """OpenTelemetry Collector readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    type: Literal["opentelemetry-collector"] = "opentelemetry-collector"
    endpoint: str = Field(
        default="http://otel-collector.monitoring.svc.cluster.local:4318",
        min_length=1,
    )
    protocol: Literal["otlp-http", "otlp-grpc"] = "otlp-http"


class TracingInstrumentationConfig(BaseModel):
    """Application tracing instrumentation readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: StrictBool = True
    mode: Literal["env"] = "env"
    service_name: str = Field(default="", alias="serviceName")


class TracingGrafanaDashboardConfig(BaseModel):
    """Grafana trace dashboard readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    title: str = ""


class TracingGrafanaConfig(BaseModel):
    """Grafana tracing readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    dashboard: TracingGrafanaDashboardConfig = Field(
        default_factory=TracingGrafanaDashboardConfig
    )


class TracingExamplesConfig(BaseModel):
    """Tracing example file generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class TracingConfig(BaseModel):
    """Tracing readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    provider: Literal["opentelemetry"] = "opentelemetry"
    backend: TracingBackendConfig = Field(default_factory=TracingBackendConfig)
    collector: TracingCollectorConfig = Field(default_factory=TracingCollectorConfig)
    instrumentation: TracingInstrumentationConfig = Field(
        default_factory=TracingInstrumentationConfig
    )
    grafana: TracingGrafanaConfig = Field(default_factory=TracingGrafanaConfig)
    examples: TracingExamplesConfig = Field(default_factory=TracingExamplesConfig)


class TerraformBackendConfig(BaseModel):
    """Terraform backend readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["local"] = "local"


class TerraformKubernetesProviderConfig(BaseModel):
    """Terraform Kubernetes provider example switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class TerraformHelmProviderConfig(BaseModel):
    """Terraform Helm provider example switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class TerraformCloudProviderConfig(BaseModel):
    """Terraform cloud provider example switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False


class TerraformProvidersConfig(BaseModel):
    """Terraform provider example configuration."""

    model_config = ConfigDict(extra="forbid")

    kubernetes: TerraformKubernetesProviderConfig = Field(
        default_factory=TerraformKubernetesProviderConfig
    )
    helm: TerraformHelmProviderConfig = Field(
        default_factory=TerraformHelmProviderConfig
    )
    cloud: TerraformCloudProviderConfig = Field(
        default_factory=TerraformCloudProviderConfig
    )


class TerraformModulesConfig(BaseModel):
    """Terraform module example generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class TerraformExamplesConfig(BaseModel):
    """Terraform example file generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class TerraformConfig(BaseModel):
    """Terraform readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: StrictBool = False
    project_name: str = Field(default="", alias="projectName")
    backend: TerraformBackendConfig = Field(default_factory=TerraformBackendConfig)
    providers: TerraformProvidersConfig = Field(
        default_factory=TerraformProvidersConfig
    )
    modules: TerraformModulesConfig = Field(default_factory=TerraformModulesConfig)
    examples: TerraformExamplesConfig = Field(default_factory=TerraformExamplesConfig)


class AnsibleInventoryConfig(BaseModel):
    """Ansible inventory readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["local"] = "local"
    hosts: list[str] = Field(default_factory=lambda: ["localhost"])

    @field_validator("hosts")
    @classmethod
    def validate_hosts(cls, value: list[str]) -> list[str]:
        """Ensure the educational inventory has at least one host name."""
        if not value:
            msg = "ansible.inventory.hosts must not be empty"
            raise ValueError(msg)
        if any(not host.strip() for host in value):
            msg = "ansible.inventory.hosts entries must not be empty"
            raise ValueError(msg)
        return value


class AnsiblePlaybookConfig(BaseModel):
    """Ansible playbook readiness configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = "site.yml"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate the local playbook filename."""
        stripped = value.strip()
        if not stripped:
            msg = "ansible.playbook.name must not be empty"
            raise ValueError(msg)
        if not stripped.endswith((".yml", ".yaml")):
            msg = "ansible.playbook.name must end with .yml or .yaml"
            raise ValueError(msg)
        return stripped


class AnsibleRolesConfig(BaseModel):
    """Ansible roles structure generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class AnsibleKubernetesCollectionConfig(BaseModel):
    """Ansible Kubernetes collection example switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class AnsibleCommunityCollectionConfig(BaseModel):
    """Ansible community collection example switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False


class AnsibleCollectionsConfig(BaseModel):
    """Ansible collection example configuration."""

    model_config = ConfigDict(extra="forbid")

    kubernetes: AnsibleKubernetesCollectionConfig = Field(
        default_factory=AnsibleKubernetesCollectionConfig
    )
    community: AnsibleCommunityCollectionConfig = Field(
        default_factory=AnsibleCommunityCollectionConfig
    )


class AnsibleExamplesConfig(BaseModel):
    """Ansible example file generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class AnsibleConfig(BaseModel):
    """Ansible readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: StrictBool = False
    project_name: str = Field(default="", alias="projectName")
    inventory: AnsibleInventoryConfig = Field(default_factory=AnsibleInventoryConfig)
    playbook: AnsiblePlaybookConfig = Field(default_factory=AnsiblePlaybookConfig)
    roles: AnsibleRolesConfig = Field(default_factory=AnsibleRolesConfig)
    collections: AnsibleCollectionsConfig = Field(
        default_factory=AnsibleCollectionsConfig
    )
    examples: AnsibleExamplesConfig = Field(default_factory=AnsibleExamplesConfig)


class SecurityContainerConfig(BaseModel):
    """Container security review switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecurityManifestsConfig(BaseModel):
    """Kubernetes manifest security review switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecurityRbacConfig(BaseModel):
    """RBAC security review switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecurityPodSecurityConfig(BaseModel):
    """Pod Security review switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecurityNetworkConfig(BaseModel):
    """Network security review switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecuritySecretsConfig(BaseModel):
    """Sensitive configuration handling review switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecuritySupplyChainConfig(BaseModel):
    """Supply chain security review switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecurityChecklistConfig(BaseModel):
    """Final security checklist switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecurityExamplesConfig(BaseModel):
    """Security review examples switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class SecurityConfig(BaseModel):
    """Local security audit readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: StrictBool = False
    project_name: str = Field(default="", alias="projectName")
    container: SecurityContainerConfig = Field(default_factory=SecurityContainerConfig)
    manifests: SecurityManifestsConfig = Field(default_factory=SecurityManifestsConfig)
    rbac: SecurityRbacConfig = Field(default_factory=SecurityRbacConfig)
    pod_security: SecurityPodSecurityConfig = Field(
        default_factory=SecurityPodSecurityConfig,
        alias="podSecurity",
    )
    network: SecurityNetworkConfig = Field(default_factory=SecurityNetworkConfig)
    secrets: SecuritySecretsConfig = Field(default_factory=SecuritySecretsConfig)
    supply_chain: SecuritySupplyChainConfig = Field(
        default_factory=SecuritySupplyChainConfig,
        alias="supplyChain",
    )
    checklist: SecurityChecklistConfig = Field(default_factory=SecurityChecklistConfig)
    examples: SecurityExamplesConfig = Field(default_factory=SecurityExamplesConfig)


class CapstoneReportConfig(BaseModel):
    """Capstone report metadata configuration."""

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    audience: Literal["technical", "training", "internship"] = "technical"


class CapstoneChecklistConfig(BaseModel):
    """Capstone validation checklist generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneArchitectureConfig(BaseModel):
    """Capstone architecture overview generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneDevSecOpsMatrixConfig(BaseModel):
    """Capstone DevSecOps chain generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneModulesSummaryConfig(BaseModel):
    """Capstone modules summary generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneManualStepsConfig(BaseModel):
    """Capstone manual steps generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneRuntimeDependenciesConfig(BaseModel):
    """Capstone runtime dependencies generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneSecuritySummaryConfig(BaseModel):
    """Capstone security summary generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneV1ReadinessConfig(BaseModel):
    """Capstone v1 readiness generation switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneExamplesConfig(BaseModel):
    """Capstone educational examples switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


class CapstoneConfig(BaseModel):
    """Final DevSecOps lab synthesis readiness configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: StrictBool = False
    project_name: str = Field(default="", alias="projectName")
    report: CapstoneReportConfig = Field(default_factory=CapstoneReportConfig)
    checklist: CapstoneChecklistConfig = Field(default_factory=CapstoneChecklistConfig)
    architecture: CapstoneArchitectureConfig = Field(
        default_factory=CapstoneArchitectureConfig
    )
    devsecops_matrix: CapstoneDevSecOpsMatrixConfig = Field(
        default_factory=CapstoneDevSecOpsMatrixConfig,
        alias="devsecopsMatrix",
    )
    modules_summary: CapstoneModulesSummaryConfig = Field(
        default_factory=CapstoneModulesSummaryConfig,
        alias="modulesSummary",
    )
    manual_steps: CapstoneManualStepsConfig = Field(
        default_factory=CapstoneManualStepsConfig,
        alias="manualSteps",
    )
    runtime_dependencies: CapstoneRuntimeDependenciesConfig = Field(
        default_factory=CapstoneRuntimeDependenciesConfig,
        alias="runtimeDependencies",
    )
    security_summary: CapstoneSecuritySummaryConfig = Field(
        default_factory=CapstoneSecuritySummaryConfig,
        alias="securitySummary",
    )
    v1_readiness: CapstoneV1ReadinessConfig = Field(
        default_factory=CapstoneV1ReadinessConfig,
        alias="v1Readiness",
    )
    examples: CapstoneExamplesConfig = Field(default_factory=CapstoneExamplesConfig)


class AppConfig(BaseModel):
    """Top-level user configuration."""

    model_config = ConfigDict(extra="forbid")

    app: AppSpec
    config: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)

    @field_validator("config", mode="before")
    @classmethod
    def normalize_config_section(cls, value: object) -> object:
        """Accept discovery-style config.enabled/data and legacy flat config maps."""
        if not isinstance(value, dict):
            return value
        if "enabled" not in value and "data" not in value:
            return value
        enabled = value.get("enabled", True)
        data = value.get("data", {})
        if not isinstance(enabled, bool):
            msg = "config.enabled must be a boolean"
            raise ValueError(msg)
        if not enabled:
            return {}
        if not isinstance(data, dict):
            msg = "config.data must be a mapping"
            raise ValueError(msg)
        return data

    service: ServiceConfig = Field(default_factory=ServiceConfig)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    probes: ProbesConfig = Field(default_factory=ProbesConfig)
    autoscaling: AutoscalingConfig = Field(default_factory=AutoscalingConfig)
    ingress: IngressConfig = Field(default_factory=IngressConfig)
    mesh: MeshConfig = Field(default_factory=MeshConfig)
    networkPolicy: NetworkPolicyConfig = Field(default_factory=NetworkPolicyConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    supplyChain: SupplyChainConfig = Field(default_factory=SupplyChainConfig)
    ci: CiConfig = Field(default_factory=CiConfig)
    gitops: GitOpsConfig = Field(default_factory=GitOpsConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    terraform: TerraformConfig = Field(default_factory=TerraformConfig)
    ansible: AnsibleConfig = Field(default_factory=AnsibleConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    capstone: CapstoneConfig = Field(default_factory=CapstoneConfig)

    @model_validator(mode="after")
    def validate_ingress_service(self) -> "AppConfig":
        """Ensure enabled Ingress has a Service backend to target."""
        if self.ingress.enabled and not self.service.enabled:
            msg = "service.enabled must be true when ingress.enabled is true"
            raise ValueError(msg)
        return self
