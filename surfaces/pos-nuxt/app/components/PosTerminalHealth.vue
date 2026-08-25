<script setup lang="ts">
// Saúde do terminal com sonda de verdade e caminho de conserto.
//
// O servidor projeta o que sabe (config declarada); a resposta que só a estação
// tem — o agente do balcão está de pé? — sai da sonda desta página
// (`useAgentHealth`, ao montar + a cada 60s) e é promovida às linhas de
// Impressora/Gaveta/Agente por `presentation/terminalHealth`. E o popover não
// para no diagnóstico: dá o próximo passo (testar de novo, reiniciar o agente,
// abrir a configuração do terminal), porque estado sem saída é só ansiedade.
import type { POSProjection } from "~/types/pos";
import { terminalHealthRows, terminalOverallStatus } from "~/presentation/terminalHealth";

const props = defineProps<{
  pos: POSProjection;
  /** Rail mode: render a dot-only vertical trigger instead of the header pill. */
  compact?: boolean;
}>();

const posRef = computed(() => props.pos);
const { probe, checking, check, agentConfigured } = useAgentHealth(posRef);

const rows = computed(() =>
  terminalHealthRows(
    props.pos.terminal_components,
    {
      status: props.pos.fiscal_status,
      label: props.pos.fiscal_label,
      message: props.pos.fiscal_message,
    },
    probe.value,
  ),
);
const overall = computed(() => meta(terminalOverallStatus(rows.value)));
const agentDown = computed(() => probe.value?.ok === false);

// A tela de configuração do terminal no gestor: é lá que mora o download do
// agente e a config da estação. Gated pelo mesmo acesso do host do Django.
const djangoOrigin = computed(() => String(useRuntimeConfig().public.djangoPublicBaseUrl || ""));
const terminalAdminUrl = computed(() => {
  if (!djangoOrigin.value || !props.pos.danfe_screen_allowed) return "";
  return `${djangoOrigin.value}/admin/pos/terminal/${encodeURIComponent(props.pos.terminal_ref)}/agent/`;
});

type StatusMeta = {
  label: string;
  dot: string;
  text: string;
  badge: "success" | "warning" | "destructive" | "outline";
};

const STATUS_META: Record<string, StatusMeta> = {
  ready: { label: "OK", dot: "bg-success", text: "text-success", badge: "success" },
  warning: { label: "Atenção", dot: "bg-warning", text: "text-amber-700 dark:text-amber-400", badge: "warning" },
  error: { label: "Erro", dot: "bg-destructive", text: "text-destructive", badge: "destructive" },
  // Periférico que a loja não instalou: aparece na lista como ausente, em tom
  // neutro, e NÃO acende o badge geral. Só falha o que existe.
  absent: { label: "Não instalado", dot: "bg-muted-foreground/40", text: "text-muted-foreground", badge: "outline" },
  // A resposta existe, mas quem a tem é a estação — a sonda desta página
  // preenche assim que responde. Fingir verde antes disso era o defeito do
  // adapter "simulated".
  deferred: { label: "Na estação", dot: "bg-muted-foreground/60", text: "text-muted-foreground", badge: "outline" },
};

function meta(status: string): StatusMeta {
  return STATUS_META[status] || { label: status || "—", dot: "bg-muted-foreground", text: "text-muted-foreground", badge: "outline" };
}
</script>

<template>
  <UiPopover>
    <UiPopoverTrigger as-child>
      <button
        v-if="compact"
        type="button"
        class="grid size-10 place-items-center rounded-md text-primary-foreground/80 transition hover:bg-primary-foreground/10 hover:text-primary-foreground"
        :aria-label="`Saúde do terminal: ${overall.label}`"
        :title="`${pos.terminal_label}: ${overall.label}`"
      >
        <span class="relative grid size-5 place-items-center">
          <Icon name="lucide:monitor" class="size-5" />
          <span class="absolute -bottom-0.5 -right-1 size-2 rounded-full ring-2 ring-primary" :class="overall.dot" />
        </span>
      </button>
      <UiButton v-else variant="ghost" size="sm" class="gap-2 text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground" :aria-label="`Saúde do terminal: ${overall.label}`">
        <span class="size-2 rounded-full" :class="overall.dot" />
        <span class="font-medium">{{ pos.terminal_label }}</span>
        <Icon name="lucide:chevron-down" class="size-3.5 opacity-60" />
      </UiButton>
    </UiPopoverTrigger>
    <UiPopoverContent :align="compact ? 'start' : 'end'" :side="compact ? 'right' : 'bottom'" class="w-72 p-0">
      <div class="border-b p-3">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-semibold">Saúde do terminal</span>
          <UiBadge :variant="overall.badge">{{ overall.label }}</UiBadge>
        </div>
        <p class="text-xs text-muted-foreground">{{ pos.terminal_label }}</p>
      </div>
      <ul class="grid gap-0.5 p-2">
        <li
          v-for="row in rows"
          :key="row.key"
          class="grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-md px-2 py-1.5"
        >
          <span class="size-2 rounded-full" :class="meta(row.status).dot" />
          <div class="min-w-0">
            <p class="text-sm font-medium leading-tight">{{ row.label }}</p>
            <p v-if="row.message" class="text-xs text-muted-foreground">{{ row.message }}</p>
          </div>
          <span class="text-xs font-semibold" :class="meta(row.status).text">{{ meta(row.status).label }}</span>
        </li>
      </ul>
      <!-- Remediação: o card não termina no diagnóstico. Só existe onde existe
           agente; num balcão de gaveta com chave não há o que sondar. -->
      <div v-if="agentConfigured" class="grid gap-2 border-t p-3">
        <p v-if="agentDown" class="text-xs text-muted-foreground">
          Reinicie o agente na estação do balcão. Depois de qualquer mudança na
          configuração do terminal, o agente precisa ser reiniciado de novo.
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <UiButton type="button" variant="outline" size="xs" class="gap-1" :disabled="checking" @click="check">
            <Icon name="lucide:refresh-cw" class="size-3.5" :class="checking ? 'animate-spin' : ''" />
            Testar de novo
          </UiButton>
          <a
            v-if="terminalAdminUrl"
            class="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            :href="terminalAdminUrl"
            target="_blank"
            rel="noopener"
          >
            Configuração do terminal
          </a>
        </div>
      </div>
    </UiPopoverContent>
  </UiPopover>
</template>
