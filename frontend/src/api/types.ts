export interface SourceFamily {
  key: string;
  display_name: string;
  description: string | null;
  filters_by_publication_date: boolean;
}

export interface Source {
  id: number;
  family_key: string;
  name: string;
  family_params: Record<string, unknown>;
  active: boolean;
}

export interface SourceUpdateInput {
  active?: boolean;
  family_params?: Record<string, unknown>;
}

export type RunStatus = "pending" | "running" | "completed" | "completed_with_errors" | "failed" | "cancelled";
export type RunSourceStatus = "pending" | "running" | "completed" | "failed";

export interface Run {
  id: number;
  triggered_by: string;
  status: RunStatus;
  fini: string | null;
  ffin: string | null;
  cancel_requested: boolean;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface RunCreateInput {
  source_ids?: number[];
  fini?: string;
  ffin?: string;
}

export interface RunSource {
  id: number;
  run_id: number;
  source_id: number;
  source_name: string;
  status: RunSourceStatus;
  docs_new: number;
  docs_updated: number;
  docs_errors: number;
  error_message: string | null;
}

export type DocumentReviewStatus = "pending" | "useful" | "not_useful";

export interface Document {
  id: number;
  doc_id: string;
  source_id: number;
  title: string;
  nombre: string;
  tipo: string | null;
  seccion: string | null;
  especialidad: string | null;
  magistrado: string | null;
  detalle: string | null;
  f_public: string | null;
  f_providencia: string | null;
  source_url: string | null;
  storage_bucket: string;
  storage_key: string;
  content_type: string | null;
  file_size_bytes: number | null;
  review_status: DocumentReviewStatus;
  reviewed_at: string | null;
  downloaded_at: string;
  case_document_count?: number | null;
  case_link_id?: number | null;
  case_link_other_source_name?: string | null;
}

export interface PaginatedDocuments {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}

export interface CaseLinkStageDocument {
  id: number;
  title: string;
  f_public: string | null;
  f_providencia: string | null;
}

export interface CaseLinkStage {
  stage_id: number;
  source_id: number;
  source_name: string;
  radicado: string;
  f_public_min: string | null;
  f_public_max: string | null;
  documents: CaseLinkStageDocument[];
}

export interface CaseLink {
  id: number;
  stages: CaseLinkStage[];
}

export interface CaseLinkListItem {
  id: number;
  source_names: string[];
  radicados: string[];
  stage_count: number;
  document_count: number;
  f_public_min: string | null;
  f_public_max: string | null;
}

export interface TipoCount {
  tipo: string;
  count: number;
}

export interface SourceCount {
  id: number;
  name: string;
  count: number;
}

export interface DocumentStats {
  by_tipo: TipoCount[];
  by_source: SourceCount[];
  by_month: number[];
  year: number;
  available_years: number[];
}

export interface DocumentVersion {
  id: number;
  document_id: number;
  nombre: string;
  file_size_bytes: number | null;
  content_type: string | null;
  downloaded_at: string;
  superseded_at: string;
}

export interface TipoSummary {
  tipo: string;
  total_files: number;
  exception_count: number;
}

export type ReorganizeExceptionKind = "missing_entity_folder" | "missing_year_folder";

export interface ReorganizeException {
  tipo: string;
  kind: ReorganizeExceptionKind;
  current_path: string;
  detected_entity: string | null;
  detected_year: number | null;
  mtime_year_hint: number | null;
  proposed_path: string | null;
}

export interface ExtraDepthEntry {
  tipo: string;
  current_path: string;
}

export interface BatchAnalysis {
  root_path: string;
  total_files: number;
  tipos: TipoSummary[];
  exceptions: ReorganizeException[];
  extra_depth: ExtraDepthEntry[];
}

export interface ResolvedMove {
  current_path: string;
  target_path: string;
}

export interface MoveResult {
  current_path: string;
  target_path: string;
  moved: boolean;
  skip_reason: string | null;
}

export interface ApplyResult {
  results: MoveResult[];
}
