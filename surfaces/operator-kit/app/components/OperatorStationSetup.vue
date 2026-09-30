<script setup lang="ts">
// INICIAR ESTE DISPOSITIVO — a montagem do balcão, uma vez por máquina.
//
// Aparece para quem gere operadores, logado com senha, num dispositivo que ainda não
// é uma estação. Depois disso o balcão abre sozinho de manhã e pede PIN, e
// ninguém precisa trazer senha de gestor para a loja abrir.
//
// É oferta, não parede: no PC pessoal do gestor a resposta certa é "agora não", e
// obrigar a escolher um terminal ali criaria uma estação onde não há balcão —
// uma chave da antessala solta num notebook que sai de casa.
import { stationTerminalHint } from "../presentation/stationOccupancy";

const emit = defineEmits<{ (e: "done"): void; (e: "dismiss"): void }>();

const { terminals, allowed, loaded, busy, error, confirmFor, load, provision } = useStationProvision();
const escolhido = ref("");

onMounted(async () => {
  await load();
  if (terminals.value.length === 1) escolhido.value = terminals.value[0]!.ref;
});

// O `ref` do terminal vira a segunda linha da opção: dois balcões podem ter
// rótulo parecido, e é o ref que desempata na hora de dizer qual máquina é esta.
// Ao lado dele, o que já está no balcão: outros dispositivos e caixa aberto.
const terminalOptions = computed(() =>
  terminals.value.map((terminal) => ({
    value: terminal.ref,
    label: terminal.label,
    hint: stationTerminalHint(terminal),
  })),
);

// A segunda palavra só vale para o balcão que o servidor avisou.
const pedeConfirmacao = computed(() => Boolean(confirmFor.value) && confirmFor.value === escolhido.value);

async function confirmar() {
  if (await provision(escolhido.value, { confirm: pedeConfirmacao.value })) emit("done");
}
</script>

<template>
  <div
    v-if="loaded && allowed && terminals.length"
    class="grid min-h-dvh place-items-center p-4"
  >
    <div class="grid w-full max-w-sm gap-4 text-center">
      <div class="mx-auto grid size-14 place-items-center rounded-full border bg-muted">
        <Icon name="lucide:monitor-check" class="size-7 text-muted-foreground" />
      </div>
      <div class="grid gap-1.5">
        <h2 class="text-lg font-semibold">Iniciar este dispositivo</h2>
        <p class="text-sm text-muted-foreground">
          Diga qual balcão é este. Depois disso ele abre sozinho e pede só o PIN de
          quem for operar.
        </p>
      </div>

      <div class="grid gap-2 text-left">
        <UiRadioGroup
          v-model="escolhido"
          label="Qual balcão é este"
          :disabled="busy"
          :options="terminalOptions"
        />
        <p
          v-if="error"
          class="text-sm"
          :class="pedeConfirmacao ? 'text-warning' : 'text-destructive'"
          role="alert"
        >{{ error }}</p>
      </div>

      <div class="grid gap-2">
        <UiButton size="lg" :disabled="busy || !escolhido" @click="confirmar">
          <Icon :name="busy ? 'line-md:loading-loop' : 'lucide:check'" class="size-5" />
          {{ busy ? "Iniciando…" : pedeConfirmacao ? "Usar este balcão também" : "É este balcão" }}
        </UiButton>
        <UiButton variant="ghost" size="lg" :disabled="busy" @click="emit('dismiss')">
          Agora não
        </UiButton>
      </div>
    </div>
  </div>
</template>
