<script setup lang="ts">
// O ENTREGADOR no painel do Balcão (dono, 13/10/2026): a encomenda de entrega da
// casa chama o entregador da TaOn daqui, como no Gestor. Tudo o que decide vem do
// servidor, o MESMO bloco e as MESMAS ações do Gestor:
//
// - o estado numa frase só, com o tom (`card.courier_label`/`courier_tone`):
//   "Entregador não chamado", "Procurando entregador", "Entregador a caminho da
//   loja", "Saiu para entrega", "Entregue", "Não atendida", "Sem resposta da TaOn";
// - quem vem (nome, telefone, veículo), o rastreio e o código, quando a TaOn diz;
// - **Chamar entregador** (ou **Chamar outro entregador**, depois de uma corrida
//   que não terminou): confirmação inline com a pergunta do servidor e a custódia
//   que sai com ele (troco da gaveta, maquininha), o mesmo corpo do Gestor;
// - **Chamar de novo**, dentro do aviso, quando a última chamada ficou sem
//   resposta: a confirmação é a do diálogo da casa, com a frase do servidor.
//
// Cancelar a corrida e registrar a volta do troco ou da maquininha ficam no Gestor
// (a frase do painel, `GESTOR_ONLY_COURIER_LINE`).
import type { OrderDetailAction } from "../../../operator-kit/app/types/orderDetail";
import {
  courierBadgeColor as badgeColor,
  courierCallLabel,
  GESTOR_ONLY_COURIER_LINE,
  custodyBody,
  noFreeMachineSentence,
  telHref,
  vehicleLine,
} from "~/presentation/courier";
import type { PreorderCard, PreorderCourier, PreorderEquipmentOption } from "~/types/preorders";
import { freeMachines, machinePhrase, moneyInput } from "../../../operator-kit/app/presentation/custody";

const props = defineProps<{
  courier: PreorderCourier;
  card: Pick<PreorderCard, "courier_label" | "courier_tone">;
  busy: boolean;
  dispatchAction?: OrderDetailAction;
  dispatchAgainAction?: OrderDetailAction;
  equipmentOptions?: PreorderEquipmentOption[];
}>();
const emit = defineEmits<{
  dispatch: [custody: { change_out?: string; equipment?: string[] }];
  dispatchAgain: [];
}>();

const driver = computed(() => (props.courier.driver?.name ? props.courier.driver : null));
const vehicle = computed(() => vehicleLine(props.courier.driver));
const noAnswer = computed(() => Boolean(props.courier.can_dispatch_again));

// ── Chamar: confirmação inline (a pergunta e a custódia) ──
const confirming = ref(false);
const question = computed(() => String(props.dispatchAction?.confirmation?.description ?? ""));
const custody = computed(() => props.courier.custody);
const asksChange = computed(() => (custody.value?.change_out_suggested_q ?? 0) > 0);
const asksMachine = computed(() => Boolean(custody.value?.needs_machine));
const free = computed(() => freeMachines(props.equipmentOptions ?? []));
const machineMissing = computed(() => asksMachine.value && !free.value.length);
const machineItems = computed(() => free.value.map((opt) => ({ value: opt.ref, label: opt.label })));
const changeOut = ref("");
const machineRef = ref("");

// A base da ação mudou (a corrida andou, outro balcão chamou): a confirmação
// armada com a leitura velha desarma.
watch(() => JSON.stringify(props.dispatchAction?.payload_schema), () => { confirming.value = false; });

function arm() {
  changeOut.value = asksChange.value ? moneyInput(custody.value?.change_out_suggested_q ?? 0) : "";
  machineRef.value = free.value[0]?.ref ?? "";
  confirming.value = true;
}
function confirmCall() {
  if (machineMissing.value) return;
  confirming.value = false;
  emit("dispatch", custodyBody(custody.value, { changeOut: changeOut.value, machineRef: machineRef.value }));
}

// ── Chamar de novo: o diálogo da casa, com a frase do servidor ──
const confirmAgain = useConfirm();
async function callAgain() {
  const go = await confirmAgain({
    tone: "primary",
    title: "Chamar o entregador de novo?",
    description: String(props.dispatchAgainAction?.confirmation?.description ?? ""),
    confirmLabel: "Chamar de novo",
    cancelLabel: "Voltar",
  });
  if (go) emit("dispatchAgain");
}
</script>

<template>
  <NuxtCard variant="soft" as="section" aria-label="Entregador" data-pos-courier>
    <div class="grid gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <h2 class="flex items-center gap-1.5 text-sm font-semibold">
          <Icon name="lucide:bike" class="size-4" aria-hidden="true" /> Entregador
        </h2>
        <NuxtBadge
          v-if="card.courier_label && !noAnswer"
          :color="badgeColor(card.courier_tone)"
          :label="card.courier_label"
          data-pos-courier-state
        />
      </div>

      <!-- A TaOn não respondeu à última chamada: cautela, não erro da casa. O gesto
           acompanha a cor do aviso. -->
      <NuxtAlert
        v-if="noAnswer"
        color="warning"
        variant="subtle"
        icon="i-lucide-circle-help"
        :title="courier.error?.message || 'A TaOn não respondeu à última chamada.'"
        data-pos-courier-no-answer
      >
        <template #actions>
          <NuxtButton
            type="button"
            color="warning"
            variant="outline"
            icon="i-lucide-refresh-cw"
            label="Chamar de novo"
            :disabled="busy || !dispatchAgainAction?.enabled"
            :title="dispatchAgainAction?.reason || undefined"
            data-pos-courier-again
            @click="callAgain"
          />
        </template>
      </NuxtAlert>
      <NuxtAlert
        v-else-if="courier.error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Falha ao abrir a corrida"
        :description="courier.error.message"
        data-pos-courier-error
      />

      <!-- Quem vem buscar, e o código que ele confere. -->
      <div v-if="driver || courier.confirmation_code" class="grid gap-1" data-pos-courier-driver>
        <p v-if="driver" class="flex items-center gap-1.5 text-sm font-medium">
          <Icon name="lucide:user" class="size-4 shrink-0 text-muted" aria-hidden="true" />
          <span class="min-w-0 break-words">{{ driver.name }}</span>
        </p>
        <p v-if="vehicle" class="flex items-center gap-1.5 text-sm text-muted">
          <Icon name="lucide:bike" class="size-4 shrink-0" aria-hidden="true" />
          <span class="min-w-0 break-words">{{ vehicle }}</span>
        </p>
        <p v-if="courier.confirmation_code" class="flex items-center gap-1.5 text-sm text-muted">
          <Icon name="lucide:key-round" class="size-4 shrink-0" aria-hidden="true" /> Código:
          <strong class="tabular-nums text-default">{{ courier.confirmation_code }}</strong>
        </p>
      </div>

      <!-- Ligar e acompanhar: botões com borda, alinhados à borda do bloco. -->
      <div v-if="driver?.phone || courier.tracking_url" class="flex flex-wrap gap-2" data-pos-courier-links>
        <NuxtButton
          v-if="driver?.phone"
          :to="telHref(driver.phone)"
          color="neutral"
          variant="outline"
          icon="i-lucide-phone"
          :label="driver.phone"
          :aria-label="`Ligar para ${driver.name}, ${driver.phone}`"
        />
        <NuxtButton
          v-if="courier.tracking_url"
          :to="courier.tracking_url"
          target="_blank"
          color="neutral"
          variant="outline"
          icon="i-lucide-map-pin"
          trailing-icon="i-lucide-external-link"
          label="Acompanhar corrida"
        />
      </div>

      <!-- Com a corrida pedida, o que ainda é só do Gestor, numa frase. -->
      <p v-if="courier.status" class="text-sm text-muted" data-pos-courier-gestor>{{ GESTOR_ONLY_COURIER_LINE }}</p>

      <!-- Chamar: o toque arma a confirmação, com a pergunta inteira do servidor e
           a custódia que sai com o entregador. -->
      <template v-if="courier.can_dispatch">
        <div v-if="confirming" class="grid gap-3" data-pos-courier-confirm>
          <p v-if="question" class="text-sm" role="status" data-pos-courier-question>{{ question }}</p>
          <NuxtFormField v-if="asksChange" label="Troco que o entregador leva da gaveta" data-pos-courier-change>
            <NuxtInput
              v-model="changeOut"
              class="w-40"
              type="text"
              inputmode="decimal"
              icon="i-lucide-circle-dollar-sign"
              aria-label="Troco que o entregador leva da gaveta, em reais"
            />
          </NuxtFormField>
          <template v-if="asksMachine">
            <NuxtFormField v-if="free.length >= 2" label="Qual maquininha vai junto?" data-pos-courier-machine>
              <NuxtRadioGroup v-model="machineRef" :items="machineItems" orientation="horizontal" />
            </NuxtFormField>
            <p v-else-if="free.length === 1" class="text-sm" data-pos-courier-machine>
              Leva a {{ machinePhrase(free[0]!.label) }}.
            </p>
            <p v-else class="text-sm text-error" data-pos-courier-machine>
              {{ noFreeMachineSentence(equipmentOptions ?? []) }}
            </p>
          </template>
          <div class="flex flex-wrap gap-2" data-pos-courier-confirm-actions>
            <NuxtButton
              type="button"
              icon="i-lucide-send"
              label="Confirmar chamada"
              :disabled="busy || !dispatchAction?.enabled || machineMissing"
              data-pos-courier-confirm-call
              @click="confirmCall"
            />
            <NuxtButton
              type="button"
              color="neutral"
              variant="outline"
              label="Voltar"
              data-pos-courier-back
              @click="confirming = false"
            />
          </div>
        </div>
        <div v-else>
          <NuxtButton
            type="button"
            :icon="courier.status || courier.attempts_count > 0 ? 'i-lucide-refresh-cw' : 'i-lucide-send'"
            :label="courierCallLabel(courier)"
            :disabled="busy || !dispatchAction?.enabled"
            :title="dispatchAction?.enabled ? undefined : dispatchAction?.reason || undefined"
            data-pos-courier-call
            @click="arm"
          />
        </div>
      </template>
    </div>
  </NuxtCard>
</template>
