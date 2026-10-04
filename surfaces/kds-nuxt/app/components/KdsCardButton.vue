<script setup lang="ts">
// O botão da base do ticket: largura inteira, DENTRO da moldura (com a margem do card
// em volta), cantos de 8px, o ato escrito. Numa linha da grade todos caem na mesma
// altura, ao alcance do polegar. Desenho da prévia v4 (`cozinha-estacao4.html`).
//
// Tons (cor só onde tem significado):
//  - `lead`    o convite do PRÓXIMO: "Iniciar preparo" sólido na cor da casa. É um só
//    na grade (o destacado), então não vira a parede amarela de 21/09 (#913): os
//    outros convites são contornados.
//  - `invite`  convite para começar, contornado: "Iniciar preparo" dos demais.
//  - `confirm` o ato que tira o pedido da tela: "Finalizar preparo", sólido verde.
//  - `outline` o gesto de volta: "Desfazer".
//  - `blocked` contornado em vermelho: item cancelado, não se convida ninguém.
//  - `locked`  tracejado e listrado, com cadeado: o servidor recusaria o Finalizar
//    (pagamento não confirmado). O toque diz o motivo.
//  - `inert`   não é botão (prévia, espera do servidor): o mesmo lugar e a mesma
//    altura, apagado, e renderizado como TEXTO, para o leitor de tela não ouvir um
//    controle que não faz nada.
export type KdsCardButtonTone = "lead" | "invite" | "confirm" | "outline" | "blocked" | "locked" | "inert";

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

const TONES: Record<Exclude<KdsCardButtonTone, "inert">, string> = {
  lead: "bg-primary text-primary-foreground hover:bg-primary/90 active:bg-primary/80",
  invite: "border-2 border-foreground/80 text-foreground hover:bg-foreground/10 active:bg-foreground/20",
  confirm: "bg-success text-success-foreground hover:bg-success/90 active:bg-success/80",
  outline: "border border-border bg-card hover:bg-accent active:bg-accent/70",
  blocked: "border border-destructive/60 bg-destructive/10 text-destructive",
  locked:
    "border-2 border-dashed border-border text-muted-foreground bg-[repeating-linear-gradient(135deg,transparent_0_7px,color-mix(in_oklab,var(--destructive)_9%,transparent)_7px_14px)]",
};
const toneClass = computed(() => (props.tone === "inert" ? "" : TONES[props.tone]));
</script>

<template>
  <p
    v-if="tone === 'inert'"
    class="flex w-full items-center justify-center gap-2 rounded-lg border px-2 font-semibold text-muted-foreground opacity-60"
    :class="sizeClass"
  >
    <Icon v-if="icon" :name="icon" class="size-5 shrink-0" />
    <span class="truncate">{{ label }}</span>
  </p>
  <button
    v-else
    type="button"
    class="flex w-full shrink-0 items-center justify-center gap-2.5 rounded-lg px-2 font-semibold transition active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100"
    :class="[sizeClass, toneClass]"
    :disabled="disabled"
    @click="$emit('click', $event)"
  >
    <Icon v-if="icon" :name="icon" class="size-5 shrink-0" />
    <span class="truncate">{{ label }}</span>
  </button>
</template>
