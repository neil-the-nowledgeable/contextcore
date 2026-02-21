/**
 * Core type definitions for the ContextCore VSCode extension.
 * These types match the ProjectContext CRD schema and canonical enums
 * from contracts/types.py.
 */

// ---------------------------------------------------------------------------
// Canonical enums (mirrored from contracts/types.py)
// ---------------------------------------------------------------------------

export type TaskStatus =
  | 'backlog' | 'todo' | 'in_progress' | 'in_review'
  | 'blocked' | 'done' | 'cancelled';

export type TaskType =
  | 'epic' | 'story' | 'task' | 'subtask'
  | 'bug' | 'spike' | 'incident';

export type HandoffStatus =
  | 'pending' | 'accepted' | 'in_progress'
  | 'completed' | 'failed' | 'timeout';

export type InsightType = 'decision' | 'recommendation' | 'blocker' | 'discovery';

export type AgentType = 'code_assistant' | 'orchestrator' | 'specialist' | 'automation';

export type QuestionStatus = 'open' | 'answered' | 'deferred';

export type BusinessValue =
  | 'revenue-primary' | 'revenue-secondary' | 'cost-reduction'
  | 'compliance' | 'enabler' | 'internal';

export type RiskType =
  | 'security' | 'compliance' | 'data-integrity'
  | 'availability' | 'financial' | 'reputational';

export type DashboardPlacement = 'featured' | 'standard' | 'archived';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export type ArtifactType =
  // Observability
  | 'dashboard' | 'prometheus_rule' | 'loki_rule' | 'slo_definition'
  | 'service_monitor' | 'notification_policy' | 'runbook' | 'alert_template'
  // Onboarding
  | 'capability_index' | 'agent_card' | 'mcp_tools' | 'onboarding_metadata'
  // Source
  | 'dockerfile' | 'python_requirements' | 'protobuf_schema'
  | 'editorconfig' | 'ci_workflow'
  // Integrity
  | 'provenance' | 'ingestion-traceability';

// ---------------------------------------------------------------------------
// Existing types
// ---------------------------------------------------------------------------

export type Criticality = 'critical' | 'high' | 'medium' | 'low';

export type Priority = 'P1' | 'P2' | 'P3' | 'P4';

export interface ProjectMetadata {
  name: string;
  namespace: string;
}

export interface ProjectInfo {
  id: string;
  epic?: string;
  name?: string;
}

export interface BusinessContext {
  criticality?: Criticality;
  value?: string;
  owner?: string;
  costCenter?: string;
}

export interface Requirements {
  availability?: string;
  latencyP99?: string;
  latencyP50?: string;
  throughput?: string;
  errorBudget?: string;
  targets?: SloTarget[];
  description?: string;
}

export interface SloTarget {
  metric: string;
  threshold: string;
}

export interface Risk {
  id?: string;
  title?: string;
  type: RiskType | string;
  priority: Priority;
  description: string;
  scope?: string[];
  severity?: string;
  component?: string;
  mitigation?: string;
  status?: string;
}

export interface Target {
  kind: string;
  name: string;
  namespace?: string;
}

export interface ObservabilitySpec {
  traceSampling?: number;
  metricsInterval?: string;
  logLevel?: LogLevel;
  dashboardPlacement?: DashboardPlacement;
  alertChannels?: string[];
  runbook?: string;
}

export interface Design {
  adr?: string;
  doc?: string;
  apiContract?: string;
  agentProtocol?: string;
  otelGenaiMigration?: string;
  otelGenaiGapAnalysis?: string;
  expansionPacks?: string;
  namingConvention?: string;
  dependencyManifest?: string;
  diagrams?: string;
}

export interface ExpansionPackage {
  name: string;
  animal: string;
  anishinaabe?: string;
  purpose: string;
  status: string;
  dependsOn?: string[];
}

export interface ProjectContextSpec {
  project?: ProjectInfo;
  business?: BusinessContext;
  requirements?: Requirements;
  risks?: Risk[];
  targets?: Target[];
  design?: Design;
  observability?: ObservabilitySpec;
  ecosystem?: {
    packages?: ExpansionPackage[];
  };
}

export interface ProjectContext {
  metadata: ProjectMetadata;
  spec: ProjectContextSpec;
  projectId?: string;
  criticality?: string;
  owner?: string;
  risks?: Risk[];
  requirements?: Requirements;
  risk?: {
    scope?: string[];
  };
}

export interface ContextCoreConfig {
  refreshInterval: number;
  kubeconfig?: string;
  kubeconfigPath?: string;
  namespace: string;
  showInlineHints: boolean;
  grafanaUrl: string;
}
