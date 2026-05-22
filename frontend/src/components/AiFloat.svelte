<script lang="ts">
  import { Bot, CircleStop, Copy, FileJson, MessageCircle, Send, UserRound, X } from 'lucide-svelte';
  import { get } from 'svelte/store';
  import { api } from '../lib/api';
  import { formatT, t } from '../lib/i18n';
  import { aiMessages, aiOpen, aiPosition, aiRequestId, aiRunning, appConfig, jsonText, language, statusMessage } from '../lib/state';

  let dragStart: { x: number; y: number; left: number; top: number; moved: boolean } | null = null;
  let suppressNextClick = false;
  let draft = '';

  $: positionStyle = $aiPosition.x || $aiPosition.y
    ? `left: ${$aiPosition.x}px; top: ${$aiPosition.y}px; right: auto; bottom: auto;`
    : '';

  async function sendFollowUp() {
    const text = draft.trim();
    const config = get(appConfig);
    if (!text || !config || get(aiRunning)) return;

    const requestId = `ai-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const assistantId = `${requestId}-assistant`;
    const startedAt = Date.now();
    const history = get(aiMessages)
      .filter((message) => message.status !== 'pending')
      .map((message) => `${message.role === 'user' ? 'User' : 'Assistant'}:\n${message.content}`)
      .join('\n\n');
    const userInstruction = [
      'Continue the FolderMind conversation below.',
      'If you provide a file organization plan, return executable FolderMind JSON only.',
      'Otherwise answer the user normally.',
      '',
      history,
      '',
      `User:\n${text}`
    ].join('\n');

    draft = '';
    aiOpen.set(true);
    aiRunning.set(true);
    aiRequestId.set(requestId);
    aiMessages.update((messages) => [
      ...messages,
      { id: `${requestId}-user`, role: 'user', content: text, status: 'done' },
      { id: assistantId, role: 'assistant', content: `${t(get(language), 'waiting')}\n${config.provider} / ${config.provider_models[config.provider] || t(get(language), 'notSelected')}`, status: 'pending' }
    ]);

    const payload = {
      userInstruction,
      fileListForAi: '',
      provider: config.provider,
      model: config.provider_models[config.provider],
      timeoutSeconds: config.ai_timeout_seconds,
      requestId
    };

    const streamed = await runAiStream(requestId, assistantId, payload, startedAt);
    if (streamed) return;
    const response = await api.generatePlan(payload);

    if (get(aiRequestId) !== requestId) return;
    aiRunning.set(false);
    aiRequestId.set('');
    const elapsedMs = Date.now() - startedAt;
    if (response.ok && response.data) {
      updateAiMessage(assistantId, response.data, 'done');
      if (extractJson(response.data)) jsonText.set(extractJson(response.data) ?? response.data);
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
        updateAiMessage(assistantId, poll.data.content, 'done');
        const json = extractJson(poll.data.content);
        if (json) jsonText.set(json);
        statusMessage.set(formatT(get(language), 'aiReadyWithMs', { ms: elapsedMs }));
      }
      return true;
    }
    return true;
  }

  async function interruptAi() {
    const requestId = get(aiRequestId);
    if (!requestId) return;
    aiRunning.set(false);
    aiRequestId.set('');
    aiMessages.update((messages) => messages.map((message) => message.status === 'pending'
      ? { ...message, content: t(get(language), 'interrupted'), status: 'cancelled' }
      : message));
    statusMessage.set(t(get(language), 'interrupted'));
    await api.cancelAiRequest(requestId);
  }

  async function copyMessage(content: string) {
    await navigator.clipboard.writeText(content);
    statusMessage.set(t(get(language), 'copied'));
  }

  function importJsonFromMessage(content: string) {
    const json = extractJson(content);
    if (!json) {
      statusMessage.set(t(get(language), 'noJsonToImport'));
      return;
    }
    jsonText.set(json);
    statusMessage.set(t(get(language), 'jsonImported'));
  }

  async function copyConversation() {
    const transcript = get(aiMessages)
      .map((message) => `${message.role === 'user' ? t(get(language), 'you') : t(get(language), 'ai')}:\n${message.content}`)
      .join('\n\n');
    if (!transcript.trim()) return;
    await navigator.clipboard.writeText(transcript);
    statusMessage.set(t(get(language), 'copied'));
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

  function looksLikeJson(text: string) {
    const trimmed = extractJson(text);
    return trimmed.startsWith('{') || trimmed.startsWith('[');
  }

  function closeFloat() {
    aiOpen.set(false);
  }

  function startDrag(event: PointerEvent) {
    const target = event.currentTarget as HTMLElement;
    const rect = target.closest('.ai-float')?.getBoundingClientRect();
    if (!rect) return;
    dragStart = { x: event.clientX, y: event.clientY, left: rect.left, top: rect.top, moved: false };
    window.addEventListener('pointermove', dragMove);
    window.addEventListener('pointerup', stopDrag);
  }

  function dragMove(event: PointerEvent) {
    if (!dragStart) return;
    const nextX = dragStart.left + event.clientX - dragStart.x;
    const nextY = dragStart.top + event.clientY - dragStart.y;
    if (Math.abs(event.clientX - dragStart.x) > 3 || Math.abs(event.clientY - dragStart.y) > 3) dragStart.moved = true;
    aiPosition.set({
      x: clamp(nextX, 8, window.innerWidth - 80),
      y: clamp(nextY, 8, window.innerHeight - 80)
    });
  }

  function stopDrag() {
    if (dragStart?.moved) {
      suppressNextClick = true;
      setTimeout(() => (suppressNextClick = false), 0);
    }
    window.removeEventListener('pointermove', dragMove);
    window.removeEventListener('pointerup', stopDrag);
    dragStart = null;
  }

  function toggleOpen() {
    if (suppressNextClick) return;
    aiOpen.update((value) => !value);
  }

  function clamp(value: number, min: number, max: number) {
    return Math.max(min, Math.min(max, value));
  }
</script>

{#if $aiMessages.length}
  <div class="ai-float" class:open={$aiOpen} style={positionStyle}>
    {#if $aiOpen}
      <section class="ai-panel">
        <div class="ai-panel-head" role="toolbar" tabindex="0" aria-label="AI chat window" on:pointerdown={startDrag}>
          <div class="ai-title">
            <span class="ai-avatar assistant"><Bot size={18} /></span>
            <div>
              <strong>{t($language, 'aiChat')}</strong>
              <small>{$aiRunning ? t($language, 'requesting') : t($language, 'ready')}</small>
            </div>
          </div>
          <div class="ai-panel-tools">
            <button class="icon-button" on:pointerdown|stopPropagation on:click|stopPropagation={copyConversation} title={t($language, 'copyConversation')}>
              <Copy size={18} />
            </button>
            <button class="icon-button" disabled={!$aiRunning} on:pointerdown|stopPropagation on:click|stopPropagation={interruptAi} title={t($language, 'interrupt')}>
              <CircleStop size={18} />
            </button>
            <button class="icon-button" on:pointerdown|stopPropagation on:click|stopPropagation={closeFloat} title={t($language, 'hideToBubble')}>
              <X size={18} />
            </button>
          </div>
        </div>

        <div class="ai-message-list">
          {#each $aiMessages as message}
            <article class="chat-row" class:user={message.role === 'user'} class:assistant={message.role !== 'user'} class:error={message.status === 'error'} class:pending={message.status === 'pending'} class:cancelled={message.status === 'cancelled'}>
              <button class={`chat-avatar ${message.role === 'user' ? 'user' : 'assistant'}`} title={message.role === 'user' ? t($language, 'you') : t($language, 'ai')}>
                {#if message.role === 'user'}<UserRound size={17} />{:else}<Bot size={17} />{/if}
              </button>
              <div class="chat-bubble">
                <div class="chat-meta">
                  <span>{message.role === 'user' ? t($language, 'you') : t($language, 'ai')}</span>
                  {#if message.status === 'pending'}<small>{t($language, 'waiting')}</small>{/if}
                  {#if message.status === 'error'}<small>{t($language, 'failed')}</small>{/if}
                  {#if message.status === 'cancelled'}<small>{t($language, 'interrupted')}</small>{/if}
                </div>
                <pre>{message.content}</pre>
                <div class="chat-actions">
                  <button on:click={() => copyMessage(message.content)} title={t($language, 'copyMessage')}><Copy size={14} />{t($language, 'copy')}</button>
                  {#if message.role === 'assistant' && looksLikeJson(message.content)}
                    <button class="primary" on:click={() => importJsonFromMessage(message.content)} title={t($language, 'importJsonToBox')}><FileJson size={14} />{t($language, 'importJsonToBox')}</button>
                  {/if}
                </div>
              </div>
            </article>
          {/each}
        </div>

        <form class="ai-compose" on:submit|preventDefault={sendFollowUp}>
          <textarea bind:value={draft} placeholder={t($language, 'typeFollowUp')} rows="2" disabled={$aiRunning}></textarea>
          <button class="primary icon-button" type="submit" disabled={!draft.trim() || $aiRunning} title={t($language, 'send')}>
            <Send size={18} />
          </button>
        </form>
      </section>
    {:else}
      <button class="ai-bubble" class:working={$aiRunning} on:pointerdown={startDrag} on:click={toggleOpen} title={t($language, 'aiChat')}>
        {#if $aiRunning}<Bot size={22} />{:else}<MessageCircle size={22} />{/if}
        <span>{$aiMessages.length}</span>
      </button>
    {/if}
  </div>
{/if}
