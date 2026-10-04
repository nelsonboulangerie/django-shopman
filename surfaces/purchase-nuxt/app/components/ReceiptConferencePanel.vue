<script setup lang="ts">
// O resumo da conferência: "4 de 7 conferidos · 2 pendências" com a barra, origem,
// valor e pendências, o que ainda segura a entrada (cada pendência é um GESTO que
// leva ao campo) e os dois atos finais: Confirmar entrada e Registrar devolução.
// No desktop mora na coluna da direita; no tablet, no pé da lista (v3 tablet, pino 4).
//
// C19 (V6): com a conferência por exceção na tela, as linhas pendentes NÃO se
// repetem aqui (o fluxo já as mostra); a Ressalva geral fica recolhida num botão.
import type { ReceiptBlocker, ReceiptDocumentAnchor, ReceiptWarningTone } from "~/types/purchase";
import { formatMoney } from "~/presentation/purchase";

export interface ConferencePendingLine {
  id: string;
  label: string;
  step: string;
  tone: ReceiptWarningTone;
}

const props = defineProps<{
  ready: number;
  total: number;
  totalPending: number;
  pendingLineCount: number;
  mode: "invoice" | "manual";
  totalCostQ: number;
  documentLabel: string;
  blank: boolean;
  documentBlockers: string[];
  supplierBlockers: string[];
  volumesStep: string;
  pendingLines: ConferencePendingLine[];
  watchWarnings: { key: string; label: string; tone: ReceiptWarningTone }[];
  receiptReady: boolean;
  firstBlocker: ReceiptBlocker | null;
  busy: boolean;
  canReject: boolean;
  note: string;
}>();

const emit = defineEmits<{
  confirm: [];
  reject: [];
  anchor: [anchor: ReceiptDocumentAnchor];
  line: [lineId: string];
  ressalva: [];
}>();

const toneClasses: Record<ReceiptWarningTone, string> = {
  ok: "border-success/25 bg-success/10 text-success",
  watch: "border-warning/30 bg-warning/10 text-warning",
  block: "border-destructive/30 bg-destructive/10 text-destructive",
};
const hasBlockers = computed(
  () =>
    props.documentBlockers.length ||
    props.supplierBlockers.length ||
    props.volumesStep ||
    props.pendingLines.length ||
    props.watchWarnings.length,
);
</script>

<template>
  <div class="rounded-xl border border-border bg-card p-4" data-receipt-conference-panel>
    <div class="flex items-baseline justify-between gap-2">
      <p class="op-title tnum">{{ ready }} de {{ total }} {{ total === 1 ? "conferido" : "conferidos" }}</p>
      <p class="op-label tnum" :class="totalPending ? 'text-destructive' : 'text-success'">
        {{ totalPending ? `${totalPending} ${totalPending === 1 ? "pendência" : "pendências"}` : "sem pendência" }}
      </p>
    </div>
    <div class="mt-2 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
      <span class="h-full bg-success" :style="{ width: total ? `${(ready / total) * 100}%` : '0%' }" />
      <span class="h-full bg-destructive/70" :style="{ width: total ? `${(Math.min(pendingLineCount, total - ready) / total) * 100}%` : '0%' }" />
    </div>

    <dl class="mt-4 grid grid-cols-3 gap-3">
      <div><dt class="op-micro text-muted-foreground">Origem</dt><dd class="op-title">{{ mode === "invoice" ? "NF" : "Sem NF" }}</dd></div>
      <div><dt class="op-micro text-muted-foreground">Valor</dt><dd class="op-title tnum">{{ formatMoney(totalCostQ) }}</dd></div>
      <div><dt class="op-micro text-muted-foreground">Pendências</dt><dd class="op-title tnum" :class="totalPending ? 'text-destructive' : 'text-success'">{{ totalPending }}</dd></div>
    </dl>

    <div v-if="blank" class="mt-4 rounded-lg border border-dashed border-border p-3 op-body text-muted-foreground">
      Nada em conferência. Escaneie a NF da próxima entrega, ou lance sem NF.
    </div>

    <div v-else-if="hasBlockers" class="mt-4 space-y-2">
      <button
        v-for="blocker in documentBlockers"
        :key="blocker"
        type="button"
        class="block min-h-control w-full min-w-0 rounded-lg border px-3 py-2 text-left op-label"
        :class="toneClasses.block"
        @click="emit('anchor', 'invoice')"
      >
        {{ blocker }}
      </button>
      <button
        v-for="blocker in supplierBlockers"
        :key="blocker"
        type="button"
        class="block min-h-control w-full min-w-0 rounded-lg border px-3 py-2 text-left op-label"
        :class="toneClasses.block"
        @click="emit('anchor', 'supplier')"
      >
        {{ blocker }}
      </button>
      <button
        v-if="volumesStep"
        type="button"
        class="block min-h-control w-full min-w-0 rounded-lg border px-3 py-2 text-left op-label"
        :class="toneClasses.block"
        @click="emit('anchor', 'volumes')"
      >
        {{ volumesStep }}
      </button>
      <button
        v-for="item in pendingLines"
        :key="`pending-${item.id}`"
        type="button"
        class="block min-h-control w-full min-w-0 rounded-lg border px-3 py-2 text-left"
        :class="toneClasses[item.tone]"
        @click="emit('line', item.id)"
      >
        <span class="block truncate op-label font-semibold">{{ item.label }}</span>
        <span class="block op-micro opacity-80">{{ item.step }}</span>
      </button>
      <div v-for="(warning, index) in watchWarnings" :key="`watch-${warning.key}-${index}`" class="rounded-lg border px-3 py-2 op-label" :class="toneClasses[warning.tone]">{{ warning.label }}</div>
    </div>

    <div v-if="!blank" class="mt-4 border-t border-border pt-4" data-receipt-confirm-panel>
      <!-- O botão nunca fica mudo: com pendência ele é tracejado (prévia v4),
           tocável, e aponta para o que falta. -->
      <button
        type="button"
        class="inline-flex h-14 w-full items-center justify-center gap-2 rounded-xl px-3 op-action disabled:opacity-50"
        :class="receiptReady ? 'bg-primary text-primary-foreground' : 'border-2 border-dashed border-primary/50 bg-background text-foreground hover:bg-accent'"
        :disabled="busy"
        @click="emit('confirm')"
      >
        <Icon :name="receiptReady ? 'lucide:package-check' : 'lucide:list-checks'" class="size-5" />
        Confirmar entrada
      </button>
      <p v-if="!receiptReady && firstBlocker" class="mt-2 flex items-start justify-center gap-1.5 op-label font-normal text-muted-foreground">
        <Icon name="lucide:arrow-right" class="mt-0.5 size-3.5 shrink-0" />
        <span>
          {{ firstBlocker.step }}{{ firstBlocker.label ? ` em ${firstBlocker.label}` : "" }}<template v-if="totalPending > 1"> · e mais {{ totalPending - 1 }}</template>
        </span>
      </p>
      <button
        type="button"
        class="mt-2 inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 op-label font-semibold hover:bg-accent"
        data-receipt-ressalva-open
        @click="emit('ressalva')"
      >
        <Icon name="lucide:notebook-pen" class="size-4" />
        Ressalva geral
      </button>
      <button
        type="button"
        class="mt-2 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 op-title text-destructive hover:bg-destructive/10 disabled:opacity-50"
        :disabled="busy || !canReject"
        @click="emit('reject')"
      >
        <Icon name="lucide:undo-2" class="size-5" />
        Registrar devolução
      </button>
    </div>
  </div>
</template>
