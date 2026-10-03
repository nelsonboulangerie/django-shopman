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
  <div
    v-if="loaded && allowed"
    class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-background p-4 text-foreground"
    role="dialog"
    aria-modal="true"
    aria-labelledby="station-setup-title"
    data-station-setup
  >
    <div class="grid w-full max-w-sm gap-4 text-center">
      <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
        <Icon name="lucide:map-pin" class="size-7 text-muted-foreground" />
      </div>
      <div class="grid gap-1.5">
        <h2 id="station-setup-title" class="text-lg font-semibold">{{ copy.setup_title }}</h2>
        <p class="text-sm text-muted-foreground">{{ copy.setup_lead }}</p>
      </div>

      <div v-if="options.length" class="grid gap-2 text-left">
        <!-- "Posto:" num seletor (decisão do dono, 03/10): com um posto só, já vem
             marcado. A segunda linha do escolhido diz o tipo e quem já está nele. -->
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">{{ copy.setup_choice_label }}</span>
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
        <p v-if="escolhidoHint" class="text-xs text-muted-foreground" data-station-setup-hint>{{ escolhidoHint }}</p>
        <p
          v-if="error"
          class="text-sm"
          :class="pedeConfirmacao ? 'text-warning' : 'text-destructive'"
          role="alert"
        >{{ error }}</p>
      </div>
      <p v-else class="text-sm text-muted-foreground" data-station-setup-empty>{{ copy.setup_empty }}</p>

      <!-- `<button>` cru e não `UiButton`: o kit não alcança a biblioteca Ui de cada
           app, e esta tela sobe nos oito (ver OperatorSessionUnavailable). -->
      <div class="grid gap-2">
        <button
          v-if="options.length"
          type="button"
          class="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          :disabled="busy || !escolhido"
          :aria-busy="busy"
          data-station-setup-confirm
          @click="confirmar"
        >
          <Icon :name="busy ? 'line-md:loading-loop' : 'lucide:check'" class="size-5" />
          {{ busy ? copy.setup_busy : pedeConfirmacao ? copy.setup_confirm_shared : copy.setup_confirm }}
        </button>
        <button
          type="button"
          class="inline-flex h-12 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition hover:bg-foreground/8 disabled:opacity-50"
          :disabled="busy"
          data-station-setup-dismiss
          @click="emit('dismiss')"
        >
          {{ copy.setup_dismiss }}
        </button>
      </div>
    </div>
  </div>
</template>
