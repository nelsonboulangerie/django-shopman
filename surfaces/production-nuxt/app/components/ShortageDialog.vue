<script setup lang="ts">
// Material/order shortage modal. Renders the structured shortage envelope the API
// returns (409) when a start/finish/plan would consume more than is available, or
// leave committed orders uncovered.
//
// Falta de insumo (WP-F11, P1-14 e P1-24):
//   - na ABERTURA (`stage: "start"`) é aviso, não trava: "Falta 300 g de
//     manteiga", com "Pedir no Compras" e "Abrir assim mesmo". O padeiro decide
//     com a informação; abrir devolve a prova ao host (`open-anyway`).
//   - no FECHAMENTO (`stage: "finish"`) é trava, e a saída é a assinatura de quem
//     pode autorizar (Gerente ou Dono), ESCOLHIDO DA LISTA e com o próprio PIN ou
//     crachá, no `OperatorManagerAuth` de sempre (decisão 3 do dono, D-042; regra
//     de 28/10). Nada de "quem autorizou" em texto livre: o servidor assina a
//     prova com o nome de quem autorizou, e o host segue pelo `confirm` de sempre.
//
// Falta de encomenda: "Revisar quantidade" volta ao número digitado. Quando o
// servidor oferece "confirm" e a tela sabe fechar o lote curto (`allowShortLot`),
// o lote fecha com o que rendeu: a tela diz quanto falta para as encomendas e
// quais pedidos ficam descobertos (decisão 1 do dono, 23/11/2026).
import type { OperatorSession } from "../../../operator-kit/app/types/operator";
import type { ProductionShortageError } from "~/types/production";
import { authorizeProductionShortage } from "~/generated/productionContract";
import { formatQty } from "~/presentation/production";
import { materialShortageLine } from "~/presentation/shortage";

const props = defineProps<{
  shortage: ProductionShortageError | null;
  allowShortLot?: boolean;
}>();
// O modal some com animação depois de `shortage` virar null. Título e frase
// saem do último envelope não nulo, para a saída não piscar outro caso com
// "lote undefined" (beta 05/11).
const last = ref<ProductionShortageError | null>(props.shortage);
watch(
  () => props.shortage,
  (value) => {
    if (value) last.value = value;
  },
);
const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [reason: string, proof: string];
  "close-short-lot": [proof: string];
  "open-anyway": [proof: string];
  review: [];
}>();

const { attrsFor } = useOperatorAppLink();

const material = computed(() =>
  last.value?.code === "material_shortage" ? last.value : null,
);
const isMaterial = computed(() => material.value != null);
const opening = computed(() => material.value?.stage === "start");
function possibility(kind: string) {
  return last.value?.possibilities.find(
    (candidate) => candidate.kind === kind && candidate.enabled,
  );
}
const forcePossibility = computed(() => possibility("force"));
const retryPossibility = computed(() => possibility("retry"));
const purchasePossibility = computed(() =>
  isMaterial.value ? possibility("purchase") : undefined,
);
const openAnywayPossibility = computed(() =>
  opening.value
    ? last.value?.possibilities.find(
        (candidate) =>
          candidate.kind === "confirm" && candidate.enabled && candidate.proof,
      )
    : undefined,
);
// Falta algo comprado: aí o Compras é quem resolve. Massa e recheio a casa produz.
const boughtMissing = computed(() =>
  (material.value?.missing ?? []).some((item) => !item.produced_here),
);
const materialLines = computed(() =>
  (material.value?.missing ?? []).map((item) => ({
    sku: item.sku,
    line: materialShortageLine(item),
    detail: `precisa ${item.needed_display} · tem ${item.available_display}`,
  })),
);
const shortLotPossibility = computed(() =>
  props.allowShortLot && last.value?.code === "order_shortage"
    ? last.value.possibilities.find(
        (candidate) =>
          candidate.kind === "confirm" && candidate.enabled && candidate.proof,
      )
    : undefined,
);
const shortLot = computed(() => {
  const value = last.value;
  if (!shortLotPossibility.value || value?.code !== "order_shortage") return null;
  const missing = Math.max(0, Number(value.required) - Number(value.requested));
  const orders = value.orders ?? [];
  return {
    yielded: formatQty(value.requested),
    missing: `${missing === 1 ? "Falta" : "Faltam"} ${formatQty(String(missing))}`,
    orders,
    // Só o que é sempre verdade: a lista daqui e o aviso ao Gestor ainda saem de
    // réguas diferentes (#3457), então a tela não promete o aviso.
    outcome:
      Number(value.requested) > 0
        ? `O lote fecha com ${formatQty(value.requested)} e o pão entra no estoque.`
        : "O lote fecha sem nada para o estoque.",
  };
});

// Falta de encomenda forçada no Planejamento: quem tem a permissão escreve o motivo.
const overrideReason = ref("");
const canConfirmOrderOverride = computed(
  () =>
    Boolean(forcePossibility.value?.proof) && overrideReason.value.trim().length > 0,
);

// A assinatura da falta de insumo no fechamento.
const authorizers = computed(() => material.value?.authorizers ?? []);
const authOpen = ref(false);
// O fato do lote na frase do diálogo de assinatura: "Falta 300 g de manteiga."
const authDetail = computed(() =>
  materialLines.value.map((item) => `${item.line}.`).join(" "),
);
const authBusy = ref(false);
const authError = ref("");
const operatorName = computed(
  () =>
    useNuxtData<OperatorSession>("operator-session").data.value?.operator?.name ??
    "",
);

watch(
  () => props.shortage,
  () => {
    overrideReason.value = "";
    authOpen.value = false;
    authBusy.value = false;
    authError.value = "";
  },
);

const title = computed(() => {
  if (isMaterial.value) {
    return opening.value ? "Falta insumo para este lote" : "Falta insumo para fechar";
  }
  return shortLot.value ? "Rendeu menos que o encomendado" : "Quantidade não cobre pedidos";
});
const description = computed(() => {
  const ref = last.value?.work_order_ref;
  if (shortLot.value) {
    return `Rendeu ${shortLot.value.yielded}. ${shortLot.value.missing} para as encomendas.`;
  }
  if (isMaterial.value && opening.value) {
    return boughtMissing.value
      ? "Dá para abrir assim mesmo. Para fechar o lote, o Compras dá entrada no que falta ou a Gerente ou o Dono autoriza."
      : "Dá para abrir assim mesmo. Para fechar o lote, o que falta precisa ser produzido ou a Gerente ou o Dono autoriza.";
  }
  if (isMaterial.value && forcePossibility.value) {
    return "O estoque não tem o que este lote consome. Para fechar assim, a Gerente ou o Dono autoriza com o PIN.";
  }
  if (isMaterial.value) {
    return boughtMissing.value
      ? "O estoque não tem o que este lote consome. Peça ao Compras para dar entrada no que falta e tente de novo."
      : "O estoque não tem o que este lote consome. Produza o que falta e tente de novo.";
  }
  return `O lote ${ref} tem encomendas que dependem dele, e a quantidade informada não cobre todas.`;
});

function closeShortLot() {
  const proof = shortLotPossibility.value?.proof;
  if (proof) emit("close-short-lot", proof);
}

function openAnyway() {
  const proof = openAnywayPossibility.value?.proof;
  if (proof) emit("open-anyway", proof);
}

function confirmOrderOverride() {
  const reason = overrideReason.value.trim();
  if (forcePossibility.value?.proof && reason) {
    emit("confirm", reason, forcePossibility.value.proof);
  }
}

async function sign(credentials: { username?: string; pin?: string; badge?: string }) {
  const proof = forcePossibility.value?.proof;
  if (!proof || authBusy.value) return;
  authBusy.value = true;
  authError.value = "";
  try {
    const signed = await authorizeProductionShortage({
      override_proof: proof,
      ...credentials,
    });
    authOpen.value = false;
    emit("confirm", `Autorizado por ${signed.authorizer_name}, com PIN.`, signed.override_proof);
  } catch (err) {
    authError.value = httpErrorMessage(err, "Não deu para conferir a autorização. Tente de novo.");
  } finally {
    authBusy.value = false;
  }
}
</script>

<template>
  <NuxtModal
    :open="shortage != null && !authOpen"
    :title="title"
    :description="description"
    @update:open="(v: boolean) => emit('update:open', v)"
  >
    <template #body>
      <div class="flex flex-col gap-3">
        <ul
          v-if="material"
          class="divide-y rounded-md border text-sm"
          data-shortage-items
        >
          <li
            v-for="item in materialLines"
            :key="item.sku"
            class="flex flex-col gap-0.5 px-3 py-2"
            data-shortage-item
          >
            <span class="font-medium text-destructive">{{ item.line }}</span>
            <span class="tabular-nums text-muted-foreground">{{ item.detail }}</span>
          </li>
        </ul>
        <template v-else-if="shortLot">
          <ul class="divide-y rounded-md border text-sm" data-short-lot-orders>
            <li
              v-for="order in shortLot.orders"
              :key="order.ref"
              class="flex items-center justify-between gap-2 px-3 py-2"
              data-short-lot-order
            >
              <span class="font-medium">{{ order.ref }}</span>
              <span class="tabular-nums text-muted-foreground"
                >{{ formatQty(order.qty) }} un.</span
              >
            </li>
          </ul>
          <p class="text-sm" data-short-lot-outcome>
            {{ shortLot.outcome }}
          </p>
        </template>
        <template v-else-if="last && last.code === 'order_shortage'">
          <div class="rounded-md border bg-muted/40 p-3 text-sm">
            <p>
              Encomendado:
              <b class="tabular-nums">{{ last.required }}</b> un. ·
              informado: <b class="tabular-nums">{{ last.requested }}</b> un.
            </p>
            <p class="mt-1 text-muted-foreground">
              Pedidos: {{ last.order_refs.join(", ") }}
            </p>
          </div>
          <p v-if="!forcePossibility" class="text-sm">
            Confira a contagem e informe pelo menos
            <b class="tabular-nums">{{ last.required }}</b> un. Se saiu mesmo
            menos, nada foi registrado: avise quem cuida das encomendas antes de
            confirmar este lote.
          </p>
        </template>

        <NuxtFormField
          v-if="forcePossibility && !isMaterial"
          label="Motivo da autorização"
        >
          <NuxtTextarea
            v-model="overrideReason"
            :maxlength="500"
            :rows="3"
            required
            class="w-full"
            aria-label="Motivo para salvar abaixo das encomendas"
            placeholder="Por que salvar abaixo das encomendas"
          />
        </NuxtFormField>
      </div>
    </template>

    <template #footer>
      <div class="flex w-full flex-wrap justify-end gap-2">
        <template v-if="isMaterial">
          <NuxtButton
            v-if="retryPossibility && opening"
            color="neutral"
            variant="outline"
            :label="retryPossibility.label"
            data-shortage-review
            @click="emit('review')"
          />
          <NuxtButton
            v-else
            color="neutral"
            variant="outline"
            label="Cancelar"
            @click="emit('update:open', false)"
          />
          <NuxtButton
            v-if="purchasePossibility"
            :href="purchasePossibility.href"
            v-bind="attrsFor(purchasePossibility.href)"
            color="neutral"
            variant="outline"
            trailing-icon="i-lucide-external-link"
            :label="purchasePossibility.label"
            data-shortage-purchase
          />
          <NuxtButton
            v-if="openAnywayPossibility"
            color="primary"
            :label="openAnywayPossibility.label"
            data-shortage-open-anyway
            @click="openAnyway"
          />
          <NuxtButton
            v-if="forcePossibility"
            color="primary"
            :label="forcePossibility.label"
            data-shortage-authorize
            @click="authOpen = true"
          />
        </template>
        <template v-else-if="shortLotPossibility">
          <NuxtButton
            v-if="retryPossibility"
            color="neutral"
            variant="outline"
            :label="retryPossibility.label"
            data-short-lot-review
            @click="emit('review')"
          />
          <NuxtButton
            color="primary"
            :label="shortLotPossibility.label"
            data-short-lot-confirm
            @click="closeShortLot"
          />
        </template>
        <template v-else>
          <NuxtButton
            color="neutral"
            variant="outline"
            :label="retryPossibility ? 'Cancelar' : 'Entendi'"
            @click="emit('update:open', false)"
          />
          <NuxtButton
            v-if="retryPossibility"
            :color="forcePossibility ? 'neutral' : 'primary'"
            :variant="forcePossibility ? 'outline' : 'solid'"
            :label="retryPossibility.label"
            @click="emit('review')"
          />
          <NuxtButton
            v-if="forcePossibility"
            color="primary"
            :disabled="!canConfirmOrderOverride"
            :label="forcePossibility.label"
            @click="confirmOrderOverride"
          />
        </template>
      </div>
    </template>
  </NuxtModal>

  <!-- A assinatura da falta: quem autoriza escolhe o próprio nome e digita o PIN
       (ou passa o crachá). Quem fecha o lote continua sendo quem era. -->
  <OperatorManagerAuth
    :open="authOpen"
    action="production_shortage"
    :detail="authDetail"
    :operator-name="operatorName || undefined"
    :managers="authorizers"
    :busy="authBusy"
    :error="authError"
    @update:open="
      (value: boolean) => {
        if (!value && !authBusy) authOpen = false;
      }
    "
    @authorize="(username: string, pin: string) => sign({ username, pin })"
    @authorize-badge="(badge: string) => sign({ badge })"
  />
</template>
