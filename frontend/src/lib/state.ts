import { writable } from 'svelte/store';
import type { AiMessage, Config, ContextOutput, ExecuteResult, HistoryRecord, Language, Plan, PreviewResult, PromptItem, ScanResult, Theme } from './types';

export const language = writable<Language>('zh-CN');
export const theme = writable<Theme>('dark');

export const rootPath = writable('');
export const scanResult = writable<ScanResult | null>(null);
export const prompts = writable<PromptItem[]>([]);
export const selectedPrompt = writable<PromptItem | null>(null);
export const contextOutput = writable<ContextOutput | null>(null);
export const jsonText = writable('');
export const activePlan = writable<Plan | null>(null);
export const previewResult = writable<PreviewResult | null>(null);
export const executeResult = writable<ExecuteResult | null>(null);
export const appConfig = writable<Config | null>(null);
export const statusMessage = writable('');
export const operation = writable<'idle' | 'scanning' | 'copying' | 'exporting' | 'previewing' | 'executing' | 'undoing' | 'ai'>('idle');
export const historyRecords = writable<HistoryRecord[]>([]);
export const currentWorkflowId = writable(newWorkflowId());
export const aiMessages = writable<AiMessage[]>([]);
export const aiOpen = writable(false);
export const aiRunning = writable(false);
export const aiRequestId = writable('');
export const aiPosition = writable({ x: 0, y: 0 });

export function newWorkflowId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
