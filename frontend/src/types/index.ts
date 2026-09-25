export interface ApiResponse {
  status: ResponseStatus;
  request_id: string | null;
  message: string | null;
  sql: string | null;
  operation: string | null;
  table?: string | null;
  columns: string[] | null;

  rows: Record<string, any>[] | null;
  row_count: number | null;
  question: string | null;
  options: string[] | null;
  confirmation_token: string | null;
  estimated_affected_rows: number | null;
  validation: ValidationSummary | null;
  visualization: VisualizationConfig | null;
  explanation: string | null;
  transcript?: string | null;
  audit_id: string | null;
}

export type ResponseStatus =
  | 'SUCCESS'
  | 'CLARIFICATION_REQUIRED'
  | 'CONFIRMATION_REQUIRED'
  | 'FAILED'
  | 'VALIDATION_FAILED'
  | 'EXECUTION_FAILED'
  | 'SECURITY_VIOLATION'
  | 'RETRY_REQUIRED'
  | 'INVALID_CONFIRMATION'
  | 'CONFIRMATION_EXPIRED'
  | 'INVALID_REQUEST'
  | 'ERROR';

export interface ValidationSummary {
  valid: boolean;
  issues: string[];
  operation: string;
  tables: string[];
  columns: string[];
}

export interface VisualizationConfig {
  type: 'bar' | 'line' | 'pie' | 'kpi' | 'table' | string;
  x_axis?: string;
  y_axis?: string;
  title?: string;
  metric?: string;
  value?: number;
  category?: string;
}

export interface QueryRequest {
  message: string;
  conversation_id?: string;
  user_role?: string;
}

export interface ClarifyRequest {
  request_id: string;
  selection: string;
}

export interface ConfirmRequest {
  confirmation_token: string;
}

export interface ColumnInfo {
  name: string;
  type: string;
  nullable?: boolean;
  primary_key?: boolean;
}

export interface ForeignKeyInfo {
  column: string;
  foreign_table: string;
  foreign_column: string;
}

export interface TableSchema {
  columns: ColumnInfo[];
  foreign_keys?: ForeignKeyInfo[];
  indexes?: any[];
}

export interface HistoryItem {
  message: string;
  sql: string;
  timestamp: string;
}

export interface HistoryResponse {
  conversation_id: string;
  items: HistoryItem[];
}
