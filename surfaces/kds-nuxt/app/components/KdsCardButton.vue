<script setup lang="ts">
// O botão da base do ticket: largura inteira, DENTRO da moldura (com a margem do card
// em volta), o ato escrito. Numa linha da grade todos caem na mesma altura, ao alcance
// do polegar. Desenho da prévia v4 (`cozinha-estacao4.html`), sobre o `NuxtButton` do
// conjunto mínimo (`xl`, o toque crítico).
//
// Tons (cor só onde tem significado):
//  - `lead`    o convite do PRÓXIMO: "Iniciar preparo" sólido na cor da casa. É um só
//    na grade (o destacado), então não vira a parede amarela de 21/09 (#913): os
//    outros convites são contornados.
//  - `invite`  convite para começar, contornado: "Iniciar preparo" dos demais.
//  - `confirm` o ato que tira o pedido da tela: "Pronto W07", sólido verde. O verde
//    do Pronto é a assinatura da Cozinha (v4); ele mora aqui, uma vez, sobre o neutro
//    sólido, e não vira cor de botão da suíte.
//  - `outline` o gesto de volta.
//  - `blocked` contornado em vermelho: item cancelado, não se convida ninguém.
//  - `locked`  tracejado e listrado, com cadeado: o servidor recusaria o Pronto
//    (pagamento não confirmado). O toque diz o motivo.
export type KdsCardButtonTone = "lead" | "invite" | "confirm" | "outline" | "blocked" | "locked";

const props = withDefaults(
  defineProps<{
    tone: KdsCardButtonTone;
    icon?: string;
    label: string;
    /** Altura + corpo de texto (escala de densidade; nunca abaixo de h-11). */
    sizeClass: string;
    disabled?: boolean;
  }>(),
  { icon: "", disabled: false },
);
defineEmits<{ click: [event: MouseEvent] }>();

type Look = { color: "primary" | "neutral" | "error"; variant: "solid" | "outline"; extra: string };
const LOOKS: Record<KdsCardButtonTone, Look> = {
  lead: { color: "primary", variant: "solid", extra: "" },
  invite: { color: "neutral", variant: "outline", extra: "" },
  confirm: {
    color: "neutral",
    variant: "solid",
    extra: "bg-success text-success-foreground hover:bg-success/90 active:bg-success/80 disabled:bg-success",
  },
  outline: { color: "neutral", variant: "outline", extra: "" },
  blocked: { color: "error", variant: "outline", extra: "" },
  locked: {
    color: "neutral",
    variant: "outline",
    extra:
      "ring-0 border-2 border-dashed border-border text-muted-foregroundbg-[repeating-linear-gradient(135deg,transparent_0_7px,color-mix(in_oklab,var(--destructive)_9%,transparent)_7px_14px)]",
  },
};
const look = computed(() => LOOKS[props.tone]);
// O rótulo do ato quebra em até duas linhas, nunca "Pronto W0…" (o oficial corta).
const BUTTON_UI = { label: "line-clamp-2 whitespace-normal text-center leading-tight" };
// O ícone segue `lucide:nome` (o mesmo nome que o `<Icon>` do card e o bundle de
// ícones do app já conhecem); o NuxtButton aceita esse formato.
const icon = computed(() => props.icon || undefined);
</script>

<template>
  <NuxtButton
    size="xl"
    block
    :color="look.color"
    :variant="look.variant"
    :icon="icon"
    :label="label"
    :disabled="disabled"
    :ui="BUTTON_UI"
    class="shrink-0 justify-center font-semibold"
    :class="[sizeClass, look.extra]"
    @click="$emit('click', $event)"
  />
</template>
