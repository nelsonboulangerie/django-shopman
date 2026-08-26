<script setup lang="ts">
const props = defineProps<{
  disabled?: boolean;
  compact?: boolean;
  /**
   * O que este teclado edita agora ("quantidade", "desconto", "preço"). O mesmo
   * pad serve os três modos, e os rótulos de leitor de tela diziam "quantidade"
   * mesmo quando o operador estava digitando um desconto.
   */
  subject?: string;
}>();

const subject = computed(() => props.subject || "quantidade");

const emit = defineEmits<{
  digit: [string];
  backspace: [];
  clear: [];
}>();

const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
const cellBase = "rounded-md border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40";
// ALTURA FIXA no degrau "campo·botão" da escala (h-11 = 44px), em vez de padding
// solto. O `compact` rendia ~38px — fora da escala e apertado para dedo — e o
// numpad do checkout usava h-14 (56px), 47% maior. Dois teclados de dígito na
// mesma casa, com regras diferentes: o operador reaprendia o alvo ao trocar de
// tela. 44px é o mesmo degrau dos campos e dos métodos de pagamento, sobe o
// pequeno e desce o grande.
const cell = computed(() => (props.compact ? `${cellBase} h-11 text-base` : `${cellBase} py-2.5 text-lg`));
const cellSmBase = "rounded-md border bg-card text-sm font-medium transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40";
const cellSm = computed(() => (props.compact ? `${cellSmBase} h-11` : `${cellSmBase} py-2.5`));
</script>

<template>
  <div :class="compact ? 'grid grid-cols-3 gap-1' : 'grid grid-cols-3 gap-1.5'" role="group" :aria-label="`Teclado numérico de ${subject}`">
    <button
      v-for="key in keys"
      :key="key"
      type="button"
      :class="cell"
      :disabled="disabled"
      :aria-label="`Dígito ${key}`"
      @click="emit('digit', key)"
    >
      {{ key }}
    </button>
    <button
      type="button"
      :class="cellSm"
      :disabled="disabled"
      :aria-label="`Limpar ${subject}`"
      @click="emit('clear')"
    >
      C
    </button>
    <button
      type="button"
      :class="cell"
      :disabled="disabled"
      aria-label="Dígito 0"
      @click="emit('digit', '0')"
    >
      0
    </button>
    <button
      type="button"
      class="grid place-items-center rounded-md border border-destructive/25 bg-destructive/5 text-destructive transition hover:bg-destructive/10 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
      :class="compact ? 'py-1.5' : 'py-2.5'"
      :disabled="disabled"
      aria-label="Apagar último dígito"
      @click="emit('backspace')"
    >
      <Icon name="lucide:delete" :class="compact ? 'size-4' : 'size-5'" />
    </button>
  </div>
</template>
