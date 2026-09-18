<script setup lang="ts">
// Interruptor do operador — ESTADO, não comando.
//
// Um botão-com-check ("Emitir nota ✓/–") diz "eu executo"; um switch diz "eu sou
// um estado", e era estado o que essas dez perguntas sempre foram: liga/desliga
// que o operador vê de longe sem ler. Sete delas montavam o `Ui/Switch.vue` do
// PDV; as outras três eram o MESMO trilho+polegar reescrito à mão no Marketing e
// no Gestor de Pedidos — e já divergiam em três tamanhos, duas cores de trilho
// desligado e, no PDV, num alvo de toque de 24 px, metade do que a casa exige.
//
// Escrito à mão, sem lib: tokens do tema central e o contrato do ARIA
// (`role="switch"` + `aria-checked`). O rótulo é de quem monta — a pergunta é da
// TELA, não do widget —, seja pelo `<label>` em volta (um `<button>` é elemento
// rotulável, então o clique no texto chega aqui) ou por `aria-label`, que cai no
// root por fallthrough.
//
// ⚠️ O alvo de toque vem de `--spacing-control` (44 px, operator-theme.css), não
// de literal: `size-11` renderiza igual HOJE e some no dia em que o token mudar.
// A ideia é a do Marketing — caixa de 44 px em volta de um trilho menor —, agora
// no primitivo: o trilho continua discreto na linha e a mão continua acertando.
withDefaults(
  defineProps<{
    /** Ligado (v-model). */
    modelValue?: boolean;
    disabled?: boolean;
    /**
     * Cor do trilho LIGADO. `primary` é o padrão (preferência, escolha do
     * cliente); `success` é o verde de "está no ar" do Gestor de Pedidos;
     * `muted` mantém a POSIÇÃO ligada e tira a cor — é a linha que está fora por
     * outro motivo (esgotada, pausada acima), onde pintar de verde prometeria o
     * que a tela não entrega.
     */
    tone?: "primary" | "success" | "muted";
    /**
     * `sm` existe por UMA tela: a matriz produto×superfície do catálogo, com um
     * interruptor por célula. Fora dela, `md`.
     */
    size?: "md" | "sm";
  }>(),
  { modelValue: false, tone: "primary", size: "md" },
);

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
</script>

<template>
  <!-- `outline` de verdade, não `ring`: o anel por box-shadow some no modo de alto
       contraste do sistema, e quem depende dele fica sem foco visível. Mesmo
       motivo no UiCheckbox e no UiRadio. -->
  <button
    type="button"
    role="switch"
    data-slot="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    class="inline-flex size-control shrink-0 cursor-pointer items-center justify-center rounded-md outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
    @click="emit('update:modelValue', !modelValue)"
  >
    <!-- No `md` o trilho preenche o alvo: a largura É o token, e o polegar anda
         de 2 px a 22 px dentro dele. No `sm` o trilho é menor de propósito — o
         alvo de 44 px continua em volta, invisível na tabela. -->
    <span
      aria-hidden="true"
      class="flex items-center rounded-full transition-colors"
      :class="[
        size === 'sm' ? 'h-4 w-7' : 'h-6 w-control',
        modelValue && tone !== 'muted'
          ? tone === 'success'
            ? 'bg-success'
            : 'bg-primary'
          : 'bg-muted-foreground/30',
      ]"
    >
      <!-- `translate-x` é o único movimento: sem escala nem sombra, para o trilho
           não competir com o numpad ao lado. -->
      <span
        class="rounded-full bg-background shadow-xs transition-transform"
        :class="[
          size === 'sm' ? 'size-3' : 'size-5',
          modelValue ? (size === 'sm' ? 'translate-x-3.5' : 'translate-x-[1.375rem]') : 'translate-x-0.5',
        ]"
      ></span>
    </span>
  </button>
</template>
