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

// O aviso tem a cor do tom; o gesto que leva ao campo é botão (vermelho quando trava,
// neutro quando só pede atenção, com o ícone no tom).
const toneAlert: Record<ReceiptWarningTone, "success" | "warning" | "error"> = {
  ok: "success",
  watch: "warning",
  block: "error",
};
const toneIcon: Record<ReceiptWarningTone, string> = {
  ok: "text-success",
  watch: "text-warning",
  block: "text-destructive",
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
  <NuxtCard data-receipt-conference-panel>
    <div class="flex items-baseline justify-between gap-2">
      <p class="text-base font-semibold tnum">{{ ready }} de {{ total }} {{ total === 1 ? "conferido" : "conferidos" }}</p>
      <p class="text-sm font-medium tnum" :class="totalPending ? 'text-destructive' : 'text-success'">
        {{ totalPending ? `${totalPending} ${totalPending === 1 ? "pendência" : "pendências"}` : "sem pendência" }}
      </p>
    </div>
    <div class="mt-2 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
      <span class="h-full bg-success" :style="{ width: total ? `${(ready / total) * 100}%` : '0%' }" />
      <span class="h-full bg-destructive/70" :style="{ width: total ? `${(Math.min(pendingLineCount, total - ready) / total) * 100}%` : '0%' }" />
    </div>

    <dl class="mt-4 grid grid-cols-3 gap-3">
      <div><dt class="text-xs text-muted-foreground">Origem</dt><dd class="text-base font-semibold">{{ mode === "invoice" ? "NF" : "Sem NF" }}</dd></div>
      <div><dt class="text-xs text-muted-foreground">Valor</dt><dd class="text-base font-semibold tnum">{{ formatMoney(totalCostQ) }}</dd></div>
      <div><dt class="text-xs text-muted-foreground">Pendências</dt><dd class="text-base font-semibold tnum" :class="totalPending ? 'text-destructive' : 'text-success'">{{ totalPending }}</dd></div>
    </dl>

    <div v-if="blank" class="mt-4 rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground">
      Nada em conferência. Escaneie a NF da próxima entrega, ou lance sem NF.
    </div>

    <div v-else-if="hasBlockers" class="mt-4 space-y-2">
      <NuxtButton
        v-for="blocker in documentBlockers"
        :key="blocker"
        variant="outline"
        color="error"
        block
        icon="i-lucide-circle-alert"
        class="justify-start text-left whitespace-normal"
        :label="blocker"
        @click="emit('anchor', 'invoice')"
      />
      <NuxtButton
        v-for="blocker in supplierBlockers"
        :key="blocker"
        variant="outline"
        color="error"
        block
        icon="i-lucide-circle-alert"
        class="justify-start text-left whitespace-normal"
        :label="blocker"
        @click="emit('anchor', 'supplier')"
      />
      <NuxtButton
        v-if="volumesStep"
        variant="outline"
        color="error"
        block
        icon="i-lucide-circle-alert"
        class="justify-start text-left whitespace-normal"
        :label="volumesStep"
        @click="emit('anchor', 'volumes')"
      />
      <NuxtButton
        v-for="item in pendingLines"
        :key="`pending-${item.id}`"
        variant="outline"
        :color="item.tone === 'block' ? 'error' : 'neutral'"
        block
        class="justify-start text-left"
        @click="emit('line', item.id)"
      >
        <Icon name="lucide:circle-alert" class="size-4 shrink-0" :class="toneIcon[item.tone]" />
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold" :title="item.label">{{ item.label }}</span>
          <span class="block text-xs font-normal text-muted-foreground">{{ item.step }}</span>
        </span>
      </NuxtButton>
      <NuxtAlert
        v-for="(warning, index) in watchWarnings"
        :key="`watch-${warning.key}-${index}`"
        variant="subtle"
        :color="toneAlert[warning.tone]"
        :title="warning.label"
      />
    </div>

    <div v-if="!blank" class="mt-4 space-y-2 border-t border-border pt-4" data-receipt-confirm-panel>
      <!-- O botão nunca fica mudo: com pendência ele é contornado (prévia v4),
           tocável, e aponta para o que falta. -->
      <NuxtButton
        size="xl"
        variant="outline"
        :active="receiptReady"
        active-variant="solid"
        active-color="primary"
        block
        :icon="receiptReady ? 'i-lucide-package-check' : 'i-lucide-list-checks'"
        label="Confirmar entrada"
        :disabled="busy"
        :loading="busy"
        data-receipt-confirm
        @click="emit('confirm')"
      />
      <p v-if="!receiptReady && firstBlocker" class="flex items-start justify-center gap-1.5 text-sm text-muted-foreground">
        <Icon name="lucide:arrow-right" class="mt-0.5 size-3.5 shrink-0" />
        <span>
          {{ firstBlocker.step }}{{ firstBlocker.label ? ` em ${firstBlocker.label}` : "" }}<template v-if="totalPending > 1"> · e mais {{ totalPending - 1 }}</template>
        </span>
      </p>
      <NuxtButton
        variant="outline"
        color="neutral"
        block
        icon="i-lucide-notebook-pen"
        label="Ressalva geral"
        data-receipt-ressalva-open
        @click="emit('ressalva')"
      />
      <NuxtButton
        variant="outline"
        color="error"
        block
        icon="i-lucide-undo-2"
        label="Registrar devolução"
        :disabled="busy || !canReject"
        @click="emit('reject')"
      />
    </div>
  </NuxtCard>
</template>
