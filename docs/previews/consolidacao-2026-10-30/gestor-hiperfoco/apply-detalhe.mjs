// PRÉVIA (hiperfoco no detalhe do pedido, 31/10/2026). Aplica numa CÓPIA de
// surfaces/orders-nuxt; nunca em surfaces/. Âncoras exatas, falha alto.
// Uso: node apply-detalhe.mjs <cópia>/surfaces/orders-nuxt
import fs from "node:fs";
import path from "node:path";

const root = process.argv[2];
if (!root) throw new Error("uso: node apply-detalhe.mjs <dir do orders-nuxt>");

function patch(rel, pairs) {
  const file = path.join(root, rel);
  let src = fs.readFileSync(file, "utf8");
  if (src.includes("PRÉVIA detalhe")) return console.log(`já aplicado: ${rel}`);
  for (const [from, to] of pairs) {
    const n = src.split(from).length - 1;
    if (n !== 1) throw new Error(`${rel}: âncora achada ${n}x:\n${from.slice(0, 160)}`);
    src = src.replace(from, to);
  }
  fs.writeFileSync(file, src);
  console.log(`ok: ${rel}`);
}

patch("app/pages/[ref].vue", [
  // 1. Botão que não se aperta não fica no cabeçalho: o bloqueio já está escrito no topo
  //    do conteúdo, com o que dá para fazer (no celular, a base já escreve o motivo).
  [
    `        <NuxtButton
          v-else-if="primary"
          type="button"
          :icon="primary.icon.replace('lucide:', 'i-lucide-')"`,
    `        <NuxtButton
          v-else-if="primary && primary.enabled"
          type="button"
          :icon="primary.icon.replace('lucide:', 'i-lucide-')"`,
  ],
  // 2. O pagamento aparecia três vezes no celular (pílula, resumo, iFood): fica no resumo.
  [
    `            v-if="order.payment_method_label || stateInEveryWidth"
            class="flex flex-col gap-2.5"
            :class="stateInEveryWidth ? '' : 'md:hidden'"`,
    `            v-if="stateInEveryWidth"
            class="flex flex-col gap-2.5"`,
  ],
  [
    `            <div
              v-if="order.payment_method_label"
              class="flex flex-wrap items-center gap-2 md:hidden"
              data-detail-pills
            >`,
    `            <div
              v-if="false"
              class="flex flex-wrap items-center gap-2 md:hidden"
              data-detail-pills
            >`,
  ],
  // 3. O bloqueio diz o que dá para fazer, ali mesmo (reenviar o link, cancelar).
  [
    `              :description="order.advance_block_reason"
              data-detail-block`,
    `              :description="order.advance_block_reason"
              :actions="
                alertActions('error', [
                  order.can_resend_payment_link && {
                    label: 'Reenviar link de pagamento',
                    disabled: busy,
                    onClick: () => resendPaymentLink(),
                  },
                  order.can_cancel && {
                    label: order.cancel_requires_approval
                      ? 'Cancelar pedido (pede gerente)'
                      : 'Cancelar pedido',
                    disabled: busy,
                    onClick: () => openDialog('cancel'),
                  },
                ])
              "
              data-detail-block`,
  ],
  // 4. A nota da cozinha se edita enquanto a cozinha ainda pode usá-la; depois do pronto,
  //    só a leitura (a do kit). E sem nota, ela não ocupa a tela: um botão abre o editor.
  [
    `<template v-if="!outside.away.value" #kitchen-note>
          <NuxtCard as="section">
            <div class="flex flex-col gap-2">`,
    `<template v-if="!outside.away.value && noteEditable" #kitchen-note>
          <NuxtCard as="section">
            <NuxtButton
              v-if="!noteOpen && !notes && !order.kitchen_note"
              type="button"
              icon="i-lucide-plus"
              label="Nota para a cozinha"
              color="neutral"
              variant="ghost"
              data-hf-note-open
              @click="noteOpen = true"
            />
            <div v-else class="flex flex-col gap-2">`,
  ],
  [
    `const stateInEveryWidth = computed(() =>`,
    `// PRÉVIA detalhe: a nota da cozinha se edita até o pronto.
const noteEditable = computed(() =>
  ["new", "accepted", "preparing"].includes(order.value?.status ?? ""),
);
const noteOpen = ref(false);
// PRÉVIA detalhe: a situação numa frase, para quem atende o cliente ao telefone: o último
// fato, a hora dele e o que vem depois.
const NEXT_BY_STATUS: Record<string, (o: { fulfillment_type: string }) => string> = {
  new: () => "esperando o aceite",
  accepted: () => "o preparo ainda não começou",
  preparing: () => "na cozinha",
  ready: (o) => (o.fulfillment_type === "delivery" ? "esperando o entregador" : "esperando o cliente"),
  dispatched: () => "a caminho do cliente",
};
const situationLine = computed(() => {
  const o = order.value;
  if (!o) return "";
  const last = [...(o.timeline ?? [])].reverse().find((e) => e.event_type === "status_change");
  const at = last?.timestamp_display?.split(" às ")[1] ?? "";
  const head = last ? \`\${last.label}\${at ? \` às \${at}\` : ""}\` : o.status_label;
  const next = NEXT_BY_STATUS[o.status]?.(o) ?? "";
  return next ? \`\${head}: \${next}.\` : \`\${head}.\`;
});
const stateInEveryWidth = computed(() =>`,
  ],
  [
    `        <template #actions>
          <section
            v-if="stateInEveryWidth"`,
    `        <template #actions>
          <p class="op-title" data-hf-situacao>{{ situationLine }}</p>
          <section
            v-if="stateInEveryWidth"`,
  ],
]);

// 5. Avisos ao cliente: só o que foi ou devia ter sido enviado. "Não se aplica" não é
//    aviso; e "crítico" só acende quando o aviso crítico falhou ou não saiu.
patch("app/components/OrderNotificationReceipts.vue", [
  [
    `defineProps<{ receipts?: readonly NotificationReceiptProjection[] }>();`,
    `const props = defineProps<{ receipts?: readonly NotificationReceiptProjection[] }>();
// PRÉVIA detalhe: o que não se aplica (skipped) não é aviso ao cliente.
const shown = computed(() => (props.receipts ?? []).filter((r) => r.state !== "skipped"));
const noneLine = computed(() => {
  const reasons = [...new Set((props.receipts ?? []).map((r) => r.detail.replace(/\\.$/, "")).filter(Boolean))];
  if (!reasons.length || reasons.every((r) => r === "Este aviso não se aplica"))
    return "Nenhum aviso ao cliente se aplica a este pedido.";
  const why = reasons.filter((r) => r !== "Este aviso não se aplica").join("; ");
  return \`Nenhum aviso foi enviado ao cliente: \${why.charAt(0).toLowerCase()}\${why.slice(1)}.\`;
});`,
  ],
  // ... mas quem atende "não recebi o aviso" precisa da resposta: uma linha só, sem alarme.
  [
    `  <NuxtCard
    v-if="receipts?.length"`,
    `  <p
    v-if="!shown.length && receipts?.length"
    class="flex items-center gap-2 px-1 op-micro text-muted-foreground"
    data-hf-receipts-none
  >
    <Icon name="lucide:bell-off" class="size-3.5 shrink-0" />
    {{ noneLine }}
  </p>
  <NuxtCard
    v-if="shown.length"`,
  ],
  [`<OperatorCountChip :count="receipts.length" />`, `<OperatorCountChip :count="shown.length" />`],
  [`          v-for="(receipt, i) in receipts"`, `          v-for="(receipt, i) in shown"`],
  [
    `              v-if="receipt.critical"`,
    `              v-if="receipt.critical && (receipt.tone === 'danger' || receipt.tone === 'warning')"`,
  ],
]);
