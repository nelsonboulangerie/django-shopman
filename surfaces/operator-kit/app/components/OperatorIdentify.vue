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
import { canSubmitPin } from "../presentation/operatorLock";
import { useIdentityCapture } from "../composables/useIdentityCapture";

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

const hasList = computed(() => props.people.length > 0);
const username = computed(() => (picked.value?.username ?? typedName.value).trim());
// Sem lista o pad aparece de cara, junto do campo de nome: é o modo de emergência.
const showPad = computed(() => !hasList.value || picked.value !== null);
const canSubmit = computed(() => canSubmitPin(username.value || null, pin.value));

// UM caminho de captura para tudo: crachá, teclado físico e botões do pad
// alimentam o mesmo buffer, na hora — dígito nenhum se perde por cadência, e a
// decisão crachá×PIN fica para o Enter (`resolveEnter`). O crachá vale em
// QUALQUER momento desta tela, sem depender de onde está o foco — quem captura
// é o documento; tocar num nome ou no pad não cega o leitor. `busy` nunca
// bloqueia a DIGITAÇÃO (bloquear submissão não pode custar dígito): ele só
// segura o Enter-submete e a resolução de crachá (autorizar duas vezes pelo
// mesmo gesto).
const { pin, pressDigit, backspace, clear } = useIdentityCapture({
  padVisible: () => showPad.value,
  badgeEnabled: () => props.badgeEnabled !== false && !props.busy,
  canSubmitEnter: () => canSubmit.value && !props.busy,
  onBadge: (token) => emit("badge", token),
  onSubmit: () => submit(),
  onDigitPick: (digit) => pickByNumber(digit),
});

// A lista é numerada: "2" escolhe o segundo. Antes só o dedo escolhia, e num
// balcão com teclado (ou com o kiosk sem mouse à mão) trocar de operador
// obrigava a mirar num alvo — a única etapa da identificação que ainda pedia
// ponteiro, já que o PIN e o crachá são teclado puro. Nove é o teto porque é
// até onde uma tecla única alcança; do décimo em diante o toque continua sendo
// o caminho, sem número prometendo atalho que não existe.
const MAX_NUMBERED = 9;
const numberedCount = computed(() => Math.min(props.people.length, MAX_NUMBERED));

/** Escolha pelo número, SEM limpar o buffer de captura — o dígito pode ser a
 *  primeira tecla de um crachá, e o token tem de chegar inteiro ao Enter. */
function pickByNumber(digit: string) {
  const index = Number(digit) - 1;
  if (index < 0 || index >= numberedCount.value) return;
  const person = props.people[index];
  if (!person) return;
  picked.value = person;
}

// Recusa apaga só o PIN: quem foi escolhido continua escolhido, senão a pessoa
// reescolheria o próprio nome a cada dedo errado no teclado.
watch(() => props.error, (e) => { if (e) clear(); });

function pick(person: IdentifiablePerson) {
  picked.value = person;
  clear();
}

function unpick() {
  picked.value = null;
  clear();
}

function submit() {
  if (!canSubmit.value || props.busy) return;
  emit("pin", { person: picked.value, username: username.value, pin: pin.value });
}

/** Para o pai limpar entre aberturas sem conhecer o estado interno. */
function reset(keepPicked = false) {
  clear();
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
          v-for="(person, index) in people"
          :key="person.username"
          type="button"
          class="flex touch-manipulation select-none items-center gap-2 rounded-lg border bg-background px-3 py-3 text-left text-sm font-medium transition hover:bg-accent"
          :aria-keyshortcuts="index < numberedCount ? String(index + 1) : undefined"
          @click="pick(person)"
        >
          <kbd
            v-if="index < numberedCount"
            class="shrink-0 rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground"
            aria-hidden="true"
          >{{ index + 1 }}</kbd>
          <span class="min-w-0 truncate">{{ person.name }}</span>
        </button>
      </div>
      <p v-if="numberedCount" class="text-center text-xs text-muted-foreground">
        Digite o número para escolher{{ badgeEnabled !== false ? ", ou passe o crachá" : "" }}.
      </p>
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
        aria-live="polite"
        :aria-label="`${pin.length} dígitos`"
      >
        {{ "•".repeat(pin.length) || "—" }}
      </div>

      <!-- `touch-manipulation` desliga o double-tap-zoom do browser nos botões:
           sem ele, dois toques rápidos no mesmo dígito viram gesto de zoom e o
           clique some — o pad tem que aguentar dedo apressado. Digitar nunca
           desabilita (nem durante verificação): só o CONFIRMAR trava, porque
           o que não pode duplicar é a submissão, não o dígito. -->
      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="d in ['1', '2', '3', '4', '5', '6', '7', '8', '9']"
          :key="d"
          type="button"
          class="touch-manipulation select-none rounded-lg border bg-background py-3 text-lg font-semibold transition hover:bg-accent"
          @click="pressDigit(d)"
        >
          {{ d }}
        </button>
        <button
          type="button"
          aria-label="Apagar"
          class="touch-manipulation select-none rounded-lg border bg-background py-3 text-sm transition hover:bg-accent"
          @click="backspace"
        >
          <Icon name="lucide:delete" class="mx-auto size-5" />
        </button>
        <button
          type="button"
          class="touch-manipulation select-none rounded-lg border bg-background py-3 text-lg font-semibold transition hover:bg-accent"
          @click="pressDigit('0')"
        >
          0
        </button>
        <button
          type="button"
          aria-label="Confirmar"
          :disabled="!canSubmit || busy"
          class="touch-manipulation select-none rounded-lg border border-transparent bg-primary py-3 text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
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
