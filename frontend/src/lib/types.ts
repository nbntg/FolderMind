export type ApiResult<T> = {
  ok: boolean;
  data?: T;
  error?: { code: string; message: string; details?: unknown };
};

export type FileEntry = {
  relative_path: string;
  absolute_path: string;
  name: string;
  size: number;
  modified_time: string;
  is_dir: boolean;
};

export type ScanResult = {
  root_path: string;
  files: FileEntry[];
  tree_text: string;
  duplicates: { hash: string; files: FileEntry[] }[];
  warnings: string[];
  file_count: number;
};

export type ScanJob = {
  jobId: string;
  path: string;
  count: number;
  currentPath?: string;
  done: boolean;
  cancelled?: boolean;
  error?: string;
  result?: ScanResult;
};

export type Action =
  | { id: number; type: 'create_dir'; path: string; reason?: string }
  | { id: number; type: 'move'; from: string; to: string; reason?: string }
  | { id: number; type: 'rename'; path: string; from: string; to: string; reason?: string }
  | { id: number; type: 'delete_dir'; path: string; reason?: string };

export type Plan = {
  summary?: string;
  actions: Action[];
};

export type PreviewResult = {
  before_tree_text: string;
  after_tree_text: string;
  lines: { actionId: number; description: string; hasConflict: boolean }[];
  conflicts: unknown[];
  missing_paths: string[];
};

export type ExecuteResult = {
  results: { action_id: number; status: string; message: string; final_path?: string }[];
  success_count: number;
  skipped_count: number;
  error_count: number;
  undo_available: boolean;
};

export type HistoryRecord = {
  id: string;
  workflowId: string;
  kind: 'scan' | 'import' | 'preview' | 'execute' | 'undo';
  path: string;
  at: string;
  title: string;
  status: 'success' | 'warning' | 'error';
  message?: string;
  fileCount?: number;
  actionCount?: number;
  successCount?: number;
  skippedCount?: number;
  errorCount?: number;
  conflictCount?: number;
  missingCount?: number;
  jsonText?: string;
  details?: string[];
};

export type Provider = 'anthropic' | 'openai' | 'custom';
export type Language = 'zh-CN' | 'en';
export type Theme = 'dark' | 'light';

export type PromptItem = {
  key: string;
  name: string;
  content: string;
  name_zh?: string;
  name_en?: string;
  content_zh?: string;
  content_en?: string;
  desc_zh?: string;
  desc_en?: string;
  is_preset: boolean;
  is_deleted?: boolean;
};

export type Config = {
  provider: Provider;
  provider_models: Record<Provider, string>;
  provider_endpoint_urls: Record<Provider, string>;
  custom_models: Record<Provider, string[]>;
  custom_endpoint_url: string;
  conflict_policy: 'ask' | 'auto_rename' | 'skip';
  exclude_rules: string[];
  language: Language;
  theme: Theme;
  ai_timeout_seconds: number;
  ai_context_file_limit: number;
  apiKey?: string;
  api_keys?: Record<Provider, string>;
};

export type ContextOutput = {
  action: 'copy' | 'export';
  text: string;
  file_count?: number;
  export_path?: string;
};

export type AiMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  status?: 'pending' | 'done' | 'error' | 'cancelled';
};
