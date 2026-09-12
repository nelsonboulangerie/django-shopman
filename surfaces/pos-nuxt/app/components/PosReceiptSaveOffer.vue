<script lang="ts" setup>
  // Gravar no cadastro é opt-in inline. Digitar nunca abre outra pergunta.
  import type { ReceiptContactOffer } from "~/presentation/receiptContact";

  const props = withDefaults(defineProps<{
    offer: ReceiptContactOffer;
    checked: boolean;
    /** A segunda palavra já foi dita? Só o CPF divergente a exige. */
    confirmed?: boolean;
  }>(), { confirmed: false });

  const emit = defineEmits<{
    "update:checked": [boolean];
    /**
     * A SEGUNDA palavra. Só o CPF divergente a pede, e a assimetria é o ponto:
     * e-mail muda (provedor, emprego) e trocá-lo é rotina de um toque; CPF a
     * pessoa tem a vida inteira, e trocá-lo no cadastro troca a identidade
     * fiscal dela.
     */
    "update:confirmed": [boolean];
  }>();

  /** O aviso e a reconfirmação estão à vista? */
  const needsWord = computed(() => props.offer.requiresConfirmation && props.checked);

  // Desmarcar — ou trocar o valor digitado, ou o cadastro mudar debaixo da
  // pergunta — DERRUBA a segunda palavra. Uma confirmação que sobrevive à
  // mudança daquilo que foi confirmado é consentimento tomado emprestado.
  watch(
    () => [props.checked, props.offer.typed, props.offer.onFile] as const,
    () => { if (props.confirmed) emit("update:confirmed", false); },
  );

</script>

<template>
  <div class="grid gap-2">
    <div><slot /></div>

    <label
      v-if="offer.kind !== 'none'"
      class="flex cursor-pointer items-start justify-between gap-3 rounded-md border border-dashed px-2.5 py-2"
    >
      <span class="grid min-w-0 gap-0.5">
        <span class="text-xs font-medium leading-tight">{{ offer.title }}</span>
        <span v-if="checked && !needsWord" class="text-xs text-muted-foreground">{{ offer.hint }}</span>
      </span>
      <UiSwitch
        :model-value="checked"
        :aria-label="offer.title"
        @update:model-value="(value: boolean) => emit('update:checked', value)"
      />
    </label>

    <!-- ⚠️ O ATRITO DO CPF — e ele existe porque CPF não é e-mail.
         E-mail MUDA: troca-se de provedor, troca-se de emprego, e o endereço
         novo substituindo o velho é rotina de cadastro. CPF NÃO MUDA: a pessoa
         tem um a vida inteira, e se o cadastro diz um e a nota traz outro, a
         hipótese provável não é "mudou" — é "esta nota é de outra pessoa".
         A oferta continua existindo (o dono quis o conserto possível no
         balcão), mas para e pergunta de novo: sem esta segunda palavra o intent
         não manda nada (`receiptContactArmed`). -->
    <div
      v-if="needsWord"
      class="grid gap-2 rounded-md border border-warning bg-warning/10 px-2.5 py-2"
      role="alertdialog"
      aria-live="assertive"
    >
      <p class="text-xs leading-snug">{{ offer.warning }}</p>
      <p v-if="!confirmed" class="text-xs font-medium leading-tight">{{ offer.confirmPrompt }}</p>
      <div v-if="!confirmed" class="flex flex-wrap items-center gap-2">
        <UiButton type="button" size="xs" @click="emit('update:confirmed', true)">
          Trocar CPF
        </UiButton>
        <UiButton
          type="button"
          size="xs"
          variant="ghost"
          @click="emit('update:checked', false)"
        >
          Manter CPF
        </UiButton>
      </div>
      <p v-else class="flex items-center gap-1.5 text-xs font-medium">
        <Icon name="lucide:check" class="size-3.5 shrink-0" />
        Troca confirmada.
      </p>
    </div>
  </div>
</template>
