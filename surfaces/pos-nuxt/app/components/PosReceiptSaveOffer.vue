<script lang="ts" setup>
  /**
   * "Quer salvar este e-mail no cadastro?" — a pergunta junto do campo.
   *
   * Duas peças, e as duas precisam existir:
   *
   * 1. A LINHA PERSISTENTE, sempre à vista sob o campo, com o interruptor. É
   *    ela que segura a promessa de transparência do "já marcado" da venda
   *    anônima: o padrão é marcado por decisão do dono, e um padrão que se
   *    esconde atrás de um "avançado" seria gravar calado com outro nome.
   * 2. O POPOVER, que abre quando o operador termina de digitar o contato e diz
   *    a consequência antes de ela acontecer.
   *
   * ⚠️ É popover, não tooltip: tooltip com ação dentro não é tooltip. Por isso
   * (a) abre ao DIGITAR e não por hover — no balcão a tela é sensível ao toque
   * e hover não existe; (b) NÃO rouba o foco do campo (`open-auto-focus`
   * prevenido, `trap-focus` desligado, `focus-outside` prevenido), senão a
   * próxima tecla de quem digita rápido cai no lugar errado; (c) sai por
   * portal, então não empurra o layout nem é recortado pelo `overflow-x-auto`
   * da coluna.
   */
  import type { ReceiptContactOffer } from "~/presentation/receiptContact";

  const props = withDefaults(defineProps<{
    offer: ReceiptContactOffer;
    checked: boolean;
    /** Desliga só o popover; a linha persistente continua. Quem chama sabe
     *  quando a pergunta seria um FANTASMA — o modal do cliente por cima, por
     *  exemplo: o balão abriria atrás do overlay, sem ninguém para respondê-lo. */
    quiet?: boolean;
    /** De que LADO o balão abre. Não é gosto: é o que ele tapa.
     *
     *  Na coluna do fechamento, `bottom` cobria o `Validar` (campo do e-mail, o
     *  último) e as duas perguntas seguintes (campo do CPF, o primeiro da
     *  seção). A coluna encosta na borda direita da tela e o miolo ao lado está
     *  vazio — daí `left`. Dentro do modal, que é centrado, `top` é o que sobra
     *  livre acima do "Concluir". Sempre pela primitiva (`side`), nunca por
     *  `position` na mão: é o `side` que mantém o portal e o desvio de colisão. */
    side?: "top" | "right" | "bottom" | "left";
  }>(), { quiet: false, side: "bottom" });

  const emit = defineEmits<{ "update:checked": [boolean] }>();

  /** O valor cuja pergunta já foi respondida ou dispensada — não reabre por ele. */
  const settledFor = ref("");
  const open = computed(
    () =>
      !props.quiet
      && props.offer.kind !== "none"
      && Boolean(props.offer.typed)
      && settledFor.value !== props.offer.typed,
  );

  // Digitou outra coisa? A pergunta é nova. Sem isto, corrigir um dígito do CPF
  // depois de dispensar deixaria a oferta muda para sempre.
  watch(
    () => props.offer.typed,
    (typed) => {
      if (typed !== settledFor.value) settledFor.value = "";
    },
  );

  function settle() {
    settledFor.value = props.offer.typed;
  }

  function confirm() {
    emit("update:checked", true);
    settle();
  }

  function decline() {
    emit("update:checked", false);
    settle();
  }

  const declineLabel = computed(() => (props.checked ? "Não salvar" : "Agora não"));
</script>

<template>
  <div class="grid gap-2">
    <UiPopover :open="open" @update:open="(value: boolean) => { if (!value) settle(); }">
      <UiPopoverAnchor as-child>
        <div><slot /></div>
      </UiPopoverAnchor>

      <UiPopoverContent
        v-if="offer.kind !== 'none'"
        align="center"
        :side="side"
        :trap-focus="false"
        class="w-80 p-3"
        role="dialog"
        :aria-label="offer.title"
        @open-auto-focus.prevent
        @close-auto-focus.prevent
        @focus-outside.prevent
      >
        <p class="text-sm font-medium leading-snug">{{ offer.title }}</p>
        <p class="mt-1 text-xs text-muted-foreground">{{ offer.hint }}</p>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <UiButton type="button" size="xs" @click="confirm">{{ offer.confirmLabel }}</UiButton>
          <UiButton type="button" size="xs" variant="ghost" @click="decline">{{ declineLabel }}</UiButton>
        </div>
      </UiPopoverContent>
    </UiPopover>

    <!-- A linha que fica. Nunca dentro de um "avançado": o padrão marcado só é
         honesto enquanto continuar visível e a um toque de distância. -->
    <label
      v-if="offer.kind !== 'none'"
      class="flex cursor-pointer items-start justify-between gap-3 rounded-md border border-dashed px-2.5 py-2"
    >
      <span class="grid min-w-0 gap-0.5">
        <span class="text-xs font-medium leading-tight">{{ offer.title }}</span>
        <span class="text-xs text-muted-foreground">{{ offer.hint }}</span>
      </span>
      <UiSwitch
        :model-value="checked"
        :aria-label="offer.title"
        @update:model-value="(value: boolean) => { emit('update:checked', value); settle(); }"
      />
    </label>
  </div>
</template>
