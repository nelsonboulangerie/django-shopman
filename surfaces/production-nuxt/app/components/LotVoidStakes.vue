<script setup lang="ts">
// O que está em jogo quando um lote sai (cancelar, ou zerar no Planejamento), dito
// ANTES do botão: quantas unidades estão encomendadas e quais pedidos dependem dele
// (WP-F07, P1-01). E o motivo, que é de quem decide: um toque nos motivos comuns ou
// o texto livre. O motivo nunca nasce do código (o servidor recusa sem ele, #3400).
//
// Lê o prometido do produto na data do lote, pela régua das reservas (WP-F10):
// primeiro nome e hora de cada pedido.
import { computed, nextTick, ref } from "vue";

import { promisedOrderLine } from "~/presentation/production";
import { lotStakes } from "~/presentation/lotStakes";
import type { PromisedOrderProjection } from "~/types/production";

const props = defineProps<{
  orders: PromisedOrderProjection[];
  unit?: string;
  /** O que acontece com o lote, na voz do gesto ("O lote volta atrás."). */
  consequence: string;
}>();

const reason = defineModel<string>("reason", { required: true });

// O texto do aviso na cor de texto da casa: o tom (âmbar, azul) fica no ícone e no
// fundo. Na cor do aviso sobre o fundo do aviso, o título media 3,55 de contraste
// (J-P3, 23/11), abaixo dos 4,5 de leitura.
const LEGIBLE = { title: "text-highlighted", description: "text-default" };

const stakes = computed(() => lotStakes(props.orders, props.unit));

// Motivos comuns de tirar um lote do dia. Tocar preenche o texto, que continua
// editável; "Outro" limpa e leva o foco ao campo.
const REASONS = [
  "Planejado a mais",
  "Falta insumo",
  "Massa perdida",
] as const;
const OTHER = "Outro";
const otherChosen = ref(false);
const reasonField = ref<{ textareaRef?: HTMLTextAreaElement | null } | null>(
  null,
);

function choose(preset: string) {
  otherChosen.value = false;
  reason.value = preset;
}
function chooseOther() {
  otherChosen.value = true;
  reason.value = "";
  // O campo é o mesmo; só o foco espera o próximo quadro.
  void nextTick(() => reasonField.value?.textareaRef?.focus());
}
const otherActive = computed(
  () =>
    otherChosen.value ||
    (!!reason.value.trim() &&
      !(REASONS as readonly string[]).includes(reason.value)),
);
</script>

<template>
  <div class="flex flex-col gap-3" data-lot-stakes>
    <NuxtAlert
      v-if="stakes"
      color="warning"
      variant="subtle"
      icon="i-lucide-triangle-alert"
      :title="stakes.headline"
      :ui="LEGIBLE"
      data-lot-stakes-orders
    >
      <template #description>
        <p>{{ consequence }} Esses pedidos perdem o pão garantido e aparecem em "Promessa em risco" no Gestor.</p>
        <ul class="mt-2 grid gap-1">
          <li
            v-for="order in orders"
            :key="order.ref"
            class="tabular-nums"
          >
            {{ promisedOrderLine(order, unit) }}
          </li>
        </ul>
      </template>
    </NuxtAlert>
    <NuxtAlert
      v-else
      color="info"
      variant="subtle"
      icon="i-lucide-info"
      :description="`${consequence} Nenhuma encomenda depende dele.`"
      :ui="LEGIBLE"
      data-lot-stakes-free
    />

    <div class="grid gap-2" data-lot-void-reason>
      <span id="lot-void-reason-label" class="text-sm font-medium">
        Motivo (fica registrado com seu nome)
      </span>
      <div
        class="flex flex-wrap gap-2"
        role="group"
        aria-labelledby="lot-void-reason-label"
      >
        <!-- Motivo pronto preenche o texto (editável); é escolha, não CTA. -->
        <NuxtButton
          v-for="preset in REASONS"
          :key="preset"
          color="neutral"
          variant="outline"
          size="xl"
          :active="!otherChosen && reason === preset"
          active-color="primary"
          active-variant="outline"
          :aria-pressed="!otherChosen && reason === preset"
          :label="preset"
          data-lot-void-preset
          @click="choose(preset)"
        />
        <NuxtButton
          color="neutral"
          variant="outline"
          size="xl"
          :active="otherActive"
          active-color="primary"
          active-variant="outline"
          :aria-pressed="otherActive"
          :label="OTHER"
          data-lot-void-other
          @click="chooseOther"
        />
      </div>
      <NuxtTextarea
        ref="reasonField"
        v-model="reason"
        :rows="2"
        :maxlength="500"
        class="w-full"
        aria-labelledby="lot-void-reason-label"
        placeholder="Ex.: a massa não fermentou"
      />
    </div>
  </div>
</template>
