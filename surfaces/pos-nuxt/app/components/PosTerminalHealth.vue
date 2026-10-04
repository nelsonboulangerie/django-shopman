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
  /**
   * `suite`: o item "Terminal" do pé do rail da suíte (onda V4): ícone, nome e o ponto
   * de atenção, na gramática do `RailSection` do kit. O painel ganha o Atualizar.
   */
  variant?: "suite" | "sheet";
  /** Suite: a Projection está sendo relida (o Atualizar gira). */
  refreshing?: boolean;
}>();

const emit = defineEmits<{ refresh: [] }>();

const posRef = computed(() => props.pos);
const { probe, checking, check, agentConfigured } = useAgentHealth(posRef);
// Rail estendido mostra rótulo, como os demais itens (verdade compartilhada do kit).
const { showLabels } = useRailState();

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
const overallStatus = computed(() => terminalOverallStatus(rows.value));
const overall = computed(() => meta(overallStatus.value));
const agentDown = computed(() => probe.value?.ok === false);

// A tela de configuração do terminal no Admin: é lá que mora o download do
// agente e a config da estação. Porta HUMANA do Admin (host próprio), não a base
// da API — quem clica aqui é o operador.
const adminOrigin = computed(() => String(useRuntimeConfig().public.adminBaseUrl || ""));
const terminalAdminUrl = computed(() => {
  if (!adminOrigin.value || !props.pos.danfe_screen_allowed) return "";
  return `${adminOrigin.value}/admin/pos/terminal/${encodeURIComponent(props.pos.terminal_ref)}/agent/`;
});

type StatusMeta = {
  label: string;
  dot: string;
  text: string;
  badge: "success" | "warning" | "destructive" | "outline";
};

const STATUS_META: Record<string, StatusMeta> = {
  ready: { label: "OK", dot: "bg-success", text: "text-success", badge: "success" },
  warning: { label: "Atenção", dot: "bg-warning", text: "text-warning", badge: "warning" },
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
      <!-- No rail o gatilho fala a gramática do `RailItem` (kit): mesmos tokens
           `rail-foreground`, mesma altura, rótulo no estado estendido. Era o
           único item do rail em `text-primary-foreground`: no tema claro os dois
           tokens coincidem (branco), no escuro `primary-foreground` vira o tom
           escuro do texto sobre a ação dourada — e o ícone sumia no bronze. -->
      <button
        v-if="variant === 'suite'"
        type="button"
        data-terminal-health-trigger
        data-rail-section
        class="relative flex w-16 flex-col items-center gap-[3px] rounded-[10px] px-0 pt-[7px] pb-1.5 text-center op-eyebrow leading-[13px] tracking-normal normal-case text-rail-foreground transition hover:bg-rail-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rail-foreground"
        :aria-label="`Terminal ${pos.terminal_label}: ${overall.label}`"
        :title="`${pos.terminal_label}: ${overall.label}`"
      >
        <Icon name="lucide:cpu" class="size-[22px]" aria-hidden="true" />
        <span>Terminal</span>
        <span
          v-if="overallStatus !== 'ready'"
          aria-hidden="true"
          class="absolute top-1.5 right-[17px] size-[9px] rounded-full ring-2 ring-rail"
          :class="overallStatus === 'error' ? 'bg-destructive' : 'bg-suite-badge'"
          data-terminal-health-attention
        />
      </button>
      <!-- No "Mais" da barra do polegar (V6-KIT, P27): uma linha do menu, com o estado escrito. -->
      <button
        v-else-if="variant === 'sheet'"
        type="button"
        data-terminal-health-trigger
        class="flex min-h-12 w-full items-center gap-3 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
        :aria-label="`Terminal ${pos.terminal_label}: ${overall.label}`"
      >
        <span class="relative grid size-5 shrink-0 place-items-center">
          <Icon name="lucide:cpu" class="size-5 text-muted-foreground" aria-hidden="true" />
          <span class="absolute -bottom-0.5 -right-1 size-2 rounded-full ring-2 ring-popover" :class="overall.dot" />
        </span>
        <span class="min-w-0 flex-1">Terminal</span>
        <span class="op-micro text-muted-foreground">{{ overall.label }}</span>
      </button>
      <button
        v-else-if="compact"
        type="button"
        data-terminal-health-trigger
        class="flex min-h-11 items-center rounded-md py-1 text-left text-rail-foreground/80 transition hover:bg-rail-foreground/10 hover:text-rail-foreground"
        :class="showLabels ? 'w-full gap-3 px-2.5' : 'w-11 justify-center'"
        :aria-label="`Saúde do terminal: ${overall.label}`"
        :title="showLabels ? undefined : `${pos.terminal_label}: ${overall.label}`"
      >
        <span class="relative grid size-5 shrink-0 place-items-center">
          <Icon name="lucide:monitor" class="size-5" />
          <span class="absolute -bottom-0.5 -right-1 size-2 rounded-full ring-2 ring-rail" :class="overall.dot" />
        </span>
        <span v-if="showLabels" class="min-w-0 text-sm leading-tight">Terminal · {{ overall.label }}</span>
      </button>
      <UiButton v-else variant="ghost" size="sm" class="gap-2 text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground" :aria-label="`Saúde do terminal: ${overall.label}`">
        <span class="size-2 rounded-full" :class="overall.dot" />
        <span class="font-medium">{{ pos.terminal_label }}</span>
        <Icon name="lucide:chevron-down" class="size-3.5 opacity-60" />
      </UiButton>
    </UiPopoverTrigger>
    <UiPopoverContent :align="variant === 'suite' ? 'end' : compact ? 'start' : 'end'" :side="variant === 'sheet' ? 'top' : compact || variant === 'suite' ? 'right' : 'bottom'" class="w-72 p-0">
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
           AGENTE — impressora ou gaveta por software. Num balcão sem nenhuma
           das duas não há o que sondar. -->
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
      <!-- Atualizar: relê a Projection do terminal (comandas, caixa, catálogo). O
           tempo real (SSE) e a reconexão já fazem isso sozinhos; aqui é a mão. -->
      <div v-if="variant === 'suite' || variant === 'sheet'" class="border-t p-2">
        <UiButton
          type="button"
          variant="ghost"
          size="sm"
          class="w-full justify-start gap-2"
          :disabled="refreshing"
          data-terminal-refresh
          @click="emit('refresh')"
        >
          <Icon name="lucide:refresh-cw" class="size-4" :class="refreshing ? 'animate-spin motion-reduce:animate-none' : ''" />
          Atualizar a tela
        </UiButton>
      </div>
    </UiPopoverContent>
  </UiPopover>
</template>
