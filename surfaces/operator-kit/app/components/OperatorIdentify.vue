<script setup lang="ts">
// IDENTIFICAR UMA PESSOA: crachá, ou escolher da lista e digitar o PIN.
//
// Este componente existe porque a mesma pergunta era feita em dois lugares por
// dois componentes diferentes: a tela de bloqueio (`OperatorLock`) e o diálogo
// de autorização do gerente (`PosManagerAuthDialog`). Os dois desenhavam o mesmo
// seletor e o mesmo teclado — e só um sabia ler crachá.
//
// A consequência não era estética. Sangria e pedido de troco são a hora em que o
// gerente mais aparece no balcão, e era exatamente ali que o crachá no pescoço
// dele não servia para nada: só o login normal lia. Duplicar estrutura não custa
// código repetido, custa recurso que existe num lugar e falta no outro.
//
// O que MUDA entre os dois usos é a moldura (tela cheia × diálogo), quem pode
// aparecer, e o que acontece no sucesso. Nada disso é identificação, então nada
// disso mora aqui: o componente emite `pin` ou `badge` e quem chamou decide.
import { appendPinDigit, canSubmitPin } from "../presentation/operatorLock";
import { useBadgeScanner } from "../composables/useBadgeScanner";

/** O mínimo que serve para escolher alguém. `OperatorCard` e o gerente do PDV cabem. */
export interface IdentifiablePerson {
  username: string;
  name: string;
}

const props = withDefaults(
  defineProps<{
    people?: readonly IdentifiablePerson[];
    busy?: boolean;
    error?: string;
    /** Desliga o leitor (ex.: enquanto um formulário de texto está aberto). */
    badgeEnabled?: boolean;
    /** Pergunta acima da lista. */
    prompt?: string;
    /** Rótulo do voltar. "Trocar operador" / "Trocar gerente". */
    changeLabel?: string;
    /**
     * Rótulo do campo de nome livre. "Nome do gerente" diz de quem é o nome —
     * num diálogo de autorização, "Nome" sozinho deixa o leitor de tela (e a
     * pessoa apressada) sem saber se é o dela ou o de quem assina.
     */
    nameLabel?: string;
    /**
     * Lista vazia libera digitar o nome. É a ÚNICA porta quando ninguém foi
     * provisionado ou a leitura falhou — esconder deixaria o balcão sem saída no
     * meio de uma sangria.
     */
    allowTypedName?: boolean;
  }>(),
  {
    people: () => [],
    badgeEnabled: true,
    prompt: "Quem está operando?",
    changeLabel: "Trocar operador",
    nameLabel: "Nome",
    allowTypedName: false,
  },
);

const emit = defineEmits<{
  pin: [{ person: IdentifiablePerson | null; username: string; pin: string }];
  badge: [string];
}>();

const picked = ref<IdentifiablePerson | null>(null);
const typedName = ref("");
const pin = ref("");

const hasList = computed(() => props.people.length > 0);
const username = computed(() => (picked.value?.username ?? typedName.value).trim());
// Sem lista o pad aparece de cara, junto do campo de nome: é o modo de emergência.
const showPad = computed(() => !hasList.value || picked.value !== null);
const canSubmit = computed(() => canSubmitPin(username.value || null, pin.value));

// O crachá vale em QUALQUER momento desta tela, sem depender de onde está o foco
// — quem captura é o documento. Tocar num nome ou no pad não cega o leitor, que
// era o defeito da versão com campo escondido.
useBadgeScanner((token) => emit("badge", token), {
  enabled: () => props.badgeEnabled !== false && !props.busy,
});

// Recusa apaga só o PIN: quem foi escolhido continua escolhido, senão a pessoa
// reescolheria o próprio nome a cada dedo errado no teclado.
watch(() => props.error, (e) => { if (e) pin.value = ""; });

function pick(person: IdentifiablePerson) {
  picked.value = person;
  pin.value = "";
}

function unpick() {
  picked.value = null;
  pin.value = "";
}

function press(digit: string) {
  pin.value = appendPinDigit(pin.value, digit);
}

function backspace() {
  pin.value = pin.value.slice(0, -1);
}

function submit() {
  if (!canSubmit.value || props.busy) return;
  emit("pin", { person: picked.value, username: username.value, pin: pin.value });
}

// PIN pelo TECLADO FÍSICO: o balcão com teclado não deveria exigir mouse para
// quatro dígitos. O listener mora no documento enquanto o pad está visível (o
// componente só existe dentro do overlay/diálogo), roteia 0-9/Backspace/Enter
// para o buffer e CONSOME a tecla, para ela não vazar aos atalhos da tela por
// baixo. Não colide com o wedge do crachá: a cadência separa — a rajada do
// leitor é consumida antes, na fase de captura (useBadgeScanner), e só a
// primeira tecla dela chega até aqui.
function onDocumentKeydown(event: KeyboardEvent) {
  if (!showPad.value || props.busy) return;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target as HTMLElement | null;
  const editing = !!target
    && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
  if (editing) return; // campo de texto de verdade (nome livre): as teclas são dele
  if (/^[0-9]$/.test(event.key)) {
    event.preventDefault();
    event.stopPropagation();
    press(event.key);
  } else if (event.key === "Backspace") {
    event.preventDefault();
    event.stopPropagation();
    backspace();
  } else if (event.key === "Enter" && canSubmit.value) {
    event.preventDefault();
    event.stopPropagation();
    submit();
  }
}
onMounted(() => document.addEventListener("keydown", onDocumentKeydown));
onBeforeUnmount(() => document.removeEventListener("keydown", onDocumentKeydown));

/** Para o pai limpar entre aberturas sem conhecer o estado interno. */
function reset(keepPicked = false) {
  pin.value = "";
  if (keepPicked) return;
  picked.value = null;
  typedName.value = "";
}

defineExpose({ reset });
</script>

<template>
  <div class="grid w-full gap-3">
    <!-- Escolher quem é -->
    <template v-if="hasList && !picked">
      <p class="text-center text-sm text-muted-foreground">{{ prompt }}</p>
      <div class="grid grid-cols-2 gap-2" role="group" :aria-label="prompt">
        <button
          v-for="person in people"
          :key="person.username"
          type="button"
          class="rounded-lg border bg-background px-3 py-3 text-left text-sm font-medium transition hover:bg-accent"
          @click="pick(person)"
        >
          {{ person.name }}
        </button>
      </div>
      <p v-if="error && !showPad" class="text-center text-sm font-medium text-destructive" role="alert">
        {{ error }}
      </p>
    </template>

    <!-- PIN -->
    <template v-if="showPad">
      <div v-if="picked" class="grid gap-1">
        <button
          type="button"
          class="inline-flex items-center gap-1 self-start text-sm text-muted-foreground hover:text-foreground"
          @click="unpick"
        >
          <Icon name="lucide:chevron-left" class="size-4" />
          {{ changeLabel }}
        </button>
        <p class="text-center text-sm font-semibold">{{ picked.name }}</p>
      </div>
      <UiInput
        v-else-if="allowTypedName"
        v-model="typedName"
        :placeholder="nameLabel"
        :aria-label="nameLabel"
        autocomplete="off"
        class="h-11 w-full text-center text-base"
      />

      <p v-if="error" class="text-center text-sm font-medium text-destructive" role="alert">
        {{ error }}
      </p>

      <div
        class="flex h-10 items-center justify-center rounded-md border bg-background text-3xl tracking-[0.4em] tabular-nums"
      >
        {{ "•".repeat(pin.length) || "—" }}
      </div>

      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="d in ['1', '2', '3', '4', '5', '6', '7', '8', '9']"
          :key="d"
          type="button"
          class="rounded-lg border bg-background py-3 text-lg font-semibold transition hover:bg-accent"
          @click="press(d)"
        >
          {{ d }}
        </button>
        <button
          type="button"
          aria-label="Apagar"
          class="rounded-lg border bg-background py-3 text-sm transition hover:bg-accent"
          @click="backspace"
        >
          <Icon name="lucide:delete" class="mx-auto size-5" />
        </button>
        <button
          type="button"
          class="rounded-lg border bg-background py-3 text-lg font-semibold transition hover:bg-accent"
          @click="press('0')"
        >
          0
        </button>
        <button
          type="button"
          aria-label="Confirmar"
          :disabled="!canSubmit || busy"
          class="rounded-lg border border-transparent bg-primary py-3 text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          @click="submit"
        >
          <Icon name="lucide:check" class="mx-auto size-5" />
        </button>
      </div>

      <!-- O crachá segue valendo aqui: a frase existe para o operador saber que
           não precisa terminar de digitar se estiver com ele no pescoço. -->
      <p v-if="badgeEnabled !== false" class="text-center text-xs text-muted-foreground">
        Ou passe o crachá no leitor.
      </p>

      <slot name="footer" />
    </template>
  </div>
</template>
