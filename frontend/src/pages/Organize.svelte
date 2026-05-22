<script lang="ts">
  import { Clipboard, FileDown, FolderOpen, Moon, Play, Plus, RotateCcw, Search, Sun, Upload, Wand2, X } from 'lucide-svelte';
  import { get } from 'svelte/store';
  import { api } from '../lib/api';
  import { formatT, t } from '../lib/i18n';
  import { createCustomPromptDraft, localizedPrompt, promptContent, promptName } from '../lib/promptText';
  import {
    activePlan,
    aiMessages,
    aiOpen,
    aiRequestId,
    aiRunning,
    appConfig,
    contextOutput,
    currentWorkflowId,
    executeResult,
    historyRecords,
    jsonText,
    language,
    operation,
    previewResult,
    prompts,
    rootPath,
    scanResult,
    selectedPrompt,
    statusMessage,
    theme,
    newWorkflowId
  } from '../lib/state';
  import type { HistoryRecord, Plan, PreviewResult, PromptItem } from '../lib/types';

  let dragging = false;
  let showPreview = false;
  let editing: PromptItem | null = null;
  let editSearch = '';
  let promptContentEl: HTMLTextAreaElement;
  let fileWidth = 340;
  let styleHeight = 142;
  let contextHeight = 122;
  let pendingExecutePlan: Plan | null = null;
  let executePreview: PreviewResult | null = null;
  let previewMode: 'normal' | 'execute' = 'normal';
  let previewDetail: 'all' | 'missing' | 'conflicts' = 'all';
  let scanJobId = '';
  let scanProgress = { count: 0, currentPath: '' };

  api.loadConfig().then((r) => {
    if (r.ok && r.data) appConfig.set(r.data);
  });
  loadPromptList();
  window.addEventListener('pywebviewready', loadPromptList, { once: true });

  $: busy = $operation !== 'idle';
  $: contextWillExport = $contextOutput?.action === 'export' || (($scanResult?.file_count ?? 0) > 500);
  $: contextButtonLabel = contextWillExport ? t($language, 'exportContent') : t($language, 'copyContent');
  $: editMatches = editing && editSearch.trim()
    ? findPromptMatches(editing.content, editSearch)
    : [];

  async function loadPromptList() {
    const response = await api.listPrompts();
    if (response.ok && response.data) {
      syncPromptList(response.data);
    }
  }

  function syncPromptList(nextPrompts: PromptItem[]) {
    prompts.set(nextPrompts);
    const current = get(selectedPrompt);
    const replacement = current ? nextPrompts.find((prompt) => prompt.key === current.key) : null;
    selectedPrompt.set(replacement ?? nextPrompts[0] ?? null);
  }

  async function chooseFolder() {
    const response = await api.chooseFolder();
    if (response.ok && response.data) {
      rootPath.set(response.data);
      currentWorkflowId.set(newWorkflowId());
      await scanFolder();
    }
  }

  async function chooseJsonFile() {
    const response = await api.chooseJsonFile();
    if (response.ok && response.data) {
      jsonText.set(response.data.text);
      await parseCurrentPlan(`${t(get(language), 'importJson')}: ${response.data.path}`);
    } else if (response.error?.code !== 'CANCELLED') {
      statusMessage.set(response.error?.message || t(get(language), 'failed'));
    }
  }

  async function scanFolder() {
    const path = get(rootPath);
    if (!path) return;
    operation.set('scanning');
    scanProgress = { count: 0, currentPath: '' };
    statusMessage.set(`${t(get(language), 'scanning')}...`);
    const started = await api.startScan(path);
    if (!started.ok || !started.data) {
      operation.set('idle');
      statusMessage.set(started.error?.message || t(get(language), 'failed'));
      return;
    }
    scanJobId = started.data.jobId;
    while (get(operation) === 'scanning' && scanJobId === started.data.jobId) {
      await new Promise((resolve) => setTimeout(resolve, 120));
      const response = await api.pollScan(started.data.jobId);
      if (!response.ok || !response.data) {
        operation.set('idle');
        scanJobId = '';
        statusMessage.set(response.error?.message || t(get(language), 'failed'));
        return;
      }
      scanProgress = { count: response.data.count ?? 0, currentPath: response.data.currentPath ?? '' };
      statusMessage.set(formatT(get(language), 'scannedFiles', { count: scanProgress.count }));
      if (!response.data.done) continue;
      operation.set('idle');
      scanJobId = '';
      if (response.data.cancelled) {
        statusMessage.set(t(get(language), 'scanCancelled'));
        return;
      }
      if (!response.data.result) {
        statusMessage.set(t(get(language), 'failed'));
        return;
      }
      scanResult.set(response.data.result);
      contextOutput.set(null);
      addHistory({
        kind: 'scan',
        path,
        title: folderName(path),
        status: 'success',
        fileCount: response.data.result.file_count,
        message: `${t(get(language), 'fileTree')}: ${response.data.result.file_count}`
      });
      statusMessage.set(`${t(get(language), 'success')}: ${response.data.result.file_count}`);
      return;
    }
  }

  async function cancelScan() {
    if (!scanJobId) return;
    await api.cancelScan(scanJobId);
    statusMessage.set(t(get(language), 'scanCancelled'));
  }

  async function buildContext() {
    const path = get(rootPath);
    const prompt = get(selectedPrompt);
    if (!path || !prompt) return null;
    operation.set('copying');
    const response = await api.buildContext(path, localizedPrompt(prompt, get(language)), '');
    operation.set('idle');
    if (response.ok && response.data) {
      contextOutput.set(response.data);
      statusMessage.set(response.data.action === 'copy' ? t(get(language), 'copyContent') : `${t(get(language), 'exported')}: ${response.data.export_path}`);
      return response.data;
    }
    statusMessage.set(response.error?.message || t(get(language), 'failed'));
    return null;
  }

  async function copyContext() {
    const output = get(contextOutput) ?? await buildContext();
    if (!output) return;
    if (output.action === 'export') {
      statusMessage.set(`${t(get(language), 'exported')}: ${output.export_path}`);
      return;
    }
    await navigator.clipboard.writeText(output.text);
    statusMessage.set(t(get(language), 'copied'));
  }

  async function sendAi() {
    await loadPromptList();
    const scan = get(scanResult);
    const config = get(appConfig);
    const prompt = get(selectedPrompt);
    const path = get(rootPath);
    if (!scan || !config || !prompt || get(aiRunning)) return;
    const fileLimit = Math.max(50, config.ai_context_file_limit || 1000);
    const filesForAi = scan.files.slice(0, fileLimit);
    const omittedCount = Math.max(0, scan.files.length - filesForAi.length);
    const fileListForAi = filesForAi.map((file) => `- ${file.relative_path} (${file.size} bytes, ${file.modified_time})`).join('\n');
    const trimmedNote = omittedCount > 0 ? `\n\n[Note]\n${formatT(get(language), 'aiPayloadTrimmed', { limit: fileLimit })}` : '';
    const template = promptContent(prompt, get(language));
    const sentText = (template.includes('{file_list}') ? template.replace('{file_list}', fileListForAi) : `${template}\n\n${fileListForAi}`) + trimmedNote;
    const requestId = `ai-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const assistantId = `${requestId}-assistant`;
    const startedAt = Date.now();
    aiOpen.set(false);
    aiRunning.set(true);
    aiRequestId.set(requestId);
    aiMessages.update((messages) => [
      ...messages,
      { id: `${requestId}-user`, role: 'user', content: sentText, status: 'done' },
      { id: assistantId, role: 'assistant', content: `${t(get(language), 'waiting')}\n${config.provider} / ${config.provider_models[config.provider] || t(get(language), 'notSelected')}`, status: 'pending' }
    ]);
    statusMessage.set(t(get(language), 'aiRequestSent'));
    void runAiRequest(requestId, assistantId, {
      rootPath: path,
      fileListForAi: fileListForAi + trimmedNote,
      userInstruction: template,
      provider: config.provider,
      model: config.provider_models[config.provider],
      timeoutSeconds: config.ai_timeout_seconds,
      requestId
    }, startedAt);
  }

  async function runAiRequest(requestId: string, assistantId: string, payload: Record<string, unknown>, startedAt: number) {
    const streamed = await runAiStream(requestId, assistantId, payload, startedAt);
    if (streamed) return;
    const response = await api.generatePlan(payload);
    if (get(aiRequestId) !== requestId) return;
    aiRunning.set(false);
    aiRequestId.set('');
    const elapsedMs = Date.now() - startedAt;
    if (response.ok && response.data) {
      const json = extractJson(response.data);
      if (json) jsonText.set(json);
      activePlan.set(null);
      updateAiMessage(assistantId, response.data, 'done');
      statusMessage.set(formatT(get(language), 'aiReadyWithMs', { ms: elapsedMs }));
    } else {
      const message = response.error?.message || t(get(language), 'failed');
      updateAiMessage(assistantId, formatT(get(language), 'aiRequestFailed', { message }), 'error');
      statusMessage.set(message);
    }
  }

  async function runAiStream(requestId: string, assistantId: string, payload: Record<string, unknown>, startedAt: number) {
    const start = await api.generatePlanStream(payload);
    if (!start.ok) return false;
    while (get(aiRequestId) === requestId) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      const poll = await api.pollAiStream(requestId);
      if (!poll.ok || !poll.data) continue;
      if (poll.data.content) updateAiMessage(assistantId, poll.data.content, poll.data.done ? 'done' : 'pending');
      if (!poll.data.done) continue;
      aiRunning.set(false);
      aiRequestId.set('');
      const elapsedMs = Date.now() - startedAt;
      if (poll.data.cancelled) {
        updateAiMessage(assistantId, poll.data.content || t(get(language), 'interrupted'), 'cancelled');
        statusMessage.set(t(get(language), 'interrupted'));
      } else if (poll.data.error) {
        updateAiMessage(assistantId, formatT(get(language), 'aiRequestFailed', { message: poll.data.error }), 'error');
        statusMessage.set(poll.data.error);
      } else {
        const json = extractJson(poll.data.content);
        if (json) jsonText.set(json);
        activePlan.set(null);
        updateAiMessage(assistantId, poll.data.content, 'done');
        statusMessage.set(formatT(get(language), 'aiReadyWithMs', { ms: elapsedMs }));
      }
      return true;
    }
    return true;
  }

  function updateAiMessage(id: string, content: string, status: 'pending' | 'done' | 'error' | 'cancelled') {
    aiMessages.update((messages) => messages.map((message) => message.id === id ? { ...message, content, status } : message));
  }

  function extractJson(text: string) {
    const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
    const trimmed = (fenced ? fenced[1] : text).trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) return trimmed;
    return '';
  }

  async function parseCurrentPlan(successPrefix?: string) {
    const raw = get(jsonText);
    if (!raw.trim()) {
      activePlan.set(null);
      statusMessage.set('JSON is empty');
      return null;
    }
    const parsed = await api.parsePlan(raw);
    if (!parsed.ok || !parsed.data) {
      activePlan.set(null);
      statusMessage.set(parsed.error?.message || 'JSON parse failed');
      return null;
    }
    activePlan.set(parsed.data);
    statusMessage.set(successPrefix ? `${successPrefix} · ${parsed.data.actions.length}` : `JSON ready: ${parsed.data.actions.length}`);
    return parsed.data;
  }

  async function previewPlan() {
    await runPreview('normal');
  }

  async function runPreview(mode: 'normal' | 'execute') {
    const path = get(rootPath);
    operation.set('previewing');
    const plan = await parseCurrentPlan();
    if (!plan) {
      operation.set('idle');
      return null;
    }
    const response = await api.previewPlan(path, plan);
    operation.set('idle');
    if (response.ok && response.data) {
      previewResult.set(response.data);
      executePreview = response.data;
      pendingExecutePlan = plan;
      previewMode = mode;
      previewDetail = response.data.missing_paths.length ? 'missing' : response.data.conflicts.length ? 'conflicts' : 'all';
      showPreview = true;
      addHistory({
        kind: 'preview',
        path,
        title: `${t(get(language), 'preview')} · ${folderName(path)}`,
        status: response.data.conflicts.length || response.data.missing_paths.length ? 'warning' : 'success',
        actionCount: plan.actions.length,
        conflictCount: response.data.conflicts.length,
        missingCount: response.data.missing_paths.length,
        jsonText: get(jsonText),
        details: [
          ...response.data.missing_paths.slice(0, 20).map((missingPath) => `Missing: ${missingPath}`),
          ...response.data.conflicts.slice(0, 20).map((item) => `Conflict: ${JSON.stringify(item)}`)
        ]
      });
      statusMessage.set(mode === 'execute' ? `${t(get(language), 'preview')}: ${plan.actions.length}` : `${t(get(language), 'preview')}: ${plan.actions.length}`);
      return { plan, preview: response.data };
    } else {
      statusMessage.set(response.error?.message || t(get(language), 'failed'));
      return null;
    }
  }

  async function execute() {
    const path = get(rootPath);
    if (!path) return;
    await runPreview('execute');
  }

  async function confirmExecute() {
    const config = get(appConfig);
    const path = get(rootPath);
    const plan = pendingExecutePlan;
    if (!config || !path || !plan) return;
    showPreview = false;
    operation.set('executing');
    statusMessage.set(`${t(get(language), 'executing')}...`);
    const response = await api.executePlan(path, plan, config.conflict_policy);
    operation.set('idle');
    if (response.ok && response.data) {
      executeResult.set(response.data);
      addHistory({
        kind: 'execute',
        path,
        title: `${t(get(language), 'execute')} · ${folderName(path)}`,
        status: response.data.error_count ? 'error' : response.data.skipped_count ? 'warning' : 'success',
        actionCount: plan.actions.length,
        successCount: response.data.success_count,
        skippedCount: response.data.skipped_count,
        errorCount: response.data.error_count,
        jsonText: get(jsonText),
        details: response.data.results.map((item) => `#${item.action_id} ${item.status}: ${item.message}${item.final_path ? ` -> ${item.final_path}` : ''}`)
      });
      statusMessage.set(`${t(get(language), 'success')}: ${response.data.success_count}, skipped ${response.data.skipped_count}, errors ${response.data.error_count}`);
    } else {
      statusMessage.set(response.error?.message || t(get(language), 'failed'));
    }
  }

  async function undo() {
    operation.set('undoing');
    statusMessage.set(`${t(get(language), 'undoing')}...`);
    try {
      const response = await api.undoLast();
      addHistory({
        kind: 'undo',
        path: get(rootPath),
        title: `${t(get(language), 'undo')} · ${folderName(get(rootPath))}`,
        status: response.ok ? 'success' : 'error',
        message: response.ok ? `${t(get(language), 'undo')}: ${t(get(language), 'success')}` : response.error?.message || t(get(language), 'failed'),
        details: response.ok && response.data && typeof response.data === 'object' && 'details' in response.data
          ? ((response.data as { details: { status: string; message: string }[] }).details ?? []).map((item) => `${item.status}: ${item.message}`)
          : []
      });
      statusMessage.set(response.ok ? `${t(get(language), 'undo')}: ${t(get(language), 'success')}` : response.error?.message || t(get(language), 'failed'));
      if (response.ok) executeResult.set(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      statusMessage.set(`${t(get(language), 'undo')}: ${message}`);
    } finally {
      operation.set('idle');
    }
  }

  async function savePrompt() {
    if (!editing) return;
    const localized = get(language) === 'en'
      ? { ...editing, name_en: editing.name, content_en: editing.content }
      : { ...editing, name_zh: editing.name, content_zh: editing.content };
    const response = await api.savePrompt(localized);
    if (response.ok) {
      const refreshed = await api.listPrompts();
      if (refreshed.ok && refreshed.data) syncPromptList(refreshed.data);
      editing = null;
    }
  }

  async function deletePrompt(prompt: PromptItem, event?: MouseEvent) {
    event?.stopPropagation();
    await api.deletePrompt(prompt.key);
    prompts.update((items) => items.filter((item) => item.key !== prompt.key));
    if (get(selectedPrompt)?.key === prompt.key) selectedPrompt.set(get(prompts)[0] ?? null);
  }

  function newPrompt() {
    const name = t(get(language), 'newPrompt');
    editing = createCustomPromptDraft(get(language), name);
  }

  async function handleDrop(event: DragEvent) {
    event.preventDefault();
    dragging = false;
    const files = Array.from(event.dataTransfer?.files ?? []);
    const first = files[0] as File & { path?: string; pywebviewFullPath?: string };
    const text = event.dataTransfer?.getData('text/plain') || event.dataTransfer?.getData('text/uri-list');
    const droppedPath = first?.pywebviewFullPath || first?.path || text;
    if (first && isJsonTextPath(first.name) && !droppedPath) {
      jsonText.set(await first.text());
      await parseCurrentPlan(`${t(get(language), 'importJson')}: ${first.name}`);
    } else if (droppedPath && isJsonTextPath(droppedPath)) {
      await importJsonFromPath(normalizeDroppedPath(droppedPath));
    } else if (droppedPath) {
      rootPath.set(normalizeDroppedPath(droppedPath));
      currentWorkflowId.set(newWorkflowId());
      scanFolder();
    } else {
      statusMessage.set('This runtime did not expose the dropped folder path. Use Choose.');
    }
  }

  async function importJsonFromPath(path: string) {
    const response = await api.readTextFile(path);
    if (response.ok && response.data) {
      jsonText.set(response.data.text);
      await parseCurrentPlan(`${t(get(language), 'importJson')}: ${response.data.path}`);
    } else {
      statusMessage.set(response.error?.message || t(get(language), 'failed'));
    }
  }

  function normalizeDroppedPath(path: string) {
    return decodeURIComponent(path.trim().replace(/^file:\/\/\//, '').replace(/^file:\/+/, '')).replace(/\//g, '\\');
  }

  function isJsonTextPath(path: string) {
    return /\.(json|txt)$/i.test(path.trim().split(/[?#]/)[0]);
  }

  function toggleTheme() {
    theme.set($theme === 'dark' ? 'light' : 'dark');
  }

  function toggleLanguage() {
    language.set($language === 'zh-CN' ? 'en' : 'zh-CN');
  }

  function startResize(kind: 'file' | 'style' | 'context', event: PointerEvent) {
    const startX = event.clientX;
    const startY = event.clientY;
    const initial = { fileWidth, styleHeight, contextHeight };
    const move = (moveEvent: PointerEvent) => {
      if (kind === 'file') fileWidth = clamp(initial.fileWidth + moveEvent.clientX - startX, 220, 620);
      if (kind === 'style') styleHeight = clamp(initial.styleHeight + moveEvent.clientY - startY, 118, 240);
      if (kind === 'context') contextHeight = clamp(initial.contextHeight + moveEvent.clientY - startY, 112, 200);
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }

  function clamp(value: number, min: number, max: number) {
    return Math.max(min, Math.min(max, value));
  }

  function addHistory(record: Omit<HistoryRecord, 'id' | 'at' | 'workflowId'>) {
    const item: HistoryRecord = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      workflowId: get(currentWorkflowId),
      at: new Date().toLocaleString(),
      ...record
    };
    historyRecords.update((items) => [item, ...items].slice(0, 100));
  }

  function folderName(path: string) {
    return path.split(/[\\/]/).filter(Boolean).pop() || path || '-';
  }

  function findPromptMatches(content: string, query: string) {
    const q = query.trim().toLowerCase();
    let offset = 0;
    return content.split('\n').map((line, index) => {
      const start = offset;
      offset += line.length + 1;
      return { line, index: index + 1, start, end: start + line.length };
    }).filter((item) => item.line.toLowerCase().includes(q));
  }

  function jumpToPromptMatch(match: { start: number; end: number }) {
    requestAnimationFrame(() => {
      promptContentEl?.focus();
      promptContentEl?.setSelectionRange(match.start, match.end);
      const contentBefore = editing?.content.slice(0, match.start) ?? '';
      const lineCount = contentBefore.split('\n').length;
      promptContentEl.scrollTop = Math.max(0, (lineCount - 3) * 24);
    });
  }

  if (typeof window !== 'undefined') {
    window.__foldermindDrop = async (path: string) => {
      const normalized = normalizeDroppedPath(path);
      if (isJsonTextPath(normalized)) {
        await importJsonFromPath(normalized);
        return;
      }
      rootPath.set(normalized);
      currentWorkflowId.set(newWorkflowId());
      await scanFolder();
    };
  }

  function highlighted(line: string) {
    const q = editSearch.trim();
    if (!q) return escapeHtml(line);
    return escapeHtml(line).replace(new RegExp(escapeRegExp(q), 'gi'), (match) => `<mark>${match}</mark>`);
  }

  function escapeHtml(text: string) {
    return text.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char] ?? char);
  }

  function escapeRegExp(text: string) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }
</script>

<div
  class="organize-screen"
  class:dragging
  role="application"
  aria-label="FolderMind workspace"
  on:dragover|preventDefault={() => (dragging = true)}
  on:dragleave={() => (dragging = false)}
  on:drop={handleDrop}
>
  <header class="topbar">
    <button class="path-box" on:click={chooseFolder} title={t($language, 'choose')}>
      <FolderOpen size={18} />
      <span>{$rootPath || t($language, 'chooseFolder')}</span>
    </button>
    <button on:click={chooseFolder}>{t($language, 'choose')}</button>
    <button class="icon-button" on:click={toggleTheme} title="Theme">
      {#if $theme === 'dark'}<Moon size={18} />{:else}<Sun size={18} />{/if}
    </button>
    <button class="icon-button" on:click={toggleLanguage} title="Language">{$language === 'zh-CN' ? 'ZH' : 'EN'}</button>
  </header>

  <div class="main-grid resizable" style={`grid-template-columns: ${fileWidth}px 6px minmax(0, 1fr);`}>
    <section class="file-pane">
      <div class="pane-head">
        <span>{t($language, 'fileTree')}</span>
        {#if $operation === 'scanning'}
          <button class="mini-button" on:click={cancelScan}>{t($language, 'cancelScan')}</button>
          <small>{scanProgress.count}</small>
        {:else}
          <small>{$scanResult?.file_count ?? '-'}</small>
        {/if}
      </div>
      <pre>{$operation === 'scanning' ? `${formatT($language, 'scannedFiles', { count: scanProgress.count })}\n${scanProgress.currentPath}` : ($scanResult?.tree_text || (dragging ? t($language, 'dropToScan') : t($language, 'scanHint')))}</pre>
    </section>
    <button class="resize-handle vertical" aria-label="Resize file tree" on:pointerdown={(event) => startResize('file', event)}></button>

    <section class="work-pane" style={`grid-template-rows: ${styleHeight}px 6px ${contextHeight}px 6px minmax(0, 1fr);`}>
      <div class="block">
        <div class="label-row">
          <span>{t($language, 'style')}</span>
        </div>
        <div class="chips prompt-chips">
          {#each $prompts as prompt}
            <div class="prompt-chip" class:active={$selectedPrompt?.key === prompt.key}>
              <button on:dblclick={() => (editing = localizedPrompt(prompt, $language))} on:click={() => selectedPrompt.set(prompt)}>{promptName(prompt, $language)}</button>
              <button class="chip-delete" title={t($language, 'deletePrompt')} on:click={(event) => deletePrompt(prompt, event)}><X size={13} /></button>
            </div>
          {/each}
          <button class="add-chip" on:click={newPrompt}><Plus size={16} /></button>
        </div>
      </div>
      <button class="resize-handle horizontal" aria-label="Resize styles" on:pointerdown={(event) => startResize('style', event)}></button>

      <div class="block">
        <div class="label-row">
          <span>{t($language, 'getContext')}</span>
          <small>{t($language, 'noApiRequired')}</small>
        </div>
        <div class="actions-row">
          <button class:working={$aiRunning} on:click={sendAi} disabled={!$scanResult || busy || $aiRunning}><Wand2 size={17} />{t($language, 'sendAi')}</button>
          <button class:working={$operation === 'copying'} on:click={copyContext} disabled={!$scanResult || busy}>
            {#if contextWillExport}<FileDown size={17} />{contextButtonLabel}{:else}<Clipboard size={17} />{contextButtonLabel}{/if}
          </button>
          <button on:click|stopPropagation={chooseJsonFile}><Upload size={17} />{t($language, 'importJson')}</button>
        </div>
      </div>
      <button class="resize-handle horizontal" aria-label="Resize context controls" on:pointerdown={(event) => startResize('context', event)}></button>

      <div class="block flex-fill">
        <label for="jsonText">{t($language, 'aiJson')}</label>
        <textarea id="jsonText" bind:value={$jsonText} placeholder={t($language, 'jsonPlaceholder')}></textarea>
      </div>
    </section>
  </div>

  <footer class="statusbar">
    <span class="status-dot" class:active={busy}></span>
    <span>{$statusMessage || t($language, 'ready')}</span>
    <div class="footer-actions">
      <button class="primary" class:working={$operation === 'executing'} on:click={execute} disabled={!$jsonText || !$rootPath || busy}><Play size={17} />{t($language, 'execute')}</button>
      <button class="danger" class:working={$operation === 'undoing'} on:click={undo} disabled={!$executeResult?.undo_available || busy}><RotateCcw size={17} />{t($language, 'undo')}</button>
    </div>
  </footer>

  {#if showPreview && $previewResult}
    <div class="modal-backdrop">
      <section class="modal wide preview-modal">
        <div class="modal-head">
          <h2>{previewMode === 'execute' ? 'Execute Preview' : t($language, 'previewTitle')}</h2>
          <button class="icon-button" on:click={() => (showPreview = false)} title={t($language, 'close')}><X size={18} /></button>
        </div>
        <div class="preview-content">
          <div class="preview-summary">
            <button class:active={previewDetail === 'all'} on:click={() => (previewDetail = 'all')}>
              <small>预览</small>
              <strong>{$previewResult.lines.length}</strong>
            </button>
            <button class:active={previewDetail === 'missing'} class:warning={$previewResult.missing_paths.length > 0} on:click={() => (previewDetail = 'missing')}>
              <small>{t($language, 'missing')}</small>
              <strong>{$previewResult.missing_paths.length}</strong>
            </button>
            <button class:active={previewDetail === 'conflicts'} class:warning={$previewResult.conflicts.length > 0} on:click={() => (previewDetail = 'conflicts')}>
              <small>{t($language, 'conflicts')}</small>
              <strong>{$previewResult.conflicts.length}</strong>
            </button>
          </div>
          {#if previewDetail !== 'all'}
            <div class="preview-issues">
              {#if previewDetail === 'missing'}
                {#each $previewResult.missing_paths as item}
                  <div>Missing: {item}</div>
                {/each}
              {:else}
                {#each $previewResult.conflicts as item}
                  <div>Conflict: {JSON.stringify(item)}</div>
                {/each}
              {/if}
            </div>
          {/if}
          <div class="preview-grid">
            <div>
              <h3>{t($language, 'before')}</h3>
              <pre>{$previewResult.before_tree_text}</pre>
            </div>
            <div>
              <h3>{t($language, 'after')}</h3>
              <pre>{$previewResult.after_tree_text}</pre>
            </div>
          </div>
        </div>
        {#if previewMode === 'execute'}
          <div class="dialog-actions modal-actions">
            <button on:click={() => (showPreview = false)}>{t($language, 'cancel')}</button>
            <button class="primary" on:click={confirmExecute}><Play size={17} />确认执行</button>
          </div>
        {/if}
      </section>
    </div>
  {/if}

  {#if editing}
    <div class="modal-backdrop">
      <section class="modal">
        <div class="modal-head">
          <h2>{t($language, 'editPrompt')}</h2>
          <button class="icon-button" on:click={() => (editing = null)} title={t($language, 'close')}><X size={18} /></button>
        </div>
        <label for="promptName">{t($language, 'promptName')}</label>
        <input id="promptName" bind:value={editing.name} />
        <label for="promptSearch">{t($language, 'promptSearch')}</label>
        <div class="search-box">
          <Search size={16} />
          <input id="promptSearch" bind:value={editSearch} placeholder={t($language, 'promptSearch')} />
        </div>
        {#if editMatches.length}
          <div class="match-list">
            <small>{t($language, 'matches')}: {editMatches.length}</small>
            {#each editMatches.slice(0, 5) as match}
              <button class="match-item" on:click={() => jumpToPromptMatch(match)}>{@html highlighted(`${match.index}: ${match.line}`)}</button>
            {/each}
          </div>
        {/if}
        <label for="promptContent">{t($language, 'promptContent')}</label>
        <textarea id="promptContent" bind:this={promptContentEl} bind:value={editing.content}></textarea>
        <div class="dialog-actions">
          <button on:click={() => (editing = null)}>{t($language, 'cancel')}</button>
          <button class="primary" on:click={savePrompt}>{t($language, 'save')}</button>
        </div>
      </section>
    </div>
  {/if}
</div>
