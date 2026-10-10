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

// A recusa (PIN errado) se dispensa: no X, ou voltando a digitar.
const errorDismissed = ref(false);
watch(
  () => props.error,
  () => {
    errorDismissed.value = false;
  },
);
watch(
  () => props.pin,
  (next) => {
    if (next.length > 0) errorDismissed.value = true;
  },
);

const showError = computed(() => Boolean(props.error) && !errorDismissed.value);

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
  } else {
    return;
  }
  event.stopPropagation();
}

// O teclado físico vale DENTRO da moldura modal onde a peça mora (o overlay da
// trava, que toma o foco ao subir, ou o diálogo), nunca no documento: atalho
// global é infraestrutura do kit (`useOperatorShortcutMap`), e o que se digita
// aqui não pode chegar à tela de baixo.
const root = ref<HTMLElement | null>(null);
let frame: HTMLElement | null = null;

onMounted(() => {
  if (!props.keyboard || !root.value) return;
  frame = root.value.closest<HTMLElement>("[data-operator-lock], [role='dialog']") ?? root.value;
  frame.addEventListener("keydown", onKeydown);
});
onBeforeUnmount(() => {
  frame?.removeEventListener("keydown", onKeydown);
  frame = null;
});
</script>

<template>
  <div
    ref="root"
    class="grid w-full min-w-0 gap-4 [@media(max-height:43.75rem)]:gap-3 [--op-pin-key:3.5rem] [@media(max-height:47.5rem)]:[--op-pin-key:2.75rem]"
    data-operator-pin-pad
  >
    <!-- Uma coluna só, da largura de quem chama: o campo, o aviso e o teclado
         batem borda com borda (dono, 10/10/2026). As casas dividem a largura do
         teclado, e a casa tem a altura da tecla (`--op-pin-key`): 56 px, e 44 px
         em tela baixa (até 760 px de altura), para a trava caber inteira no
         celular sem rolar (dono, 10/10/2026). 44 px é o piso do alvo de toque. -->
    <div class="grid min-w-0 gap-2">
      <p v-if="label" class="text-center text-sm font-medium text-muted-foreground">
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
        :color="showError ? 'error' : 'neutral'"
        :highlight="showError"
        role="group"
        :aria-label="fieldName"
        :ui="{
          root: 'flex w-full gap-2',
          base: 'size-auto h-(--op-pin-key) w-0 min-w-0 flex-1 text-base disabled:cursor-default disabled:opacity-100',
        }"
        data-operator-pin-field
      />
      <span class="sr-only" aria-live="polite">{{ spoken }}</span>
      <!-- A recusa se dispensa no X, e some sozinha quando se volta a digitar. -->
      <NuxtAlert
        v-if="showError"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :title="error"
        close
        @update:open="errorDismissed = true"
      />
    </div>

    <!-- Tecla do tamanho do dedo, com o número no meio. `touch-manipulation` desliga o
         double-tap-zoom: dois toques rápidos no mesmo dígito não viram zoom.
         Digitar nunca desabilita (nem durante a verificação): só o CONFIRMAR
         trava, porque o que não pode duplicar é a submissão, não o dígito. -->
    <div class="grid grid-cols-3 gap-2 touch-manipulation">
      <NuxtButton
        v-for="d in KEYS"
        :key="d"
        block
        color="neutral"
        variant="outline"
        size="xl"
        class="h-(--op-pin-key) text-xl tabular-nums"
        :label="d"
        @click="emit('digit', d)"
      />
      <NuxtButton
        block
        color="neutral"
        variant="ghost"
        size="xl"
        class="h-(--op-pin-key)"
        icon="i-lucide-delete"
        aria-label="Apagar o último dígito"
        @click="emit('backspace')"
      />
      <NuxtButton
        block
        color="neutral"
        variant="outline"
        size="xl"
        class="h-(--op-pin-key) text-xl tabular-nums"
        label="0"
        @click="emit('digit', '0')"
      />
      <NuxtButton
        block
        size="xl"
        class="h-(--op-pin-key)"
        :icon="submitIcon"
        :aria-label="submitLabel"
        :disabled="!canSubmit || busy"
        :loading="busy"
        @click="submit"
      />
    </div>
  </div>
</template>
