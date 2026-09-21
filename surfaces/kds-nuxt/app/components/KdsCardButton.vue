<script setup lang="ts">
// O botão da base do card, nas estações e na expedição: largura inteira, DENTRO da
// moldura (com a margem do card em volta), cantos arredondados, o ato escrito.
// Numa linha da grade todos caem na mesma altura, ao alcance do polegar.
//
// Tons — cor só onde tem significado:
//  - `invite`  convite para começar, CONTORNADO em primary: "Iniciar preparo".
//    Decisão do Pablo (21/09, #913): numa grade cheia de pedidos novos o
//    botão sólido virava uma parede amarela; contornado, o convite segue
//    visível e o único sólido da grade é o ato que tira o pedido da tela.
//  - `confirm` o ato que tira o pedido da tela (neutro invertido): "Finalizar
//    preparo", "Despachar pedido", "Entregar pedido".
//  - `outline` o gesto de volta: "Desfazer".
//  - `blocked` contornado em vermelho: não se convida ninguém a apertá-lo.
//  - `inert`   não é botão (prévia, espera do servidor): o mesmo lugar e a mesma
//    altura, apagado, e renderizado como TEXTO — o leitor de tela não ouve um
//    controle que não faz nada.
export type KdsCardButtonTone = "invite" | "confirm" | "outline" | "blocked" | "inert";

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
  invite: "border-2 border-primary/70 text-primary hover:bg-primary/10 active:bg-primary/20",
  confirm: "bg-foreground text-background hover:bg-foreground/90 active:bg-foreground/80",
  outline: "border bg-card hover:bg-accent active:bg-accent/70",
  blocked: "border border-destructive/50 bg-destructive/10 text-destructive dark:text-red-300",
};
const toneClass = computed(() => (props.tone === "inert" ? "" : TONES[props.tone]));
</script>

<template>
  <p
    v-if="tone === 'inert'"
    class="flex w-full items-center justify-center gap-2 rounded-md border px-2 font-semibold text-muted-foreground opacity-60"
    :class="sizeClass"
  >
    <Icon v-if="icon" :name="icon" class="size-4 shrink-0" />
    <span class="truncate">{{ label }}</span>
  </p>
  <button
    v-else
    type="button"
    class="flex w-full items-center justify-center gap-2 rounded-md px-2 font-semibold transition active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100"
    :class="[sizeClass, toneClass]"
    :disabled="disabled"
    @click="$emit('click', $event)"
  >
    <Icon v-if="icon" :name="icon" class="size-5 shrink-0" />
    <span class="truncate">{{ label }}</span>
  </button>
</template>
