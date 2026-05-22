<script lang="ts">
  import { Copy, FileJson, RotateCcw, X } from 'lucide-svelte';
  import { historyRecords, language, statusMessage } from '../lib/state';
  import { api } from '../lib/api';
  import { t } from '../lib/i18n';
  import type { HistoryRecord } from '../lib/types';

  type Workflow = {
    id: string;
    title: string;
    path: string;
    at: string;
    status: 'success' | 'warning' | 'error';
    records: HistoryRecord[];
  };

  let selectedId = '';
  let detailFilter: 'all' | 'preview' | 'missing' | 'conflicts' | 'errors' = 'all';
  let detailModalTitle = '';
  let detailModalLines: string[] = [];
  let pendingDelete: Workflow | null = null;

  $: workflows = buildWorkflows($historyRecords);
  $: selected = workflows.find((item) => item.id === selectedId) ?? workflows[0] ?? null;
  $: if (!selectedId && workflows[0]) selectedId = workflows[0].id;
  $: latest = selected?.records[0] ?? null;
  $: scan = findKind(selected, 'scan');
  $: preview = findKind(selected, 'preview');
  $: execute = findKind(selected, 'execute');
  $: undo = findKind(selected, 'undo');

  async function clearHistory() {
    const response = await api.clearHistory();
    if (!response.ok) {
      statusMessage.set(response.error?.message || t($language, 'failed'));
      return;
    }
    historyRecords.set([]);
    selectedId = '';
    statusMessage.set(t($language, 'clearHistory'));
  }

  function askDelete(workflow: Workflow, event: Event) {
    event.stopPropagation();
    pendingDelete = workflow;
  }

  async function deleteWorkflow() {
    if (!pendingDelete) return;
    const deleteIds = new Set(pendingDelete.records.map((record) => record.id));
    const response = await api.deleteHistoryRecords([...deleteIds]);
    if (!response.ok) {
      statusMessage.set(response.error?.message || '删除历史失败');
      pendingDelete = null;
      return;
    }
    historyRecords.update((records) => records.filter((record) => !deleteIds.has(record.id)));
    if (selectedId === pendingDelete.id) {
      selectedId = '';
    }
    statusMessage.set(`已删除 ${response.data?.deleted ?? deleteIds.size} 条历史记录`);
    pendingDelete = null;
  }

  function buildWorkflows(records: HistoryRecord[]): Workflow[] {
    const groups = new Map<string, HistoryRecord[]>();
    for (const record of records) {
      const key = workflowKey(record);
      const group = groups.get(key) ?? [];
      group.push(record);
      groups.set(key, group);
    }
    return Array.from(groups.entries()).map(([id, group]) => {
      const sorted = [...group].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
      const newest = sorted[0];
      const worst = sorted.some((item) => item.status === 'error') ? 'error' : sorted.some((item) => item.status === 'warning') ? 'warning' : 'success';
      return {
        id,
        title: newest.title.replace(/^(预览|执行整理|Undo|Preview|Execute) · /, ''),
        path: newest.path,
        at: newest.at,
        status: worst,
        records: sorted
      };
    }).sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  }

  function findKind(workflow: Workflow | null, kind: HistoryRecord['kind']) {
    return workflow?.records.find((item) => item.kind === kind) ?? null;
  }

  function workflowKey(record: HistoryRecord) {
    const stamp = Date.parse(record.at);
    const bucket = Number.isFinite(stamp) ? Math.floor(stamp / (10 * 60 * 1000)) : record.workflowId;
    return `${record.path}::${bucket}`;
  }

  function stat(record: HistoryRecord | null, key: 'successCount' | 'skippedCount' | 'errorCount' | 'fileCount' | 'actionCount' | 'conflictCount' | 'missingCount') {
    return record?.[key] ?? 0;
  }

  function stepClass(record: HistoryRecord | null) {
    return record ? record.status : 'pending';
  }

  function filteredDetails(workflow: Workflow) {
    const lines = workflow.records.flatMap((record) => [`[${record.kind}] ${record.at}`, record.message, ...(record.details ?? [])].filter(Boolean) as string[]);
    if (detailFilter === 'all') return lines;
    if (detailFilter === 'preview') return lines.filter((line) => line.toLowerCase().includes('[preview]') || line.toLowerCase().includes('missing') || line.toLowerCase().includes('conflict'));
    if (detailFilter === 'missing') return lines.filter((line) => line.toLowerCase().includes('missing'));
    if (detailFilter === 'conflicts') return lines.filter((line) => line.toLowerCase().includes('conflict'));
    return lines.filter((line) => line.toLowerCase().includes('error'));
  }

  function showDetails(filter: typeof detailFilter, title: string) {
    if (!selected) return;
    detailFilter = filter;
    detailModalTitle = title;
    detailModalLines = filteredDetails(selected);
  }

  function closeDetails() {
    detailModalTitle = '';
    detailModalLines = [];
  }

  async function copyDetailModal() {
    if (!detailModalLines.length) return;
    await navigator.clipboard.writeText(detailModalLines.join('\n'));
    statusMessage.set(t($language, 'copied'));
  }
</script>

<section class="history-screen">
  <header class="page-head">
    <div>
      <h1>{t($language, 'historyPane')}</h1>
      <p>{t($language, 'historyHint')}</p>
    </div>
    <button on:click={clearHistory} disabled={!$historyRecords.length}><RotateCcw size={16} />{t($language, 'clearHistory')}</button>
  </header>

  <div class="history-layout">
    <aside class="history-events">
      {#if !workflows.length}
        <div class="empty-state">{t($language, 'noHistory')}</div>
      {:else}
        {#each workflows as workflow}
          <button class="history-event-card" class:active={selected?.id === workflow.id} on:click={() => (selectedId = workflow.id)}>
            <span class={`record-dot ${workflow.status}`}></span>
            <strong>{workflow.title}</strong>
            <small>{workflow.records.length} steps · {workflow.at}</small>
            <span class="delete-history" role="button" tabindex="0" title="删除历史" on:click={(event) => askDelete(workflow, event)} on:keydown={(event) => event.key === 'Enter' && askDelete(workflow, event)}>
              <X size={16} />
            </span>
          </button>
        {/each}
      {/if}
    </aside>

    <section class="history-detail">
      {#if selected}
        <div class="detail-title">
          <div>
            <h2>{selected.title}</h2>
            <p>{selected.path}</p>
          </div>
        </div>

        <div class="workflow-steps">
          <button class={stepClass(scan)} on:click={() => showDetails('all', t($language, 'scan'))}><small>{t($language, 'scan')}</small><strong>{scan ? t($language, scan.status === 'success' ? 'success' : 'failed') : '-'}</strong></button>
          <button class={stepClass(preview)} class:active={detailFilter === 'preview'} on:click={() => showDetails('preview', t($language, 'preview'))}><small>{t($language, 'preview')}</small><strong>{preview ? `${stat(preview, 'conflictCount')} / ${stat(preview, 'missingCount')}` : '-'}</strong></button>
          <button class={stepClass(execute)} on:click={() => showDetails('errors', t($language, 'execute'))}><small>{t($language, 'execute')}</small><strong>{execute ? `${stat(execute, 'successCount')} / ${stat(execute, 'skippedCount')} / ${stat(execute, 'errorCount')}` : '-'}</strong></button>
          <button class={stepClass(undo)} on:click={() => showDetails('all', t($language, 'undo'))}><small>{t($language, 'undo')}</small><strong>{undo ? t($language, undo.status === 'success' ? 'success' : 'failed') : '-'}</strong></button>
        </div>

        <div class="metric-grid">
          <div><small>{t($language, 'files')}</small><strong>{stat(scan, 'fileCount')}</strong></div>
          <div><small>{t($language, 'actions')}</small><strong>{stat(execute ?? preview, 'actionCount')}</strong></div>
          <div><small>{t($language, 'success')}</small><strong>{stat(execute, 'successCount')}</strong></div>
          <div><small>{t($language, 'skipped')}</small><strong>{stat(execute, 'skippedCount')}</strong></div>
          <button class:active={detailFilter === 'errors'} on:click={() => showDetails('errors', t($language, 'errors'))}><small>{t($language, 'errors')}</small><strong>{stat(execute, 'errorCount')}</strong></button>
          <button class:active={detailFilter === 'conflicts'} on:click={() => showDetails('conflicts', t($language, 'conflicts'))}><small>{t($language, 'conflicts')}</small><strong>{stat(preview, 'conflictCount')}</strong></button>
          <button class:active={detailFilter === 'missing'} on:click={() => showDetails('missing', t($language, 'missing'))}><small>{t($language, 'missing')}</small><strong>{stat(preview, 'missingCount')}</strong></button>
          <div><small>{t($language, 'eventType')}</small><strong>{latest?.kind ?? '-'}</strong></div>
        </div>

        <div class="detail-columns">
          <section>
            <h3>{t($language, 'details')}</h3>
            {#if filteredDetails(selected).length}
              <pre class="selectable-text">{filteredDetails(selected).join('\n')}</pre>
            {:else}
              <div class="empty-state">{t($language, 'noDetails')}</div>
            {/if}
          </section>
          <section>
            <h3><FileJson size={16} />JSON</h3>
            {#if (execute ?? preview)?.jsonText}
              <pre class="selectable-text">{(execute ?? preview)?.jsonText}</pre>
            {:else}
              <div class="empty-state">{t($language, 'noJsonSnapshot')}</div>
            {/if}
          </section>
        </div>
      {:else}
        <div class="empty-state">{t($language, 'noHistory')}</div>
      {/if}
    </section>
  </div>

  {#if detailModalTitle}
    <div class="modal-backdrop">
      <section class="modal wide">
        <div class="modal-head">
          <h2>{detailModalTitle}</h2>
          <button on:click={closeDetails}>{t($language, 'close')}</button>
        </div>
        {#if detailModalLines.length}
          <pre class="detail-modal-pre selectable-text">{detailModalLines.join('\n')}</pre>
        {:else}
          <div class="empty-state">{t($language, 'noDetails')}</div>
        {/if}
        <div class="dialog-actions modal-actions">
          <button on:click={copyDetailModal} disabled={!detailModalLines.length}><Copy size={16} />{t($language, 'copyAllContent')}</button>
        </div>
      </section>
    </div>
  {/if}

  {#if pendingDelete}
    <div class="modal-backdrop">
      <section class="modal confirm-modal">
        <div class="modal-head">
          <h2>删除历史记录</h2>
          <button on:click={() => (pendingDelete = null)}>{t($language, 'close')}</button>
        </div>
        <p>确定要删除“{pendingDelete.title}”这条历史记录吗？这个操作会删除它包含的 {pendingDelete.records.length} 条步骤记录。</p>
        <div class="dialog-actions">
          <button on:click={() => (pendingDelete = null)}>{t($language, 'cancel')}</button>
          <button class="danger" on:click={deleteWorkflow}>删除</button>
        </div>
      </section>
    </div>
  {/if}
</section>
