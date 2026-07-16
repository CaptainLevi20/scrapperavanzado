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

export type RunStatus = "pending" | "running" | "completed";
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
  status: RunSourceStatus;
  docs_new: number;
  docs_errors: number;
  error_message: string | null;
}

export type DocumentReviewStatus = "pending" | "useful" | "not_useful";

export interface Document {
  id: number;
  doc_id: string;
  source_id: number;
  title: string;
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
}

export interface PaginatedDocuments {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}

export interface FamilyCount {
  key: string;
  display_name: string;
  count: number;
}

export interface TipoCount {
  tipo: string;
  count: number;
}

export interface DocumentStats {
  by_family: FamilyCount[];
  by_tipo: TipoCount[];
  by_month: number[];
  year: number;
  available_years: number[];
}
