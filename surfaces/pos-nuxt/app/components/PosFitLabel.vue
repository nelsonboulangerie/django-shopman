<script setup lang="ts">
// RÓTULO QUE SE ADAPTA AO ESPAÇO (política da suíte, dono 10/10): rótulo completo,
// depois o rótulo curto escrito à mão (`short`), depois só o ícone do botão. Nunca
// corta no meio e nunca vaza. Quem decide é a LARGURA DO CONTÊINER (`@container`
// no ancestral: a coluna da comanda, a barra da venda), por CSS: sem JS de largura
// e sem piscar na primeira pintura.
//
// O nome acessível não muda com o espaço: o rótulo completo fica sempre no `sr-only`
// e as versões visíveis são `aria-hidden`. Quem precisa do texto inteiro com o
// ícone sozinho tem o `title` do botão (a dica).
//
// Peça local do PDV até a do kit (`OperatorButton`, frente própria) entrar no
// `main`: a troca é passar `label`/`short-label` ao botão do kit e apagar esta.
//
// As faixas são fixas e escritas por extenso: o Tailwind só gera a classe que lê
// no código (classe montada em tempo de execução não existe no CSS).
const props = withDefaults(
  defineProps<{
    label: string;
    /** O rótulo curto, escrito à mão ("Enviar à cozinha" → "Cozinha"). */
    short?: string;
    /** Abaixo do degrau curto o botão fica só com o ícone. `false` mantém o curto. */
    iconOnly?: boolean;
    /** O degrau do contêiner: sm (20/14 rem), md (24/18 rem), lg (28/20 rem). */
    step?: "sm" | "md" | "lg";
  }>(),
  { short: "", iconOnly: true, step: "md" },
);

const STEPS = {
  sm: { full: "hidden @min-[20rem]:inline", short: "hidden @min-[14rem]:inline @min-[20rem]:hidden", shortOnly: "inline @min-[20rem]:hidden" },
  md: { full: "hidden @min-[24rem]:inline", short: "hidden @min-[18rem]:inline @min-[24rem]:hidden", shortOnly: "inline @min-[24rem]:hidden" },
  lg: { full: "hidden @min-[28rem]:inline", short: "hidden @min-[20rem]:inline @min-[28rem]:hidden", shortOnly: "inline @min-[28rem]:hidden" },
} as const;

const classes = computed(() => {
  const step = STEPS[props.step];
  if (props.short) return { full: step.full, short: props.iconOnly ? step.short : step.shortOnly };
  // Sem rótulo curto: o completo enquanto couber; abaixo do degrau, só o ícone.
  return { full: props.iconOnly ? step.full : "inline", short: "" };
});
</script>

<template>
  <span class="sr-only">{{ label }}</span>
  <span :class="classes.full" class="whitespace-nowrap" aria-hidden="true" data-fit-label="full">{{ label }}</span>
  <span v-if="short" :class="classes.short" class="whitespace-nowrap" aria-hidden="true" data-fit-label="short">{{ short }}</span>
</template>
