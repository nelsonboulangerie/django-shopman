<script setup lang="ts">
// O PIN da suíte: o campo e o teclado, uma peça só.
//
// A identificação (`OperatorIdentify`: trava e autorização do gerente) e a troca
// de PIN (`OperatorPinChange`) desenhavam cada uma o seu campo e o seu teclado, e
// os dois tinham derivado do mesmo jeito: 8 casas para um PIN de 4, o campo
// encostado à esquerda, as teclas esticadas na largura do cartão com o número
// no canto (dono, 10/10/2026). Aqui o desenho mora uma vez.
//
// O campo desenha a regra do PIN (`pinSlots`): no mínimo 4 dígitos, até 8. Nasce
// com 4 casas e ganha uma a cada dígito além do quarto. Ele só MOSTRA: quem
// digita é o teclado da tela ou o teclado físico (a captura de quem chama, ou a
// desta peça com `keyboard`). Campo focável abria o teclado do sistema por cima
// do pad no tablet, e, focado, tirava o Enter e o crachá da captura.
import {
  PIN_MIN_DIGITS,
  pinSlots,
} from "../presentation/operatorLock";

const props = withDefaults(
  defineProps<{
    /** O PIN digitado até agora (só dígitos). */
    pin: string;
    /** Nome do campo, visível acima dele ("PIN atual", "Novo PIN"). */
    label?: string;
    /** Recusa a mostrar abaixo do campo. */
    error?: string;
    /** Se a tecla de confirmar está liberada (quem chama sabe quem e quanto). */
    canSubmit?: boolean;
    busy?: boolean;
    /** Ícone e nome da tecla de confirmar. */
    submitIcon?: string;
    submitLabel?: string;
    /**
     * A peça ouve o teclado físico sozinha. Só para quem não tem captura própria
     * (a troca de PIN); a identificação já captura no documento e decide crachá.
     */
    keyboard?: boolean;
  }>(),
  {
    label: "",
    error: "",
    canSubmit: false,
    busy: false,
    submitIcon: "i-lucide-check",
    submitLabel: "Confirmar",
    keyboard: false,
  },
);

const emit = defineEmits<{
  digit: [string];
  backspace: [];
  submit: [];
}>();

const slots = computed(() => pinSlots(props.pin.length));
// O campo recebe bolinhas, não os dígitos: o PIN não fica no DOM (nem como
// `value` de um campo de senha), e a bolinha tem o tamanho do texto, não o do
// disco minúsculo que o navegador desenha num campo de senha.
const dots = computed(() => Array.from(props.pin, () => "●"));
const fieldName = computed(() => props.label || "PIN");
// O que o leitor de tela ouve a cada dígito: quantos já foram, e o mínimo.
const spoken = computed(() =>
  props.pin.length
    ? `${props.pin.length} de no mínimo ${PIN_MIN_DIGITS} dígitos`
    : `PIN de no mínimo ${PIN_MIN_DIGITS} dígitos`,
);

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9"] as const;

function submit() {
  if (!props.canSubmit || props.busy) return;
  emit("submit");
}

function onKeydown(event: KeyboardEvent) {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target as HTMLElement | null;
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
  if (/^[0-9]$/.test(event.key)) {
    event.preventDefault();
    emit("digit", event.key);
  } else if (event.key === "Backspace") {
    event.preventDefault();
    emit("backspace");
  } else if (event.key === "Enter" && props.canSubmit && !props.busy) {
    event.preventDefault();
    submit();
  }
}

onMounted(() => {
  if (props.keyboard) document.addEventListener("keydown", onKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="grid w-full justify-items-center gap-4" data-operator-pin-pad>
    <div class="grid justify-items-center gap-2">
      <p v-if="label" class="text-sm font-medium text-muted-foreground">
        {{ label }}
      </p>
      <!-- Só mostra (`disabled`), com a cor plena: o campo não é o lugar de
           digitar, e não pode parecer apagado. `role="group"` com o nome do
           campo inteiro: o reka nomeia cada casa em inglês (README, "Idioma das
           peças do Nuxt UI"). -->
      <NuxtPinInput
        :model-value="dots"
        :length="slots"
        disabled
        size="xl"
        :color="error ? 'error' : 'neutral'"
        :highlight="Boolean(error)"
        role="group"
        :aria-label="fieldName"
        :ui="{
          root: 'justify-center gap-2',
          base: 'size-12 text-base disabled:cursor-default disabled:opacity-100',
        }"
        data-operator-pin-field
      />
      <span class="sr-only" aria-live="polite">{{ spoken }}</span>
      <NuxtAlert
        v-if="error"
        class="w-full"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :title="error"
      />
    </div>

    <!-- Tecla do tamanho do dedo, não da largura do cartão: a grade tem largura
         própria e o número fica no meio da tecla. `touch-manipulation` desliga o
         double-tap-zoom: dois toques rápidos no mesmo dígito não viram zoom.
         Digitar nunca desabilita (nem durante a verificação): só o CONFIRMAR
         trava, porque o que não pode duplicar é a submissão, não o dígito. -->
    <div class="grid w-full max-w-72 grid-cols-3 gap-2 touch-manipulation">
      <NuxtButton
        v-for="d in KEYS"
        :key="d"
        block
        color="neutral"
        variant="outline"
        size="xl"
        class="h-14 text-xl tabular-nums"
        :label="d"
        @click="emit('digit', d)"
      />
      <NuxtButton
        block
        color="neutral"
        variant="ghost"
        size="xl"
        class="h-14"
        icon="i-lucide-delete"
        aria-label="Apagar o último dígito"
        @click="emit('backspace')"
      />
      <NuxtButton
        block
        color="neutral"
        variant="outline"
        size="xl"
        class="h-14 text-xl tabular-nums"
        label="0"
        @click="emit('digit', '0')"
      />
      <NuxtButton
        block
        size="xl"
        class="h-14"
        :icon="submitIcon"
        :aria-label="submitLabel"
        :disabled="!canSubmit || busy"
        :loading="busy"
        @click="submit"
      />
    </div>
  </div>
</template>
