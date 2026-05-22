import type { ApiResult, Config, ContextOutput, ExecuteResult, HistoryRecord, Plan, PreviewResult, PromptItem, Provider, ScanJob, ScanResult } from './types';
import { JSON_RULES_EN, JSON_RULES_ZH } from './promptText';

declare global {
  interface Window {
    pywebview?: {
      api: Record<string, (...args: unknown[]) => Promise<unknown>>;
    };
    __foldermindDrop?: (path: string) => void | Promise<void>;
    __foldermindInitialHistory?: HistoryRecord[];
  }
}

const demoScan: ScanResult = {
  root_path: '',
  files: [],
  tree_text: 'FolderMind/\n- choose a folder in the desktop app',
  duplicates: [],
  warnings: [],
  file_count: 0
};

async function call<T>(method: string, ...args: unknown[]): Promise<ApiResult<T>> {
  await waitForDesktopBridge();
  if (window.pywebview?.api?.[method]) {
    return window.pywebview.api[method](...args) as Promise<ApiResult<T>>;
  }
  return fallback<T>(method, args);
}

function waitForDesktopBridge(timeoutMs = 3000): Promise<void> {
  if (window.pywebview?.api) return Promise.resolve();
  if (!isDesktopShell()) return Promise.resolve();
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      window.removeEventListener('pywebviewready', finish);
      resolve();
    };
    window.addEventListener('pywebviewready', finish, { once: true });
    setTimeout(finish, timeoutMs);
  });
}

function isDesktopShell() {
  return window.location.protocol === 'file:' || navigator.userAgent.toLowerCase().includes('pywebview');
}

async function fallback<T>(method: string, args: unknown[]): Promise<ApiResult<T>> {
  if (method === 'load_config') {
    return { ok: true, data: JSON.parse(localStorage.getItem('foldermind.config') || 'null') ?? defaultConfig() } as ApiResult<T>;
  }
  if (method === 'save_config') {
    localStorage.setItem('foldermind.config', JSON.stringify(args[0]));
    return { ok: true } as ApiResult<T>;
  }
  if (method === 'reset_config') {
    const config = defaultConfig();
    localStorage.setItem('foldermind.config', JSON.stringify(config));
    localStorage.removeItem('foldermind.prompts');
    return { ok: true, data: { ...config, api_keys: { anthropic: '', openai: '', custom: '' } } as T };
  }
  if (method === 'load_history') {
    return { ok: true, data: JSON.parse(localStorage.getItem('foldermind.history') || '[]') } as ApiResult<T>;
  }
  if (method === 'save_history') {
    localStorage.setItem('foldermind.history', JSON.stringify(args[0]));
    return { ok: true } as ApiResult<T>;
  }
  if (method === 'clear_history') {
    localStorage.removeItem('foldermind.history');
    return { ok: true } as ApiResult<T>;
  }
  if (method === 'delete_history_records') {
    const ids = new Set(args[0] as string[]);
    const records = JSON.parse(localStorage.getItem('foldermind.history') || '[]') as HistoryRecord[];
    const remaining = records.filter((record) => !ids.has(record.id));
    localStorage.setItem('foldermind.history', JSON.stringify(remaining));
    return { ok: true, data: { deleted: records.length - remaining.length } as T };
  }
  if (method === 'history_info') {
    return { ok: true, data: { path: 'browser-local-storage', folder: 'browser-local-storage' } } as ApiResult<T>;
  }
  if (method === 'open_history_folder') {
    return { ok: false, error: { code: 'BRIDGE_UNAVAILABLE', message: 'Run in the desktop window to open the history folder.' } };
  }
  if (method === 'choose_folder') {
    const chosen = prompt('Folder path');
    return chosen ? ({ ok: true, data: chosen } as ApiResult<T>) : { ok: false, error: { code: 'CANCELLED', message: 'Cancelled' } };
  }
  if (method === 'choose_json_file' || method === 'read_text_file') {
    return { ok: false, error: { code: 'BRIDGE_UNAVAILABLE', message: 'Run in the pywebview desktop window for this feature.' } };
  }
  if (method === 'scan_folder') {
    return { ok: true, data: { ...demoScan, root_path: String(args[0] || '') } } as ApiResult<T>;
  }
  if (method === 'start_scan') {
    return { ok: true, data: { jobId: `browser-${Date.now()}` } as T };
  }
  if (method === 'poll_scan') {
    return { ok: true, data: { jobId: String(args[0]), path: '', count: 0, done: true, result: demoScan } as T };
  }
  if (method === 'cancel_scan') {
    return { ok: true, data: { cancelled: true } as T };
  }
  if (method === 'build_context') {
    const promptItem = args[1] as PromptItem;
    return { ok: true, data: { action: 'copy', text: promptItem.content.replace('{file_list}', demoScan.tree_text), file_count: 0 } } as ApiResult<T>;
  }
  if (method === 'generate_plan') {
    return { ok: true, data: '{"summary":"Browser preview mode","actions":[]}' as T };
  }
  if (method === 'generate_plan_stream') {
    return { ok: false, error: { code: 'BRIDGE_UNAVAILABLE', message: 'Run in the pywebview desktop window for streaming.' } };
  }
  if (method === 'poll_ai_stream') {
    return { ok: false, error: { code: 'BRIDGE_UNAVAILABLE', message: 'Run in the pywebview desktop window for streaming.' } };
  }
  if (method === 'cancel_ai_request') {
    return { ok: true, data: { cancelled: true } as T };
  }
  if (method === 'test_connection') {
    const input = args[0] as { apiKey?: string; customUrl?: string };
    if (!input?.apiKey) return { ok: true, data: { success: false, latencyMs: 0, errorMessage: '请先填写 API Key。' } as T };
    if (input.customUrl === '') return { ok: true, data: { success: false, latencyMs: 0, errorMessage: '请先填写自定义 API 地址。' } as T };
    return { ok: true, data: { success: true, latencyMs: 1 } as T };
  }
  if (method === 'parse_plan') {
    try {
      return { ok: true, data: JSON.parse(String(args[0]).replace(/^```json|```$/g, '')) } as ApiResult<T>;
    } catch (error) {
      return { ok: false, error: { code: 'JSON_PARSE_ERROR', message: String(error) } };
    }
  }
  if (method === 'preview_plan') {
    const plan = args[1] as Plan;
    return {
      ok: true,
      data: {
        before_tree_text: demoScan.tree_text,
        after_tree_text: demoScan.tree_text,
        lines: plan.actions.map((a) => ({ actionId: a.id, description: a.type, hasConflict: false })),
        conflicts: [],
        missing_paths: []
      }
    } as ApiResult<T>;
  }
  if (method === 'execute_plan') {
    const plan = args[1] as Plan;
    return { ok: true, data: { results: plan.actions.map((a) => ({ action_id: a.id, status: 'skipped', message: 'Browser preview mode' })), success_count: 0, skipped_count: plan.actions.length, error_count: 0, undo_available: false } } as ApiResult<T>;
  }
  if (method === 'undo_last') {
    return { ok: false, error: { code: 'UNDO_NOT_AVAILABLE', message: 'Browser preview mode' } };
  }
  if (method === 'list_prompts') {
    return { ok: true, data: defaultPrompts() } as ApiResult<T>;
  }
  if (method === 'save_prompt') {
    const prompts = JSON.parse(localStorage.getItem('foldermind.prompts') || '[]') as PromptItem[];
    const item = args[0] as PromptItem;
    const saved = { ...item, key: item.key || `custom-${Date.now()}`, is_preset: false };
    localStorage.setItem('foldermind.prompts', JSON.stringify([...prompts.filter((p) => p.key !== saved.key), saved]));
    return { ok: true, data: saved } as ApiResult<T>;
  }
  if (method === 'delete_prompt') {
    return { ok: true } as ApiResult<T>;
  }
  return { ok: false, error: { code: 'BRIDGE_UNAVAILABLE', message: 'Run in the pywebview desktop window for this feature.' } };
}

function defaultConfig(): Config {
  return {
    provider: 'anthropic',
    provider_models: { anthropic: 'claude-opus-4-6', openai: 'gpt-4o', custom: '' },
    provider_endpoint_urls: {
      anthropic: 'https://api.anthropic.com/v1/messages',
      openai: 'https://api.openai.com/v1/chat/completions',
      custom: ''
    },
    custom_models: { anthropic: ['claude-opus-4-6', 'claude-sonnet-4-6'], openai: ['gpt-4o'], custom: [] },
    custom_endpoint_url: '',
    conflict_policy: 'ask',
    exclude_rules: [],
    language: 'zh-CN',
    theme: 'dark',
    ai_timeout_seconds: 60,
    ai_context_file_limit: 1000
  };
}

function defaultPrompts(): PromptItem[] {
  const makePrompt = (key: string, nameZh: string, nameEn: string, taskZh: string, taskEn: string): PromptItem => ({
    key,
    name: nameZh,
    name_zh: nameZh,
    name_en: nameEn,
    content: `${taskZh}\n\n[文件列表]\n{file_list}\n\n${JSON_RULES_ZH}`,
    content_zh: `${taskZh}\n\n[文件列表]\n{file_list}\n\n${JSON_RULES_ZH}`,
    content_en: `${taskEn}\n\n[File list]\n{file_list}\n\n${JSON_RULES_EN}`,
    is_preset: true
  });
  return [
    makePrompt('organize', '整理归类', 'Organize by Category', '请按用途、主题和类型整理这些文件。', 'Organize these files by purpose, topic, and type.'),
    makePrompt('study', '学习计划', 'Study Plan', '请识别学习资料主题，按课程、资料类型和学习优先级整理。', 'Organize learning materials by course, topic, material type, and study priority.'),
    makePrompt('archive', '归档清理', 'Archive Cleanup', '请找出适合归档的旧文件和低频文件，近期文件和不确定文件保持原位。', 'Find old or low-frequency files suitable for archiving. Keep recent or uncertain files in place.'),
    makePrompt('project', '项目整理', 'Project Structure', '请识别代码、文档、素材、配置、输出物和临时文件，按项目结构整理。', 'Identify code, documents, assets, configuration, outputs, and temporary files. Organize them into project-style folders.'),
    makePrompt('rename', '重命名规范', 'Rename Rules', '请找出命名混乱但内容含义明确的文件，提出清晰、可读、低风险的 rename 方案。已经清晰的文件名不要改。', 'Find files with messy but understandable names and propose clear, readable, low-risk rename actions. Do not rename files that are already clear.')
  ];
}

export const api = {
  chooseFolder: () => call<string>('choose_folder'),
  chooseJsonFile: () => call<{ path: string; text: string }>('choose_json_file'),
  readTextFile: (path: string) => call<{ path: string; text: string }>('read_text_file', path),
  scanFolder: (path: string) => call<ScanResult>('scan_folder', path),
  startScan: (path: string) => call<{ jobId: string }>('start_scan', path),
  pollScan: (jobId: string) => call<ScanJob>('poll_scan', jobId),
  cancelScan: (jobId: string) => call<{ cancelled: boolean }>('cancel_scan', jobId),
  buildContext: (rootPath: string, prompt: PromptItem, extraInstruction: string) => call<ContextOutput>('build_context', rootPath, prompt, extraInstruction),
  generatePlan: (input: Record<string, unknown>) => call<string>('generate_plan', input),
  generatePlanStream: (input: Record<string, unknown>) => call<{ requestId: string }>('generate_plan_stream', input),
  pollAiStream: (requestId: string) => call<{ content: string; done: boolean; error?: string; cancelled?: boolean }>('poll_ai_stream', requestId),
  cancelAiRequest: (requestId: string) => call<{ cancelled: boolean }>('cancel_ai_request', requestId),
  testConnection: (input: Record<string, unknown>) => call<{ success: boolean; latencyMs: number; errorMessage?: string }>('test_connection', input),
  parsePlan: (json: string) => call<Plan>('parse_plan', json),
  previewPlan: (rootPath: string, plan: Plan) => call<PreviewResult>('preview_plan', rootPath, plan),
  executePlan: (rootPath: string, plan: Plan, conflictPolicy: string) => call<ExecuteResult>('execute_plan', rootPath, plan, conflictPolicy),
  undoLast: () => call<unknown>('undo_last'),
  loadConfig: () => call<Config>('load_config'),
  saveConfig: (config: Config) => call<void>('save_config', config),
  resetConfig: () => call<Config & { api_keys?: Record<Provider, string> }>('reset_config'),
  loadHistory: () => call<HistoryRecord[]>('load_history'),
  saveHistory: (records: HistoryRecord[]) => call<void>('save_history', records),
  clearHistory: () => call<void>('clear_history'),
  deleteHistoryRecords: (recordIds: string[]) => call<{ deleted: number }>('delete_history_records', recordIds),
  historyInfo: () => call<{ path: string; folder: string }>('history_info'),
  openHistoryFolder: () => call<string>('open_history_folder'),
  listPrompts: () => call<PromptItem[]>('list_prompts'),
  savePrompt: (prompt: PromptItem) => call<PromptItem>('save_prompt', prompt),
  deletePrompt: (key: string) => call<void>('delete_prompt', key)
};
