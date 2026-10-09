<script setup lang="ts">
// PDV › Ajustes › Terminal (v4 `salao-mesas4.html` pino 1): a saúde do terminal em
// página, o mesmo diagnóstico do painel do pé do rail (`PosTerminalHealth`), com
// o caminho de conserto: testar o agente de novo, abrir a configuração do terminal
// no Admin e atualizar a tela.
import { terminalHealthRows, terminalOverallStatus } from "~/presentation/terminalHealth";

useHead({ title: "Terminal" });

const { pos, refresh } = await usePosTerminal();
const { probe, checking, check, agentConfigured } = useAgentHealth(computed(() => pos.value!));
const rows = computed(() => pos.value
  ? terminalHealthRows(
    pos.value.terminal_components,
    { status: pos.value.fiscal_status, label: pos.value.fiscal_label, message: pos.value.fiscal_message },
    probe.value,
  )
  : []);
const overall = computed(() => terminalOverallStatus(rows.value));
const adminOrigin = computed(() => String(useRuntimeConfig().public.adminBaseUrl || ""));
const terminalAdminUrl = computed(() => {
  if (!pos.value || !adminOrigin.value || !pos.value.danfe_screen_allowed) return "";
  return `${adminOrigin.value}/admin/pos/terminal/${encodeURIComponent(pos.value.terminal_ref)}/agent/`;
});
const TONE: Record<string, { label: string; dot: string; text: string }> = {
  ready: { label: "OK", dot: "bg-success", text: "text-success" },
  warning: { label: "Atenção", dot: "bg-warning", text: "text-warning" },
  error: { label: "Erro", dot: "bg-destructive", text: "text-destructive" },
  absent: { label: "Não instalado", dot: "bg-muted-foreground/40", text: "text-muted-foreground" },
  deferred: { label: "Na estação", dot: "bg-muted-foreground/60", text: "text-muted-foreground" },
};
function tone(status: string) {
  return TONE[status] || { label: status || "Sem leitura", dot: "bg-muted-foreground", text: "text-muted-foreground" };
}
const refreshing = ref(false);
async function refreshScreen() {
  refreshing.value = true;
  try {
    await refresh();
  } finally {
    refreshing.value = false;
  }
}
</script>

<template>
  <PosSettingsShell title="Terminal" subtitle="saúde do balcão e dos periféricos">
    <section v-if="pos" class="rounded-xl border border-border bg-card" data-settings-terminal>
      <header class="flex items-center gap-3 border-b border-border p-4">
        <span class="grid size-11 place-items-center rounded-lg bg-secondary">
          <Icon name="lucide:monitor-cog" class="size-5" aria-hidden="true" />
        </span>
        <div class="min-w-0 flex-1">
          <h2 class="truncate op-title">{{ pos.terminal_label }}</h2>
          <p class="op-micro text-muted-foreground">Este dispositivo</p>
        </div>
        <span class="inline-flex items-center gap-1.5 op-label font-semibold" :class="tone(overall).text">
          <span class="size-2 rounded-full" :class="tone(overall).dot" aria-hidden="true" />{{ tone(overall).label }}
        </span>
      </header>
      <ul class="divide-y divide-border">
        <li v-for="row in rows" :key="row.key" class="grid grid-cols-[auto_1fr_auto] items-center gap-3 px-4 py-3">
          <span class="size-2.5 rounded-full" :class="tone(row.status).dot" aria-hidden="true" />
          <div class="min-w-0">
            <p class="op-label font-semibold">{{ row.label }}</p>
            <p v-if="row.message" class="op-micro text-muted-foreground">{{ row.message }}</p>
          </div>
          <span class="op-label font-semibold" :class="tone(row.status).text">{{ tone(row.status).label }}</span>
        </li>
      </ul>
      <footer class="flex flex-wrap items-center gap-2 border-t border-border p-4">
        <NuxtButton
          v-if="agentConfigured"
          color="neutral"
          variant="outline"
          icon="i-lucide-refresh-cw"
          label="Testar o agente de novo"
          :loading="checking"
          @click="check"
        />
        <NuxtButton
          color="neutral"
          variant="outline"
          icon="i-lucide-rotate-cw"
          label="Atualizar a tela"
          :loading="refreshing"
          data-terminal-refresh
          @click="refreshScreen"
        />
        <a
          v-if="terminalAdminUrl"
          class="op-label text-muted-foreground underline underline-offset-2 hover:text-foreground"
          :href="terminalAdminUrl"
          target="_blank"
          rel="noopener"
        >Configuração do terminal no Admin</a>
      </footer>
    </section>
  </PosSettingsShell>
</template>
