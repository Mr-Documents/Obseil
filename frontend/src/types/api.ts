/**
 * Types mirroring the Obseil REST contract.
 *
 * Kept hand-written rather than generated: the surface is small, and an
 * explicit file documents the contract for readers who never run the API.
 * When a field is added server-side it must be added here too — that is the
 * point, and TypeScript will tell you where it matters.
 */

// --- Errors -----------------------------------------------------------------
export interface ApiErrorField {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: { fields?: ApiErrorField[] } & Record<string, unknown>;
    request_id: string;
  };
}

// --- Pagination -------------------------------------------------------------
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// --- Auth -------------------------------------------------------------------
export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthResponse {
  user: User;
  tokens: TokenPair;
}

export interface RegisterPayload {
  email: string;
  full_name: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

// --- Projects ---------------------------------------------------------------
export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSummary extends Project {
  dataset_count: number;
  analysis_count: number;
  latest_quality_score: number | null;
  last_analysed_at: string | null;
}

export interface ProjectCreatePayload {
  name: string;
  description?: string | null;
}

export type ProjectUpdatePayload = Partial<ProjectCreatePayload>;

// --- Profiling --------------------------------------------------------------
export type ColumnType =
  'numeric' | 'integer' | 'boolean' | 'datetime' | 'categorical' | 'text' | 'empty';

export interface ValueCount {
  value: string;
  count: number;
  percentage: number;
}

export interface NumericStatistics {
  mean: number | null;
  median: number | null;
  std: number | null;
  minimum: number | null;
  maximum: number | null;
  q1: number | null;
  q3: number | null;
  iqr: number | null;
  skewness: number | null;
  zero_count: number;
  negative_count: number;
}

export interface DatetimeStatistics {
  earliest: string | null;
  latest: string | null;
  range_days: number | null;
}

export interface TextStatistics {
  min_length: number | null;
  max_length: number | null;
  mean_length: number | null;
  empty_string_count: number;
  whitespace_padded_count: number;
}

export interface ColumnProfile {
  name: string;
  position: number;
  dtype: string;
  inferred_type: ColumnType;
  count: number;
  missing_count: number;
  missing_percentage: number;
  unique_count: number;
  unique_percentage: number;
  is_constant: boolean;
  is_unique: boolean;
  is_numeric_like: boolean;
  memory_bytes: number;
  numeric: NumericStatistics | null;
  datetime: DatetimeStatistics | null;
  text: TextStatistics | null;
  top_values: ValueCount[];
}

// --- Datasets ---------------------------------------------------------------
export type DatasetStatus = 'uploaded' | 'analyzing' | 'ready' | 'failed';
export type AnalysisStatus = 'running' | 'completed' | 'failed';

export interface AnalysisSummary {
  id: string;
  dataset_id: string;
  project_id: string;
  status: AnalysisStatus;
  error_message: string | null;
  row_count: number;
  column_count: number;
  missing_cell_count: number;
  missing_percentage: number;
  duplicate_row_count: number;
  duplicate_row_percentage: number;
  quality_score: number | null;
  quality_grade: string | null;
  finding_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  anomaly_count: number;
  anomaly_rate: number;
  ml_skipped_reason: string | null;
  duration_ms: number | null;
  completed_at: string | null;
  created_at: string;
}

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  original_filename: string;
  file_format: string;
  size_bytes: number;
  checksum_sha256: string;
  row_count: number | null;
  column_count: number | null;
  status: DatasetStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  latest_analysis: AnalysisSummary | null;
}

export interface DatasetStatistics {
  dataset_id: string;
  analysis_id: string;
  analysed_at: string | null;
  row_count: number;
  column_count: number;
  total_cells: number;
  missing_cells: number;
  missing_percentage: number;
  duplicate_row_count: number;
  duplicate_row_percentage: number;
  memory_bytes: number;
  sampled: boolean;
  source_rows: number | null;
  notes: string[];
  columns: ColumnProfile[];
}

export interface DatasetPreviewRow {
  index: number;
  values: Record<string, string | null>;
}

export interface DatasetPreview {
  columns: string[];
  rows: DatasetPreviewRow[];
  total_rows: number;
  offset: number;
  limit: number;
}

// --- Findings ---------------------------------------------------------------
export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type FindingStatus = 'open' | 'reviewed' | 'ignored';
export type FindingCategory = 'rule' | 'anomaly';
export type FeedbackVerdict = 'valid_issue' | 'false_positive';

export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low'];

export interface FindingFeedback {
  verdict: FeedbackVerdict;
  note: string | null;
  created_at: string;
}

export interface Finding {
  id: string;
  analysis_id: string;
  dataset_id: string;
  type: string;
  category: FindingCategory;
  severity: Severity;
  title: string;
  description: string;
  impact: string;
  recommendation: string;
  detection_method: string;
  detection_method_label: string;
  column_name: string | null;
  columns: string[] | null;
  affected_rows: number | null;
  affected_percentage: number | null;
  details: Record<string, unknown> | null;
  sample_row_indices: number[] | null;
  status: FindingStatus;
  created_at: string;
  feedback: FindingFeedback | null;
}

export interface FindingSummary {
  analysis_id: string;
  total: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  open_count: number;
  reviewed_count: number;
  ignored_count: number;
  false_positive_count: number;
}

export interface FindingUpdatePayload {
  status?: FindingStatus;
  verdict?: FeedbackVerdict;
  note?: string | null;
}

export interface FindingFilters {
  severity?: Severity[];
  type?: string[];
  status?: FindingStatus[];
  category?: FindingCategory[];
  search?: string;
  limit?: number;
  offset?: number;
}

// --- Quality score ----------------------------------------------------------
export type QualityGrade = 'excellent' | 'good' | 'needs_attention' | 'poor' | 'critical';

export type QualityDimensionName =
  'completeness' | 'uniqueness' | 'validity' | 'consistency' | 'distribution' | 'anomaly';

export interface DimensionScore {
  dimension: QualityDimensionName;
  label: string;
  penalty: number;
  raw_penalty: number;
  cap: number;
  capped: boolean;
  finding_count: number;
}

export interface ScoreContribution {
  finding_type: string;
  severity: Severity;
  column: string | null;
  penalty: number;
  affected_percentage: number | null;
}

export interface QualityScore {
  analysis_id: string;
  dataset_id: string;
  analysed_at: string | null;
  score: number;
  grade: QualityGrade;
  grade_label: string;
  summary: string;
  total_penalty: number;
  dimensions: DimensionScore[];
  top_contributors: ScoreContribution[];
  methodology: string;
}

// --- Anomalies --------------------------------------------------------------
export interface AnomalyContributor {
  feature: string;
  value: number | null;
  deviation_iqr: number;
}

export interface Anomaly {
  id: string;
  analysis_id: string;
  dataset_id: string;
  row_index: number;
  rank: number;
  raw_score: number;
  anomaly_score: number;
  feature_values: Record<string, number | null> | null;
  top_contributors: AnomalyContributor[] | null;
}

export interface AnomalyOverview {
  analysis_id: string;
  ran: boolean;
  skipped_reason: string | null;
  algorithm: string | null;
  features: string[];
  parameters: Record<string, unknown>;
  rows_scored: number;
  anomaly_count: number;
  anomaly_rate: number;
  method_note: string;
}

// --- History & comparison ---------------------------------------------------
export type MetricPolarity = 'higher_is_better' | 'lower_is_better' | 'neutral';
export type ComparisonDirection = 'improved' | 'regressed' | 'unchanged' | 'changed';

export interface MetricComparison {
  key: string;
  label: string;
  baseline: number | null;
  current: number | null;
  delta: number | null;
  direction: ComparisonDirection;
  polarity: MetricPolarity;
  unit: string | null;
}

export interface FindingTypeChange {
  type: string;
  baseline_count: number;
  current_count: number;
  status: 'resolved' | 'new' | 'persisting';
}

export interface AnalysisComparison {
  baseline_id: string;
  current_id: string;
  baseline_at: string;
  current_at: string;
  baseline_score: number | null;
  current_score: number | null;
  score_delta: number | null;
  headline: string;
  metrics: MetricComparison[];
  dimensions: MetricComparison[];
  finding_types: FindingTypeChange[];
  resolved_types: string[];
  new_types: string[];
}

export interface HistoryEntry extends AnalysisSummary {
  dataset_name: string;
  dataset_row_count: number | null;
  version: number;
}

export interface TrendPoint {
  analysis_id: string;
  score: number | null;
  at: string | null;
  finding_count: number;
  dataset_name: string;
}
