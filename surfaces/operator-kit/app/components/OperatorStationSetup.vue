<script setup lang="ts">
// VINCULAR ESTE DISPOSITIVO A UM POSTO DE TRABALHO: uma vez por máquina, em qualquer app.
//
// Aparece para quem gere operadores, logado, num dispositivo que ainda não é posto.
// Depois disso o dispositivo abre sozinho e pede PIN, e ninguém precisa trazer senha
// de gestor para a loja abrir.
//
// É oferta, não parede: no notebook pessoal do gestor a resposta certa é "usar sem vincular",
// e obrigar a escolher ali criaria um posto onde não há posto. Quem não pode vincular
// (403) nem vê: a oferta se dispensa sozinha.
//
// Cada app lista os postos que fazem sentido nele (a Produção oferece salas; a
// Cozinha, estações e Expedição), mas o posto é um só para todos os apps. Toda
// palavra desta tela vem do servidor (`workstation_vocabulary.py`).
import { workstationRadioOptions } from "../presentation/workstation";

const props = defineProps<{
  /** Id do app (`surfaces/registry.json`). Omitido → a identidade do app. */
  surface?: string;
}>();

// `dismiss` é o "Usar sem vincular" de quem podia vincular; `unavailable`, o 403 de quem não
// pode. O shell lembra só o primeiro: quem não pode hoje pode passar a poder.
const emit = defineEmits<{ (e: "done"): void; (e: "dismiss"): void; (e: "unavailable"): void }>();

const { workstations, copy, allowed, loaded, busy, error, confirmFor, load, provision } = useStationProvision(
  props.surface,
);
const escolhido = ref("");
// A1: a oferta é banner; os passos abrem no Slideover sob demanda.
const open = ref(false);

onMounted(async () => {
  await load();
  // Sem permissão, não há oferta: o app segue como se ela não existisse.
  if (!allowed.value) {
    emit("unavailable");
    return;
  }
  if (workstations.value.length === 1) escolhido.value = workstations.value[0]!.ref;
});

const options = computed(() => workstationRadioOptions(workstations.value));
const escolhidoHint = computed(() => options.value.find((o) => o.value === escolhido.value)?.hint ?? "");

// A segunda palavra só vale para o caixa que o servidor avisou.
const pedeConfirmacao = computed(() => Boolean(confirmFor.value) && confirmFor.value === escolhido.value);

async function confirmar() {
  if (await provision(escolhido.value, { confirm: pedeConfirmacao.value })) emit("done");
}
</script>

<template>
  <!-- A1: a oferta de posto é BANNER, não parede. O board fica operável atrás; os
       passos (escolher posto e confirmar) moram no Slideover. O "Usar sem vincular"
       continua lembrado neste navegador (useStationSetupOffer). -->
  <NuxtBanner
    v-if="loaded && allowed"
    :title="copy.setup_title"
    :description="copy.setup_lead"
    icon="i-lucide-map-pin"
    class="mb-3 shrink-0"
    data-station-setup
  >
    <template #actions>
      <NuxtButton
        v-if="options.length"
        size="sm"
        :label="copy.setup_confirm"
        data-station-setup-open
        @click="open = true"
      />
      <NuxtButton
        size="sm"
        color="neutral"
        variant="ghost"
        :label="copy.setup_dismiss"
        data-station-setup-dismiss
        @click="emit('dismiss')"
      />
    </template>
  </NuxtBanner>

  <NuxtSlideover
    v-model:open="open"
    :title="copy.setup_title"
    :description="copy.setup_lead"
    data-station-setup-steps
  >
    <template #body>
      <div v-if="options.length" class="grid gap-2 text-left">
        <label class="grid gap-1.5 text-sm suite:op-label">
          <span class="font-medium suite:op-eyebrow suite:text-muted-foreground">{{ copy.setup_choice_label }}</span>
          <UiNativeSelect
            v-model="escolhido"
            class="h-12 w-full"
            :disabled="busy"
            data-station-setup-select
          >
            <option v-if="options.length > 1" value="" disabled>&nbsp;</option>
            <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
          </UiNativeSelect>
        </label>
        <p v-if="escolhidoHint" class="text-xs text-muted-foreground suite:op-micro" data-station-setup-hint>{{ escolhidoHint }}</p>
        <p
          v-if="error"
          class="text-sm"
          :class="pedeConfirmacao ? 'text-warning' : 'text-destructive'"
          role="alert"
        >{{ error }}</p>
      </div>
      <p v-else class="text-sm text-muted-foreground suite:op-body" data-station-setup-empty>{{ copy.setup_empty }}</p>
    </template>

    <template #footer>
      <div class="grid w-full gap-2">
        <NuxtButton
          v-if="options.length"
          block
          :loading="busy"
          :label="busy ? copy.setup_busy : pedeConfirmacao ? copy.setup_confirm_shared : copy.setup_confirm"
          data-station-setup-confirm
          @click="confirmar"
        />
        <NuxtButton
          block
          color="neutral"
          variant="outline"
          :label="copy.setup_dismiss"
          :disabled="busy"
          data-station-setup-slideover-dismiss
          @click="emit('dismiss')"
        />
      </div>
    </template>
  </NuxtSlideover>
</template>
