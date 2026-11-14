<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import type {
  Action,
  IFoodNegotiationAlternative,
  IFoodNegotiationProjection,
} from "~/generated/ordersContract";
import { parseMoneyCell } from "../../../operator-kit/app/presentation/gridEdit";
import { moneyInput } from "../../../operator-kit/app/presentation/custody";

const props = defineProps<{
  orderRef: string;
  negotiations?: readonly IFoodNegotiationProjection[];
}>();
const emit = defineEmits<{ refresh: []; "dirty-change": [value: boolean] }>();
const intention = useOrderIntention();
type Draft = {
  decision: string;
  reason: string;
  detail: string;
  /** Contraproposta: qual alternativa, o valor digitado (reais) ou o tempo e o motivo. */
  alternativeId: string;
  amount: string;
  minutes: string;
  timeReason: string;
  confirmed: boolean;
  revision: string;
  busy: boolean;
  uncertain: boolean;
  error: string;
  sent: boolean;
  action?: Action;
};
const drafts = reactive<Record<string, Draft>>({});
function draft(id: string): Draft {
  return (drafts[id] ??= {
    decision: "",
    reason: "",
    detail: "",
    alternativeId: "",
    amount: "",
    minutes: "",
    timeReason: "",
    confirmed: false,
    revision: "",
    busy: false,
    uncertain: false,
    error: "",
    sent: false,
  });
}
function actionFor(item: IFoodNegotiationProjection) {
  return item.actions.find((action) => action.ref === draft(item.id).decision);
}
function choose(item: IFoodNegotiationProjection, value: string) {
  const d = draft(item.id);
  if (d.busy || d.uncertain || d.sent) return;
  Object.assign(d, {
    decision: value,
    reason: "",
    detail: "",
    // Uma alternativa só: já vem escolhida (o óbvio não se pergunta).
    alternativeId:
      value === "alternative" && item.alternatives.length === 1
        ? item.alternatives[0]!.id
        : "",
    amount: "",
    minutes: "",
    timeReason: "",
    confirmed: false,
    error: "",
    revision: String(
      item.actions.find((a) => a.ref === value)?.payload_schema.base_revision ||
        "",
    ),
  });
}
function reasonLabel(value: string) {
  return (
    (
      {
        HIGH_STORE_DEMAND: "Alta demanda na loja",
        UNKNOWN_ISSUE: "Problema não identificado",
        CUSTOMER_SATISFACTION: "Satisfação do cliente",
        INVENTORY_CHECK: "Conferência de estoque",
        SYSTEM_ISSUE: "Problema no sistema",
        WRONG_ORDER: "Pedido incorreto",
        PRODUCT_QUALITY: "Qualidade do produto",
        LATE_DELIVERY: "Atraso na entrega",
        CUSTOMER_REQUEST: "Solicitação do cliente",
        ORDER_DELIVERED: "Pedido entregue",
      } as Record<string, string>
    )[value] || value
  );
}
function reasons(item: IFoodNegotiationProjection) {
  const decision = draft(item.id).decision;
  if (decision === "alternative") return [];
  return decision === "accept" ? item.accept_reasons : item.reject_reasons;
}
function isMoney(alternative?: IFoodNegotiationAlternative) {
  return alternative?.type === "REFUND" || alternative?.type === "BENEFIT";
}
function chosenAlternative(item: IFoodNegotiationProjection) {
  const id = draft(item.id).alternativeId;
  return item.alternatives.find((alternative) => alternative.id === id);
}
function alternativeOption(alternative: IFoodNegotiationAlternative) {
  return isMoney(alternative)
    ? `${alternative.label} (até ${alternative.max_amount_display})`
    : alternative.label;
}
function chooseAlternative(item: IFoodNegotiationProjection, value: string) {
  Object.assign(draft(item.id), {
    alternativeId: value,
    amount: "",
    minutes: "",
    timeReason: "",
    confirmed: false,
  });
}
/** Centavos do valor digitado; null quando vazio ou ilegível. */
function amountQ(item: IFoodNegotiationProjection) {
  return parseMoneyCell(draft(item.id).amount);
}
/** O que impede a contraproposta de seguir, dito para o operador; "" quando pronta. */
function alternativeProblem(item: IFoodNegotiationProjection) {
  const alternative = chosenAlternative(item);
  if (!alternative) return "Escolha a contraproposta.";
  const d = draft(item.id);
  if (isMoney(alternative)) {
    if (!d.amount.trim()) return `Informe o valor, até ${alternative.max_amount_display}.`;
    const cents = amountQ(item);
    if (cents === null || cents <= 0 || cents > alternative.max_amount_q)
      return `Informe um valor de R$ 0,01 até ${alternative.max_amount_display}.`;
    return "";
  }
  if (!alternative.minutes_options.includes(Number(d.minutes)))
    return "Escolha quantos minutos a mais.";
  if (!alternative.reason_options.some((option) => option.value === d.timeReason))
    return "Escolha o motivo do tempo a mais.";
  return "";
}
/** "reembolso de R$ 5,00" / "mais 20 minutos": o que vai ao iFood, numa frase. */
function alternativeSummary(item: IFoodNegotiationProjection) {
  const alternative = chosenAlternative(item);
  if (!alternative || alternativeProblem(item)) return "";
  if (isMoney(alternative)) {
    const noun = alternative.type === "REFUND" ? "reembolso" : "benefício";
    return `${noun} de R$ ${moneyInput(amountQ(item) ?? 0)}`;
  }
  return `mais ${draft(item.id).minutes} minutos`;
}
function changed(item: IFoodNegotiationProjection) {
  return (
    draft(item.id).revision !==
    String(actionFor(item)?.payload_schema.base_revision || "")
  );
}
/** A primeira negociação que ainda pede resposta: a decisão dela é o controle que
 *  recebe o foco quando o aviso traz o operador até aqui (`useNextFocus` da página). */
const firstOpenId = computed(
  () =>
    props.negotiations?.find(
      (item) => item.can_respond && !draft(item.id).sent,
    )?.id,
);
function canSend(item: IFoodNegotiationProjection) {
  const d = draft(item.id);
  const validReason =
    d.decision === "alternative"
      ? !alternativeProblem(item)
      : (d.decision === "accept" && !reasons(item).length) ||
        reasons(item).includes(d.reason);
  return (
    item.can_respond &&
    !!actionFor(item)?.enabled &&
    !!d.decision &&
    validReason &&
    d.confirmed &&
    !changed(item) &&
    !d.busy &&
    !d.sent &&
    !d.uncertain
  );
}
function consequence(item: IFoodNegotiationProjection) {
  if (draft(item.id).decision === "alternative") {
    const summary = alternativeSummary(item);
    return summary
      ? `Enviar ao iFood a contraproposta: ${summary}. O cliente decide se aceita, e o resultado chega pelo iFood.`
      : "";
  }
  const projected = actionFor(item)?.confirmation.description;
  if (typeof projected === "string" && projected) return projected;
  return draft(item.id).decision === "accept"
    ? "Aceitar autoriza o iFood a aplicar a solicitação descrita acima, incluindo cancelamento ou reembolso quando previstos."
    : "Recusar envia sua decisão ao iFood. A resolução será confirmada pela plataforma.";
}
function requestLabel(value: string) {
  return (
    (
      {
        CANCELLATION: "Cancelamento",
        PARTIAL_CANCELLATION: "Cancelamento parcial",
        REFUND: "Reembolso",
      } as Record<string, string>
    )[value] || "Solicitação do cliente"
  );
}
function dateLabel(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Prazo não informado";
  // "08/10 às 07:49": o ano e os segundos não ajudam a decidir (dono, 08/10/2026).
  const day = parsed.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  const time = parsed.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${day} às ${time}`;
}
function timeoutLabel(value: string) {
  return (
    (
      {
        ACCEPT_CANCELLATION:
          "O iFood informa que aceitará o cancelamento ao vencer o prazo.",
        REJECT_CANCELLATION:
          "O iFood informa que recusará o cancelamento ao vencer o prazo.",
        VOID: "O iFood informa que não aplicará uma ação automática ao vencer o prazo.",
      } as Record<string, string>
    )[value] ||
    "A consequência do vencimento não foi informada. Confira no iFood."
  );
}
function safeEvidence(url: string) {
  const proxy = `/api/v1/backstage/orders/${encodeURIComponent(props.orderRef)}/ifood-handshake-evidence/?`;
  if (url.startsWith(proxy)) return true;
  try {
    return new URL(url).protocol === "https:";
  } catch {
    return false;
  }
}
function alternativeBody(item: IFoodNegotiationProjection) {
  const d = draft(item.id);
  const alternative = chosenAlternative(item);
  return isMoney(alternative)
    ? { alternative_id: d.alternativeId, amount_q: amountQ(item) }
    : {
        alternative_id: d.alternativeId,
        minutes: Number(d.minutes),
        reason: d.timeReason,
      };
}
async function submit(item: IFoodNegotiationProjection, retry = false) {
  const d = draft(item.id);
  if (d.busy || (retry ? !d.uncertain : !canSend(item))) return;
  if (!retry) d.action = actionFor(item);
  d.busy = true;
  d.error = "";
  try {
    await intention.executePath(
      `${props.orderRef}:ifood-handshake:${item.id}`,
      `/api/v1/backstage/orders/${encodeURIComponent(props.orderRef)}/ifood-handshake/`,
      d.action,
      d.decision === "alternative"
        ? alternativeBody(item)
        : {
            reason: d.reason,
            detail_reason: d.decision === "accept" ? d.detail.trim() : "",
          },
    );
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
  } finally {
    d.busy = false;
  }
}
const dirty = computed(() =>
  Object.values(drafts).some((d) => !!d.decision && !d.sent),
);
watch(dirty, (value) => emit("dirty-change", value), { immediate: true });
watch(
  () => props.orderRef,
  () => {
    for (const key of Object.keys(drafts)) Reflect.deleteProperty(drafts, key);
  },
);
</script>

<template>
  <!-- Card próprio, logo abaixo do card do pedido (dono, 08/10/2026): dentro do
       resumo, o título colava nas linhas. O id e o data-* são o alvo dos links da
       Fila, do aviso com prazo e do e2e. -->
  <NuxtCard
    v-if="negotiations?.length"
    id="ifood-negotiations"
    data-ifood-negotiations
    data-focus-target="ifood-negotiations"
    class="scroll-mt-4 outline-none"
  >
    <div class="flex flex-col gap-3">
      <h2 class="op-title">Negociações iFood</h2>
      <div class="grid gap-4">
      <template v-for="(item, negotiationIndex) in negotiations" :key="item.id">
        <NuxtSeparator v-if="negotiationIndex > 0" />
        <div :data-dispute-id="item.id">
          <div class="space-y-3">
            <h3 class="text-sm font-medium">{{ requestLabel(item.action) }}</h3>
            <p class="whitespace-pre-wrap break-words">
              {{ item.message || "Solicitação recebida do iFood." }}
            </p>
            <p class="text-sm text-muted-foreground">
              Prazo: {{ dateLabel(item.expires_at) }}
            </p>
            <p class="text-sm">{{ timeoutLabel(item.timeout_action) }}</p>
            <ul v-if="item.items.length" class="list-inside list-disc text-sm">
              <li v-for="(line, index) in item.items" :key="index">{{ line }}</li>
            </ul>
            <div class="flex flex-wrap gap-3 text-sm">
              <NuxtButton
                v-for="(url, index) in item.evidence_urls.filter(safeEvidence)"
                :key="url"
                :to="url"
                target="_blank"
                rel="noopener noreferrer"
                color="neutral"
                variant="ghost"
                :label="`Evidência ${index + 1}`"
                trailing-icon="i-lucide-external-link"
              />
            </div>
            <!-- O iFood ofereceu contraproposta, mas nenhuma de um tipo que o Gestor
                 sabe enviar: aí, e só aí, a saída é o canal do iFood. -->
            <p
              v-if="item.alternatives_available && !item.alternatives.length"
              class="text-sm text-muted-foreground"
            >
              O iFood ofereceu uma contraproposta que o Gestor não envia. Para
              usá-la, use o canal do iFood.
            </p>
            <NuxtAlert
              v-if="item.response_notice"
              color="info"
              variant="subtle"
              :description="item.response_notice"
            />
            <NuxtAlert
              v-if="draft(item.id).sent"
              color="success"
              variant="subtle"
              icon="i-lucide-check"
              description="Resposta registrada para envio. Aguarde a confirmação do iFood."
            />
            <NuxtForm
              v-if="item.can_respond && !draft(item.id).sent"
              :state="draft(item.id)"
              class="space-y-3"
              @submit="submit(item)"
            >
              <fieldset
                :disabled="draft(item.id).busy || draft(item.id).uncertain"
                class="space-y-3"
              >
                <legend class="text-sm font-medium">Escolha sua resposta</legend>
                <NuxtFormField label="Decisão">
                  <NuxtSelect
                    class="w-full"
                    :data-focus-control="item.id === firstOpenId ? '' : undefined"
                    :model-value="draft(item.id).decision || undefined"
                    placeholder="Selecione uma decisão"
                    :items="
                      item.actions.map((action) => ({
                        label:
                          action.ref === 'accept'
                            ? 'Aceitar solicitação'
                            : action.ref === 'alternative'
                              ? 'Fazer contraproposta'
                              : 'Recusar solicitação',
                        value: action.ref,
                        disabled: !action.enabled,
                      }))
                    "
                    @update:model-value="choose(item, String($event))"
                  />
                </NuxtFormField>
                <NuxtFormField
                  v-if="draft(item.id).decision && reasons(item).length"
                  label="Motivo informado pelo iFood"
                >
                  <NuxtSelect
                    :model-value="draft(item.id).reason || undefined"
                    class="w-full"
                    placeholder="Selecione um motivo"
                    :items="
                      reasons(item).map((reason) => ({
                        label: reasonLabel(reason),
                        value: reason,
                      }))
                    "
                    @update:model-value="
                      draft(item.id).reason = String($event ?? '');
                      draft(item.id).confirmed = false;
                    "
                  />
                </NuxtFormField>
                <template v-if="draft(item.id).decision === 'alternative'">
                  <NuxtFormField label="Contraproposta">
                    <NuxtSelect
                      class="w-full"
                      data-alternative-select
                      :model-value="draft(item.id).alternativeId || undefined"
                      placeholder="Selecione a contraproposta"
                      :items="
                        item.alternatives.map((alternative) => ({
                          label: alternativeOption(alternative),
                          value: alternative.id,
                        }))
                      "
                      @update:model-value="chooseAlternative(item, String($event ?? ''))"
                    />
                  </NuxtFormField>
                  <NuxtFormField
                    v-if="isMoney(chosenAlternative(item))"
                    label="Valor"
                    :hint="`até ${chosenAlternative(item)!.max_amount_display}`"
                  >
                    <NuxtInput
                      v-model="draft(item.id).amount"
                      class="w-full"
                      type="text"
                      inputmode="decimal"
                      icon="i-lucide-circle-dollar-sign"
                      data-alternative-amount
                      placeholder="0,00"
                      :aria-label="`Valor da contraproposta, até ${chosenAlternative(item)!.max_amount_display}`"
                      @update:model-value="draft(item.id).confirmed = false"
                    />
                  </NuxtFormField>
                  <template v-else-if="chosenAlternative(item)">
                    <NuxtFormField label="Tempo a mais">
                      <NuxtSelect
                        class="w-full"
                        data-alternative-minutes
                        :model-value="draft(item.id).minutes || undefined"
                        placeholder="Selecione os minutos"
                        :items="
                          chosenAlternative(item)!.minutes_options.map((minutes) => ({
                            label: `${minutes} minutos`,
                            value: String(minutes),
                          }))
                        "
                        @update:model-value="
                          draft(item.id).minutes = String($event ?? '');
                          draft(item.id).confirmed = false;
                        "
                      />
                    </NuxtFormField>
                    <NuxtFormField label="Motivo do tempo a mais">
                      <NuxtSelect
                        class="w-full"
                        data-alternative-reason
                        :model-value="draft(item.id).timeReason || undefined"
                        placeholder="Selecione um motivo"
                        :items="
                          chosenAlternative(item)!.reason_options.map((option) => ({
                            label: option.label,
                            value: option.value,
                          }))
                        "
                        @update:model-value="
                          draft(item.id).timeReason = String($event ?? '');
                          draft(item.id).confirmed = false;
                        "
                      />
                    </NuxtFormField>
                  </template>
                  <p
                    v-if="alternativeProblem(item)"
                    class="text-sm text-muted-foreground"
                  >
                    {{ alternativeProblem(item) }}
                  </p>
                </template>
                <NuxtFormField
                  v-if="draft(item.id).decision === 'accept'"
                  label="Detalhes adicionais"
                  hint="opcional"
                  :description="`${draft(item.id).detail.length}/250`"
                >
                  <NuxtTextarea
                    v-model="draft(item.id).detail"
                    class="w-full"
                    maxlength="250"
                    :rows="3"
                    @input="draft(item.id).confirmed = false"
                  />
                </NuxtFormField>
                <p
                  v-if="draft(item.id).decision && !actionFor(item)?.enabled"
                  class="text-sm"
                >
                  {{
                    actionFor(item)?.reason ||
                    "Esta resposta não está disponível."
                  }}
                </p>
                <NuxtAlert
                  v-if="draft(item.id).decision && changed(item)"
                  color="warning"
                  variant="subtle"
                  description="A negociação foi atualizada. Selecione novamente a decisão para revisar os dados atuais."
                />
                <NuxtCheckbox
                  v-if="draft(item.id).decision && consequence(item)"
                  v-model="draft(item.id).confirmed"
                  :label="`${consequence(item)} Confirmo esta consequência.`"
                />
              </fieldset>
              <NuxtAlert
                v-if="draft(item.id).error"
                color="error"
                variant="subtle"
                icon="i-lucide-triangle-alert"
                :description="draft(item.id).error"
              />
              <NuxtButton
                v-if="draft(item.id).uncertain"
                type="button"
                label="Verificar mesmo envio"
                :loading="draft(item.id).busy"
                :disabled="draft(item.id).busy"
                @click="submit(item, true)"
              />
              <NuxtButton
                v-else
                type="submit"
                label="Enviar resposta ao iFood"
                :loading="draft(item.id).busy"
                :disabled="!canSend(item)"
              />
            </NuxtForm>
          </div>
        </div>
      </template>
    </div>
    </div>
  </NuxtCard>
</template>
