<script lang="ts">
  import { Clock3, Settings, Zap } from 'lucide-svelte';
  import { api } from './lib/api';
  import { t } from './lib/i18n';
  import { appConfig, historyRecords, language, statusMessage, theme } from './lib/state';
  import AiFloat from './components/AiFloat.svelte';
  import HistoryPage from './pages/History.svelte';
  import Organize from './pages/Organize.svelte';
  import SettingsPage from './pages/Settings.svelte';

  let page: 'organize' | 'history' | 'settings' = 'organize';
  let historyLoaded = false;
  let configLoaded = false;
  let configSaveTimer: ReturnType<typeof setTimeout> | null = null;
  $: workflowCount = new Set($historyRecords.map((item) => item.workflowId)).size;

  function applyLoadedHistory(records: unknown) {
    if (Array.isArray(records)) {
      historyRecords.set(records);
      historyLoaded = true;
      statusMessage.set(`History loaded: ${records.length}`);
    }
  }

  if (typeof window !== 'undefined') {
    applyLoadedHistory(window.__foldermindInitialHistory);
    window.addEventListener('foldermind-history-loaded', (event) => {
      applyLoadedHistory((event as CustomEvent).detail);
    });
  }

  api.loadConfig().then((response) => {
    if (response.ok && response.data) {
      appConfig.set(response.data);
      language.set(response.data.language);
      theme.set(response.data.theme);
      document.documentElement.dataset.theme = response.data.theme;
      configLoaded = true;
    }
  });

  api.loadHistory().then((response) => {
    if (response.ok) {
      const records = response.data ?? [];
      if (!historyLoaded || records.length > 0) applyLoadedHistory(records);
    } else {
      statusMessage.set(response.error?.message || 'History load failed');
    }
  });

  $: document.documentElement.dataset.theme = $theme;
  $: if (historyLoaded) api.saveHistory($historyRecords);
  $: if (configLoaded && $appConfig && ($appConfig.language !== $language || $appConfig.theme !== $theme)) {
    const nextConfig = { ...$appConfig, language: $language, theme: $theme };
    appConfig.set(nextConfig);
    scheduleConfigSave(nextConfig);
  }

  function scheduleConfigSave(config: typeof $appConfig) {
    if (!config) return;
    if (configSaveTimer) clearTimeout(configSaveTimer);
    configSaveTimer = setTimeout(() => {
      configSaveTimer = null;
      void api.saveConfig(config);
    }, 120);
  }
</script>

<main class="shell">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">FM</div>
      <div>
        <strong>FolderMind</strong>
        <small>{t($language, 'appSubtitle')}</small>
      </div>
    </div>

    <button class:active={page === 'organize'} on:click={() => (page = 'organize')} title={t($language, 'organize')}>
      <Zap size={17} />
      <span>{t($language, 'organize')}</span>
    </button>
    <button class:active={page === 'history'} on:click={() => (page = 'history')} title={t($language, 'history')}>
      <Clock3 size={17} />
      <span>{t($language, 'history')}</span>
      <small class="nav-count">{workflowCount}</small>
    </button>

    <div class="sidebar-spacer"></div>
    <button class="settings-nav" class:active={page === 'settings'} on:click={() => (page = 'settings')} title={t($language, 'settings')}>
      <Settings size={17} />
      <span>{t($language, 'settings')}</span>
    </button>
  </aside>

  <section class="workspace">
    {#if page === 'organize'}
      <Organize />
    {:else if page === 'history'}
      <HistoryPage />
    {:else}
      <SettingsPage />
    {/if}
  </section>

  <AiFloat />
</main>
