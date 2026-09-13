<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import type { Action, IFoodNegotiationProjection } from "~/generated/ordersContract";

const props = defineProps<{ orderRef: string; negotiations?: readonly IFoodNegotiationProjection[] }>();
const emit = defineEmits<{ refresh: []; "dirty-change": [value: boolean] }>();
const intention = useOrderIntention();
type Draft = { decision: string; reason: string; detail: string; confirmed: boolean; revision: string; busy: boolean; uncertain: boolean; error: string; sent: boolean; action?: Action };
const drafts = reactive<Record<string, Draft>>({});
function draft(id: string): Draft {
  return drafts[id] ??= { decision: "", reason: "", detail: "", confirmed: false, revision: "", busy: false, uncertain: false, error: "", sent: false };
}
function actionFor(item: IFoodNegotiationProjection) {
  return item.actions.find(action => action.ref === draft(item.id).decision);
}
function choose(item: IFoodNegotiationProjection, value: string) {
  const d = draft(item.id);
  if (d.busy || d.uncertain || d.sent) return;
  Object.assign(d, { decision: value, reason: "", detail: "", confirmed: false, error: "", revision: String(item.actions.find(a => a.ref === value)?.payload_schema.base_revision || "") });
}
function reasonLabel(value: string) {
  return ({ HIGH_STORE_DEMAND: "Alta demanda na loja", UNKNOWN_ISSUE: "Problema não identificado", CUSTOMER_SATISFACTION: "Satisfação do cliente", INVENTORY_CHECK: "Conferência de estoque", SYSTEM_ISSUE: "Problema no sistema", WRONG_ORDER: "Pedido incorreto", PRODUCT_QUALITY: "Qualidade do produto", LATE_DELIVERY: "Atraso na entrega", CUSTOMER_REQUEST: "Solicitação do cliente", ORDER_DELIVERED: "Pedido entregue" } as Record<string, string>)[value] || value;
}
function reasons(item: IFoodNegotiationProjection) {
  return draft(item.id).decision === "accept" ? item.accept_reasons : item.reject_reasons;
}
function changed(item: IFoodNegotiationProjection) {
  return draft(item.id).revision !== String(actionFor(item)?.payload_schema.base_revision || "");
}
function canSend(item: IFoodNegotiationProjection) {
  const d = draft(item.id);
  const validReason = d.decision === "accept" && !reasons(item).length || reasons(item).includes(d.reason);
  return item.can_respond && !!actionFor(item)?.enabled && !!d.decision && validReason && d.confirmed && !changed(item) && !d.busy && !d.sent && !d.uncertain;
}
function consequence(item: IFoodNegotiationProjection) {
  const projected = actionFor(item)?.confirmation.description;
  if (typeof projected === "string" && projected) return projected;
  return draft(item.id).decision === "accept"
    ? "Aceitar autoriza o iFood a aplicar a solicitação descrita acima, incluindo cancelamento ou reembolso quando previstos."
    : "Recusar envia sua decisão ao iFood. A resolução será confirmada pela plataforma.";
}
function requestLabel(value: string) {
  return ({ CANCELLATION: "Cancelamento", PARTIAL_CANCELLATION: "Cancelamento parcial", REFUND: "Reembolso" } as Record<string, string>)[value] || "Solicitação do cliente";
}
function dateLabel(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Prazo não informado" : parsed.toLocaleString("pt-BR");
}
function timeoutLabel(value: string) {
  return ({ ACCEPT_CANCELLATION: "O iFood informa que aceitará o cancelamento ao vencer o prazo.", REJECT_CANCELLATION: "O iFood informa que recusará o cancelamento ao vencer o prazo.", VOID: "O iFood informa que não aplicará uma ação automática ao vencer o prazo." } as Record<string, string>)[value]
    || "A consequência do vencimento não foi informada. Confira no iFood.";
}
function safeEvidence(url: string) {
  const proxy = `/api/v1/backstage/orders/${encodeURIComponent(props.orderRef)}/ifood-handshake-evidence/?`;
  if (url.startsWith(proxy)) return true;
  try { return new URL(url).protocol === "https:"; } catch { return false; }
}
async function submit(item: IFoodNegotiationProjection, retry = false) {
  const d = draft(item.id);
  if (d.busy || (retry ? !d.uncertain : !canSend(item))) return;
  if (!retry) d.action = actionFor(item);
  d.busy = true;
  d.error = "";
  try {
    await intention.executePath(`${props.orderRef}:ifood-handshake:${item.id}`, `/api/v1/backstage/orders/${encodeURIComponent(props.orderRef)}/ifood-handshake/`, d.action,
      { reason: d.reason, detail_reason: d.decision === "accept" ? d.detail.trim() : "" });
    d.uncertain = false;
    d.sent = true;
    emit("refresh");
  } catch (error) {
    const failure = httpError(error);
    const outcome = (failure.data as { outcome?: string } | null)?.outcome;
    d.uncertain = outcome !== "not_applied";
    d.confirmed = false;
    d.error = d.uncertain
      ? "Não foi possível confirmar o envio. Verifique esta mesma resposta antes de escolher outra decisão."
      : "A resposta não foi aplicada. Atualize os dados e revise sua decisão antes de tentar novamente.";
    emit("refresh");
  } finally { d.busy = false; }
}
const dirty = computed(() => Object.values(drafts).some(d => !!d.decision && !d.sent));
watch(dirty, value => emit("dirty-change", value), { immediate: true });
watch(() => props.orderRef, () => { for (const key of Object.keys(drafts)) Reflect.deleteProperty(drafts, key); });
</script>

<template>
  <section v-if="negotiations?.length" id="ifood-negotiations" class="space-y-4 rounded-lg border p-4" data-ifood-negotiations>
    <h2 class="font-semibold">Negociações iFood</h2>
    <article v-for="item in negotiations" :key="item.id" class="space-y-3 rounded-md border p-3" :data-dispute-id="item.id">
      <h3 class="text-sm font-medium">{{ requestLabel(item.action) }}</h3>
      <p class="whitespace-pre-wrap break-words">{{ item.message || 'Solicitação recebida do iFood.' }}</p>
      <p class="text-sm text-muted-foreground">Prazo: {{ dateLabel(item.expires_at) }}</p>
      <p class="text-sm">{{ timeoutLabel(item.timeout_action) }}</p>
      <ul v-if="item.items.length" class="list-inside list-disc text-sm"><li v-for="(line, index) in item.items" :key="index">{{ line }}</li></ul>
      <div class="flex flex-wrap gap-3 text-sm">
        <a v-for="(url, index) in item.evidence_urls.filter(safeEvidence)" :key="url" :href="url" target="_blank" rel="noopener noreferrer" class="min-h-control inline-flex items-center text-primary underline">Evidência {{ index + 1 }}</a>
      </div>
      <p v-if="item.alternatives_available" class="text-sm text-muted-foreground">Há contrapropostas disponíveis. Para negociar uma alternativa, use o canal do iFood.</p>
      <p v-if="item.response_notice" role="status" class="text-sm">{{ item.response_notice }}</p>
      <p v-if="draft(item.id).sent" role="status" class="text-sm">Resposta registrada para envio. Aguarde a confirmação do iFood.</p>
      <form v-if="item.can_respond && !draft(item.id).sent" class="space-y-3" @submit.prevent="submit(item)">
        <fieldset :disabled="draft(item.id).busy || draft(item.id).uncertain" class="space-y-3">
          <legend class="text-sm font-medium">Escolha sua resposta</legend>
          <label class="block text-sm">Decisão
            <select :value="draft(item.id).decision" class="mt-1 block min-h-control w-full rounded-md border bg-background p-2" @change="choose(item, ($event.target as HTMLSelectElement).value)">
              <option value="">Selecione uma decisão</option>
              <option v-for="action in item.actions" :key="action.ref" :value="action.ref" :disabled="!action.enabled">{{ action.ref === 'accept' ? 'Aceitar solicitação' : 'Recusar solicitação' }}</option>
            </select>
          </label>
          <label v-if="draft(item.id).decision && reasons(item).length" class="block text-sm">Motivo informado pelo iFood
            <select v-model="draft(item.id).reason" class="mt-1 block min-h-control w-full rounded-md border bg-background p-2" @change="draft(item.id).confirmed = false">
              <option value="">Selecione um motivo</option>
              <option v-for="reason in reasons(item)" :key="reason" :value="reason">{{ reasonLabel(reason) }}</option>
            </select>
          </label>
          <label v-if="draft(item.id).decision === 'accept'" class="block text-sm">Detalhes adicionais (opcional)
            <textarea v-model="draft(item.id).detail" maxlength="250" rows="3" class="mt-1 block w-full rounded-md border bg-background p-2" @input="draft(item.id).confirmed = false" />
            <span class="text-muted-foreground">{{ draft(item.id).detail.length }}/250</span>
          </label>
          <p v-if="draft(item.id).decision && !actionFor(item)?.enabled" class="text-sm">{{ actionFor(item)?.reason || 'Esta resposta não está disponível.' }}</p>
          <p v-if="draft(item.id).decision && changed(item)" role="alert" class="text-sm">A negociação foi atualizada. Selecione novamente a decisão para revisar os dados atuais.</p>
          <label v-if="draft(item.id).decision" class="flex items-start gap-2 text-sm">
            <input v-model="draft(item.id).confirmed" type="checkbox" class="mt-1" />
            <span>{{ consequence(item) }} Confirmo esta consequência.</span>
          </label>
        </fieldset>
        <p v-if="draft(item.id).error" role="alert" class="text-sm text-destructive">{{ draft(item.id).error }}</p>
        <button v-if="draft(item.id).uncertain" type="button" class="min-h-control rounded-md border px-3 py-2 text-sm" :disabled="draft(item.id).busy" @click="submit(item, true)">Verificar mesmo envio</button>
        <button v-else type="submit" class="min-h-control rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50" :disabled="!canSend(item)">{{ draft(item.id).busy ? 'Enviando…' : 'Enviar resposta ao iFood' }}</button>
      </form>
    </article>
  </section>
</template>
