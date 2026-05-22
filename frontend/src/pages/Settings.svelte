<script lang="ts">
  import { onDestroy } from 'svelte';
  import { AlertTriangle, CheckCircle2, Eye, EyeOff, FolderOpen, Plus, RotateCcw, Save, Search, Trash2, X, XCircle } from 'lucide-svelte';
  import { api } from '../lib/api';
  import { formatT, t } from '../lib/i18n';
  import { createCustomPromptDraft, localizedPrompt, promptContent, promptName } from '../lib/promptText';
  import { appConfig, language, prompts as promptStore, theme } from '../lib/state';
  import type { Config, PromptItem, Provider } from '../lib/types';

  const providers: { key: Provider; label: string }[] = [
    { key: 'anthropic', label: 'Anthropic (Claude)' },
    { key: 'openai', label: 'OpenAI (GPT)' },
    { key: 'custom', label: 'Custom' }
  ];

  const defaultEndpoints: Record<Provider, string> = {
    anthropic: 'https://api.anthropic.com/v1/messages',
    openai: 'https://api.openai.com/v1/chat/completions',
    custom: ''
  };

  let config: Config | null = null;
  let providerApiKeys: Record<Provider, string> = { anthropic: '', openai: '', custom: '' };
  let showApiKey = false;
  let modelName = '';
  let prompts: PromptItem[] = [];
  let promptSearch = '';
  let editing: PromptItem | null = null;
  let message = '';
  let testMessage = '';
  let testState: 'idle' | 'testing' | 'success' | 'error' = 'idle';
  let historyInfo: { path: string; folder: string } | null = null;
  let showResetConfirm = false;
  let configLoaded = false;
  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null;
  let lastSavedSignature = '';
  let lastScheduledSignature = '';

  api.loadConfig().then((response) => {
    if (response.ok && response.data) {
      config = normalizeConfig({ ...response.data, language: $language, theme: $theme });
      providerApiKeys = { ...providerApiKeys, ...(response.data.api_keys ?? {}) };
      appConfig.set(config);
      language.set(config.language);
      theme.set(config.theme);
      lastSavedSignature = currentSettingsSignature();
      configLoaded = true;
    }
  });
  loadPrompts();
  api.historyInfo().then((response) => {
    if (response.ok && response.data) historyInfo = response.data;
  });

  $: activeProvider = config?.provider ?? 'anthropic';
  $: activeEndpoint = config?.provider_endpoint_urls?.[activeProvider] ?? defaultEndpoints[activeProvider];
  $: activeApiKey = providerApiKeys[activeProvider] ?? '';
  $: filteredPrompts = prompts.filter((prompt) => {
    const q = promptSearch.trim().toLowerCase();
    return !q || promptName(prompt, $language).toLowerCase().includes(q) || promptContent(prompt, $language).toLowerCase().includes(q);
  });
  $: if (configLoaded && config) {
    const signature = currentSettingsSignature();
    if (signature !== lastSavedSignature && signature !== lastScheduledSignature) {
      scheduleAutoSave(signature);
    }
  }

  onDestroy(() => {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    if (configLoaded && config && currentSettingsSignature() !== lastSavedSignature) {
      void save('auto');
    }
  });

  function normalizeConfig(value: Config): Config {
    const provider = providers.some((item) => item.key === value.provider) ? value.provider : 'anthropic';
    return {
      ...value,
      provider,
      provider_endpoint_urls: { ...defaultEndpoints, ...(value.provider_endpoint_urls ?? {}), custom: value.provider_endpoint_urls?.custom ?? value.custom_endpoint_url ?? '' },
      provider_models: { anthropic: 'claude-opus-4-6', openai: 'gpt-4o', custom: '', ...value.provider_models },
      custom_models: { anthropic: [], openai: [], custom: [], ...value.custom_models },
      ai_timeout_seconds: Number(value.ai_timeout_seconds || 60),
      ai_context_file_limit: Number(value.ai_context_file_limit || 1000),
      api_keys: undefined
    };
  }

  async function loadPrompts() {
    const response = await api.listPrompts();
    if (response.ok && response.data) {
      prompts = response.data;
      promptStore.set(response.data);
    }
  }

  function selectProvider(provider: Provider) {
    if (!config) return;
    config = { ...config, provider };
    showApiKey = false;
    testState = 'idle';
    testMessage = '';
  }

  function setCurrentModel(model: string) {
    if (!config) return;
    config = {
      ...config,
      provider_models: { ...config.provider_models, [config.provider]: model }
    };
  }

  function setEndpoint(value: string) {
    if (!config) return;
    config = {
      ...config,
      custom_endpoint_url: config.provider === 'custom' ? value : config.custom_endpoint_url,
      provider_endpoint_urls: { ...config.provider_endpoint_urls, [config.provider]: value }
    };
  }

  function setTimeoutSeconds(value: string) {
    if (!config) return;
    config = { ...config, ai_timeout_seconds: Number(value) || 60 };
  }

  function setContextFileLimit(value: string) {
    if (!config) return;
    const limit = Math.max(50, Math.min(Number(value) || 1000, 5000));
    config = { ...config, ai_context_file_limit: limit };
  }

  function setActiveApiKey(value: string) {
    providerApiKeys = { ...providerApiKeys, [activeProvider]: value };
    testState = 'idle';
    testMessage = '';
  }

  function addModel() {
    if (!config || !modelName.trim()) return;
    const provider = config.provider;
    const current = config.custom_models[provider] ?? [];
    const nextModels = Array.from(new Set([...current, modelName.trim()]));
    config = {
      ...config,
      custom_models: { ...config.custom_models, [provider]: nextModels },
      provider_models: { ...config.provider_models, [provider]: modelName.trim() }
    };
    modelName = '';
  }

  function removeModel(name: string) {
    if (!config) return;
    const provider = config.provider;
    const nextModels = (config.custom_models[provider] ?? []).filter((item) => item !== name);
    config = {
      ...config,
      custom_models: { ...config.custom_models, [provider]: nextModels },
      provider_models: { ...config.provider_models, [provider]: config.provider_models[provider] === name ? nextModels[0] ?? '' : config.provider_models[provider] }
    };
  }

  function buildPayload(): Config {
    if (!config) throw new Error('Config is not ready.');
    return {
      ...config,
      language: $language,
      theme: $theme,
      custom_endpoint_url: config.provider_endpoint_urls.custom,
      api_keys: providerApiKeys
    };
  }

  function currentSettingsSignature() {
    return config ? JSON.stringify(buildPayload()) : '';
  }

  function scheduleAutoSave(signature: string) {
    lastScheduledSignature = signature;
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(() => {
      autoSaveTimer = null;
      void save('auto');
    }, 550);
  }

  async function save(mode: 'manual' | 'auto' = 'manual') {
    if (!config) return;
    const payload = buildPayload();
    const response = await api.saveConfig(payload);
    if (response.ok) {
      config = payload;
      appConfig.set(config);
      lastSavedSignature = currentSettingsSignature();
      lastScheduledSignature = lastSavedSignature;
    }
    message = response.ok ? (mode === 'auto' ? t($language, 'autoSaved') : t($language, 'settingsSaved')) : response.error?.message || t($language, 'saveFailed');
  }

  async function testConnection() {
    if (!config) return;
    testState = 'testing';
    testMessage = t($language, 'testing');
    const response = await api.testConnection({
      provider: config.provider,
      model: config.provider_models[config.provider],
      apiKey: providerApiKeys[config.provider],
      anthropicUrl: config.provider_endpoint_urls.anthropic,
      openaiUrl: config.provider_endpoint_urls.openai,
      customUrl: config.provider_endpoint_urls.custom,
      timeoutSeconds: config.ai_timeout_seconds
    });
    if (!response.ok || !response.data) {
      testState = 'error';
      testMessage = response.error?.message || t($language, 'failed');
      return;
    }
    testState = response.data.success ? 'success' : 'error';
    testMessage = response.data.success
      ? formatT($language, 'connectionSuccess', { ms: response.data.latencyMs })
      : formatT($language, 'connectionFailed', { message: response.data.errorMessage ?? t($language, 'failed') });
  }

  async function savePrompt() {
    if (!editing) return;
    const localized = $language === 'en'
      ? { ...editing, name_en: editing.name, content_en: editing.content }
      : { ...editing, name_zh: editing.name, content_zh: editing.content };
    const response = await api.savePrompt(localized);
    if (response.ok) {
      editing = null;
      await loadPrompts();
    }
  }

  async function deletePrompt(prompt: PromptItem) {
    await api.deletePrompt(prompt.key);
    await loadPrompts();
  }

  function newPrompt() {
    const name = t($language, 'newPrompt');
    editing = createCustomPromptDraft($language, name);
  }

  function editPrompt(prompt: PromptItem) {
    editing = localizedPrompt(prompt, $language);
  }

  async function openHistoryFolder() {
    const response = await api.openHistoryFolder();
    message = response.ok ? `${t($language, 'historyStorage')}: ${response.data}` : response.error?.message || t($language, 'openFailed');
  }

  async function resetSettings() {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    autoSaveTimer = null;
    const response = await api.resetConfig();
    if (response.ok && response.data) {
      config = normalizeConfig(response.data);
      providerApiKeys = { anthropic: '', openai: '', custom: '', ...(response.data.api_keys ?? {}) };
      appConfig.set(config);
      language.set(config.language);
      theme.set(config.theme);
      lastSavedSignature = currentSettingsSignature();
      lastScheduledSignature = lastSavedSignature;
      showResetConfirm = false;
      message = t($language, 'restoredDefaultSettings');
      await loadPrompts();
    } else {
      message = response.error?.message || t($language, 'restoreDefaultFailed');
    }
  }
</script>

{#if config}
  <div class="settings-grid">
    <section class="settings-column">
      <div class="settings-card">
        <h2>{t($language, 'apiProvider')}</h2>
        <div class="segmented">
          {#each providers as provider}
            <button class:active={config.provider === provider.key} on:click={() => selectProvider(provider.key)}>{provider.label}</button>
          {/each}
        </div>
      </div>

      <div class="settings-card">
        <div class="label-row">
          <h2>{t($language, 'modelManage')}</h2>
          <small>{t($language, 'currentModel')}: {config.provider_models[config.provider] || t($language, 'notSelected')}</small>
        </div>
        <div class="model-list">
          {#each config.custom_models[config.provider] ?? [] as model}
            <button class:active={config.provider_models[config.provider] === model} on:click={() => setCurrentModel(model)}>
              <span>{model}</span>
              <small>{t($language, 'preset')}</small>
            </button>
            <button class="small-danger" on:click={() => removeModel(model)} title={t($language, 'delete')}><X size={14} /></button>
          {/each}
        </div>
        <div class="inline-form">
          <input bind:value={modelName} placeholder={t($language, 'modelPlaceholder')} />
          <button on:click={addModel}><Plus size={16} />{t($language, 'add')}</button>
        </div>
      </div>

      <div class="settings-card">
        <div class="label-row">
          <h2>{t($language, 'apiEndpoint')}</h2>
          {#if config.provider !== 'custom'}<small>{t($language, 'defaultEndpointHint')}</small>{/if}
        </div>
        <input value={activeEndpoint} placeholder={defaultEndpoints[config.provider] || 'https://api.example.com/v1/chat/completions'} on:input={(event) => setEndpoint(event.currentTarget.value)} />
        {#if config.provider === 'custom'}
          <p class="endpoint-help">{t($language, 'customEndpointHint')}</p>
        {/if}
      </div>

      <div class="settings-card compact">
        <label>
          {t($language, 'requestTimeout')}
          <select value={config.ai_timeout_seconds} on:change={(event) => setTimeoutSeconds(event.currentTarget.value)}>
            <option value="30">30 s</option>
            <option value="60">60 s</option>
            <option value="120">120 s</option>
          </select>
        </label>
        <label>
          {t($language, 'contextFileLimit')}
          <input type="number" min="50" max="5000" step="50" value={config.ai_context_file_limit} on:input={(event) => setContextFileLimit(event.currentTarget.value)} />
        </label>
        <p class="endpoint-help">{t($language, 'contextFileLimitHint')}</p>
      </div>

      <div class="settings-card">
        <h2>{t($language, 'apiKey')}</h2>
        <div class="secret-field">
          <input value={activeApiKey} type={showApiKey ? 'text' : 'password'} placeholder={t($language, 'apiKeyHint')} on:input={(event) => setActiveApiKey(event.currentTarget.value)} />
          <button class="icon-button" title={showApiKey ? t($language, 'hide') : t($language, 'show')} on:click={() => (showApiKey = !showApiKey)}>
            {#if showApiKey}<EyeOff size={18} />{:else}<Eye size={18} />{/if}
          </button>
        </div>
        <div class="test-row">
          <button class:working={testState === 'testing'} disabled={testState === 'testing'} on:click={testConnection}>{t($language, 'testConnection')}</button>
          {#if testMessage}
            <span class:success={testState === 'success'} class:error={testState === 'error'}>
              {#if testState === 'success'}<CheckCircle2 size={16} />{:else if testState === 'error'}<XCircle size={16} />{/if}
              {testMessage}
            </span>
          {/if}
        </div>
      </div>
    </section>

    <section class="settings-column">
      <section class="settings-card prompt-manager">
        <div class="manager-head">
          <h2>{t($language, 'promptManage')}</h2>
          <button on:click={newPrompt}><Plus size={16} />{t($language, 'create')}</button>
        </div>
        <div class="search-box">
          <Search size={16} />
          <input bind:value={promptSearch} placeholder={t($language, 'search')} />
        </div>
        <div class="prompt-list">
          {#each filteredPrompts as prompt}
            <div class="prompt-row">
              <strong>{promptName(prompt, $language)}</strong>
              <div>
                {#if prompt.is_preset}<span>{t($language, 'preset')}</span>{/if}
                <button on:click={() => editPrompt(prompt)}>{t($language, 'edit')}</button>
                <button on:click={() => deletePrompt(prompt)}><Trash2 size={15} />{t($language, 'delete')}</button>
              </div>
            </div>
          {/each}
        </div>
      </section>

      <div class="settings-card compact">
        <label>
          Language
          <select bind:value={$language}>
            <option value="zh-CN">中文</option>
            <option value="en">English</option>
          </select>
        </label>
        <label>
          Theme
          <select bind:value={$theme}>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>
      </div>

      <div class="settings-card">
        <h2>{t($language, 'historyStorage')}</h2>
        <p class="muted">{t($language, 'historyStorageHint')}</p>
        <input readonly value={historyInfo?.path ?? ''} />
        <button on:click={openHistoryFolder}><FolderOpen size={16} />{t($language, 'openHistoryFolder')}</button>
      </div>

      <div class="settings-card danger-zone">
        <h2>{t($language, 'resetSettings')}</h2>
        <p class="muted">{t($language, 'resetSettingsHint')}</p>
        <button class="danger" on:click={() => (showResetConfirm = true)}><RotateCcw size={16} />{t($language, 'resetSettings')}</button>
      </div>

      <button class="primary save-button" on:click={() => save('manual')}><Save size={17} />{t($language, 'saveSettings')}</button>
      <p class="muted">{message}</p>
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
      <label for="promptContent">{t($language, 'promptContent')}</label>
      <textarea id="promptContent" bind:value={editing.content}></textarea>
      <div class="dialog-actions">
        <button on:click={() => (editing = null)}>{t($language, 'cancel')}</button>
        <button class="primary" on:click={savePrompt}>{t($language, 'save')}</button>
      </div>
    </section>
  </div>
{/if}

{#if showResetConfirm}
  <div class="modal-backdrop">
    <section class="modal confirm-modal strong-confirm">
      <div class="modal-head">
        <h2><AlertTriangle size={22} />{t($language, 'resetSettingsConfirmTitle')}</h2>
        <button class="icon-button" on:click={() => (showResetConfirm = false)} title={t($language, 'close')}><X size={18} /></button>
      </div>
      <p>{t($language, 'resetSettingsConfirmBody')}</p>
      <div class="dialog-actions">
        <button on:click={() => (showResetConfirm = false)}>{t($language, 'cancel')}</button>
        <button class="danger" on:click={resetSettings}><RotateCcw size={17} />{t($language, 'confirmReset')}</button>
      </div>
    </section>
  </div>
{/if}
