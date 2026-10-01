// Mirrors the backend contract (schemas/*.schema.json). Only fields the UI reads are typed.

export type Severity = "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export type CmpVerdict = "DIRECT" | "CONDITIONAL" | "NOT" | "BLOCKED_BY_INTEGRITY";
export type ClaimVerdict = "SUPPORTED" | "CONDITIONAL" | "UNSUPPORTED" | "BLOCKED";
export type DimStatus = "PASS" | "CONDITIONAL" | "FAIL" | "N/A";

export interface SourceInfo {
  kind: "live" | "snapshot" | "fixture";
  base_url: string;
  fetched_at: string;
  snapshot_id: string | null;
  manifest_sha256: string | null;
  fallback_reason: string | null;
}

export interface ResourceRef {
  resource_type: string;
  resource_id: string;
  fhir_path: string | null;
  display: string | null;
}

export interface FindingCompact {
  id: string;
  rule_id: string;
  title: string;
  category: string;
  severity: Severity;
  confidence: number;
  confidence_label: string;
  scope: "oah-ig" | "third-party";
  resource: ResourceRef;
  summary: string;
  related_count: number;
  has_lineage: boolean;
}

export interface ObservedValue {
  label: string;
  value: number | string | null;
  unit: string | null;
  fhir_path: string | null;
}

export interface Finding extends Omit<FindingCompact, "related_count" | "has_lineage"> {
  rule_version: string;
  related_resources: ResourceRef[];
  evidence: {
    observed: ObservedValue[];
    constraint: string;
    expected: string;
    measures: Record<string, unknown>;
    raw_excerpt: unknown;
  };
  interpretation: string;
  root_cause: string;
  hypotheses: string[];
  remediation: string;
  lineage: { source: string; locator: string; raw_row: string; matches: Record<string, boolean>; statement: string } | null;
  provenance: {
    source: SourceInfo;
    resource_sha256: string | null;
    resource_version_id: string | null;
    resource_last_updated: string | null;
    rules_version: string;
    knowledge_version: string;
    ig_source: string;
  } | null;
}

export interface ImpactNode {
  id: string;
  type: "library" | "profile" | "series" | "comparison" | "claim";
  label: string;
  depth: number;
  via: string | null;
  attrs: Record<string, unknown>;
}

export interface Impact {
  start: string[];
  reachable: ImpactNode[];
  counts: Record<string, number>;
  edges: [string, string, string][];
  statement: string;
}

export interface OperationOutcome {
  issue: { severity: string; code: string; diagnostics?: string }[];
}

/** A finding's own evidence written out as arithmetic (backend `audit/calculation.py`); every result is a rule measure. */
export interface CalcStep {
  label: string;
  expression: string;
  result: string;
  value: number | null;
  measure: string | null;
  operation: string | null;
  operands: number[];
}

export interface Calculation {
  steps: CalcStep[];
  result: string;
  check: { constraint: string; evaluated: string; holds: boolean } | null;
}

export interface FindingDetail {
  finding: Finding;
  calculation: Calculation | null;
  raw: Record<string, unknown> | null;
  server_validation: OperationOutcome | null;
  impact: Impact;
  explanation: { text: string; method: string; fallback_reason: string | null };
  same_resource: FindingCompact[];
  rule: RuleSpec;
  record: {
    indicator_key: string | null;
    indicator: string | null;
    canonical_unit: string | null;
    hard: { min?: number; max?: number; rationale: string } | null;
    typical: { min?: number; max?: number; rationale: string } | null;
    year: number | null;
    location: string | null;
    stats: { stat: string; value: number | null; unit: string | null }[];
    value: { value: number | null; code: string | null } | null;
  } | null;
}

export interface RuleSpec {
  id: string;
  version: string;
  title: string;
  category: string;
  severity: string;
  confidence: string;
  applies_to: string;
  constraint: string;
  rationale: string;
  references: string[];
  findings?: number;
}

export interface Summary {
  resources_by_type: Record<string, number>;
  resources_by_scope: Record<string, number>;
  observations_checked: number;
  findings_total: number;
  findings_by_severity: Record<Severity, number>;
  findings_by_rule: Record<string, number>;
  findings_by_scope: Record<string, number>;
  affected_resources: number;
  oah_observations: number;
  oah_observations_with_blocking: number;
  integrity_pass_rate: number | null;
  server_validation: Record<string, number>;
  anchor: { id: string; present: boolean; rules_fired: string[]; values?: Record<string, number>; unit?: string };
}

export interface Overview {
  run_id: string;
  created_at: string;
  source: SourceInfo;
  summary: Summary;
  rules_version: string;
  knowledge_version: string;
  ig_commit: string;
  findings_by_category: Record<string, number>;
  hero_finding: FindingCompact | null;
  top_findings: FindingCompact[];
  blocking_by_site: Record<string, number>;
  comparisons: { id: string; a: string; b: string; verdict: CmpVerdict }[];
  claims: { id: string; text: string; verdict: ClaimVerdict }[];
  graph: Record<string, number>;
}

export interface Status {
  version: string;
  has_run: boolean;
  run_id: string | null;
  source: SourceInfo | null;
  scan: {
    running: boolean;
    mode: string | null;
    started_at: string | null;
    error: string | null;
    /** Real stages of the scan, reported by the backend as they happen. */
    stages?: { id: string; label: string; state: "running" | "done" | "failed"; detail: string | null; at: string }[];
  } | null;
  mode: string | null;
  fhir_base: string | null;
  llm: string;
  llm_name: string | null;
  llm_user_keys: boolean;
  rule_count: number;
  snapshots: { snapshot_id: string; fetched_at: string; manifest_sha256: string; resource_counts: Record<string, number>; server_validations: number }[];
  /** IG source files that lineage reads and that are not on this computer (a repository published without the data). */
  ig_files_missing?: string[];
}

export interface Cohort {
  group_id: string;
  sex: string | null;
  age_low: number | null;
  age_high: number | null;
  label: string;
}

export interface Descriptor {
  observation_id: string;
  statistic: string | null;
  label: string;
  indicator_key: string | null;
  measure_label: string | null;
  medium: string;
  unit: string | null;
  value: number | null;
  location_id: string | null;
  location_name: string | null;
  cohort: Cohort | null;
  period: { start: string | null; end: string | null } | null;
  aggregation: string;
  method: string | null;
}

export interface Dimension {
  dimension: string;
  rule_id: string;
  status: DimStatus;
  reason: string;
  details: Record<string, unknown>;
}

export interface Comparison {
  id: string;
  a: Descriptor;
  b: Descriptor;
  verdict: CmpVerdict;
  dimensions: Dimension[];
  blocking_findings: string[];
  transformations: string[];
  supported_alternatives: string[];
  summary: string;
}

export interface StructuredClaim {
  type: "COMPARE_HIGHER" | "TREND_INCREASE" | "EXCEEDS_THRESHOLD" | "ASSOCIATION" | "CAUSAL";
  subject?: string | null;
  object?: string | null;
  statistic?: string | null;
  location_id?: string | null;
  indicator_key?: string | null;
  outcome_indicator_key?: string | null;
  threshold_id?: string | null;
  year_from?: number | null;
  year_to?: number | null;
  text?: string | null;
}

export interface ClaimResult {
  id: string;
  claim: StructuredClaim;
  claim_rendered: string;
  verdict: ClaimVerdict;
  reasons: string[];
  rule_trace: { step: string; check: string; outcome: unknown }[];
  blocking_findings: string[];
  comparison: Comparison | null;
  statistics: Record<string, unknown>;
  safe_alternatives: string[];
  inputs: string[];
  /** The verdict restated per rung: Observation, Description, Comparison, Association, Causation. */
  ladder: ClaimRung[];
  supported_up_to: string | null;
}

export interface ClaimRung {
  level: "observation" | "description" | "comparison" | "association" | "causation";
  label: string;
  status: "supported" | "conditional" | "unsupported" | "blocked" | "not_claimed";
  why: string;
  claimed: boolean;
}

export interface ParseResult {
  intent: Record<string, unknown>;
  claim: StructuredClaim | null;
  method: string;
  understood: string[];
  problems: string[];
}

export interface ObservationItem {
  id: string;
  indicator_key: string | null;
  indicator: string | null;
  medium: string;
  location_id: string | null;
  location: string | null;
  cohort: string | null;
  year: number | null;
  date: string | null;
  statistics: string[];
  value: number | null;
  unit: string | null;
  blocking: boolean;
  findings: number;
  scope: string;
  period: { start: string | null; end: string | null } | null;
  method: string | null;
  /** Every statistic exactly as published. */
  stats: Record<string, number | null>;
  worst: Severity | null;
  worst_finding: string | null;
}

export interface LocationItem {
  id: string;
  name: string | null;
  latitude: number | null;
  longitude: number | null;
  part_of: string | null;
  scope: string;
  observations: number;
  with_problems: number;
  measures: number;
  years: [number, number] | null;
}

export interface SupportRow {
  library_id: string;
  library_title: string;
  indicator_key: string;
  indicator_label: string;
  medium: string;
  observations: number;
  years: number[];
  blocked: number;
  warned: number;
  status: "USABLE" | "USABLE_WITH_CAVEATS" | "PARTLY_USABLE" | "NOT_USABLE";
  can_support: string[];
  cannot_support: string[];
  rules: string[];
}

export interface Knowledge {
  version: string;
  ig_commit: string;
  indicators: Record<string, { label: string; medium: string; kind: string; unit: string }>;
  thresholds: Record<string, { id: string; indicator: string; value: number; unit: string; source: string; matrix: string; averaging: string }>;
  plausibility: { indicators: Record<string, { hard?: { min?: number; max?: number; rationale: string }; typical?: { min?: number; max?: number; rationale: string } }> };
}

/** A user's own model settings. Kept in their browser only and sent with their own requests. */
export interface LlmConfig {
  provider: string;
  model: string;
  api_key?: string;
  base_url?: string;
}

export interface LlmPreset {
  id: string;
  label: string;
  kind: "ollama" | "openai-compatible" | "anthropic";
  base_url: string | null;
  default_model: string;
  needs_key: boolean;
  free_tier: boolean;
  key_url: string | null;
  note: string;
  models: string[];
}

export interface LlmProviders {
  allow_user_keys: boolean;
  allow_custom_url: boolean;
  server_default: string | null;
  providers: LlmPreset[];
}

export interface LlmTest {
  ok: boolean;
  name: string | null;
  error?: string;
  latency_ms?: number;
  reply?: string;
  models: string[];
}

/** What-if lab: the rules on an edited copy of one published observation (nothing is stored). */
export interface LabCheck {
  rule_id: string;
  title: string;
  fired: boolean;
  was_fired: boolean;
  severity: Severity | null;
  summary: string | null;
}

export interface LabResult {
  observation_id: string;
  values: Record<string, number>;
  published_values: Record<string, number>;
  changed: boolean;
  checks: LabCheck[];
  findings_total: number;
  worst: Severity | null;
  published_findings_total: number;
  record: FindingDetail["record"];
  published_record: FindingDetail["record"];
}

export interface LabValidation {
  outcome: OperationOutcome;
  http_status: number;
  server: string;
  checked_at: string;
  note: string;
}

/** Checking data a user brings (processed in memory for one request). */
export interface CheckResult {
  resources: {
    key: string;
    resource_type: string;
    id: string;
    display: string | null;
    replaces_published: boolean;
    identical_to_published: boolean;
    findings: number;
    worst: Severity | null;
  }[];
  findings: (Omit<Finding, "provenance" | "lineage"> & { resource: ResourceRef & { key: string } })[];
  summary: {
    checked: number;
    with_findings: number;
    findings_total: number;
    by_severity: Record<Severity, number>;
    replaced_published: number;
    identical_to_published: number;
    context: SourceInfo;
  };
  notes: string[];
}
