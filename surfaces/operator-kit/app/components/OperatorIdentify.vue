<script setup lang="ts">
// IDENTIFICAR UMA PESSOA: crachá, ou escolher da lista e digitar o PIN.
//
// Este componente existe porque a mesma pergunta era feita em dois lugares por
// dois componentes diferentes: a tela de bloqueio (`OperatorLock`) e o diálogo
// de autorização do gerente (`OperatorManagerAuth`). Os dois desenhavam o mesmo
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
const username = computed(() =>
  (picked.value?.username ?? typedName.value).trim(),
);
// Sem lista o pad aparece de cara, junto do campo de nome: é o modo de emergência.
const showPad = computed(() => !hasList.value || picked.value !== null);
const canSubmit = computed(() =>
  canSubmitPin(username.value || null, pin.value),
);

// UM caminho de captura para tudo: crachá, teclado físico e botões do pad
// alimentam o mesmo buffer, na hora — dígito nenhum se perde por cadência, e a
// decisão crachá×PIN fica para o Enter (`resolveEnter`). O crachá vale em
// QUALQUER momento desta tela, sem depender de onde está o foco — quem captura
// é o documento; tocar num nome ou no pad não cega o leitor. `busy` nunca
// bloqueia a DIGITAÇÃO (bloquear submissão não pode custar dígito): ele só
// segura o Enter-submete e a resolução de crachá (autorizar duas vezes pelo
// mesmo gesto).
// A moldura modal em volta (overlay da trava ou diálogo): campo de texto dela é
// do dono (o motivo do cancelamento, o nome livre); o que ficou focado FORA dela
// (a busca do PDV atrás do overlay) não recebe as teclas. Ver `useIdentityCapture`.
const root = ref<HTMLElement | null>(null);
const frame = () =>
  root.value?.closest("[data-operator-lock], [role='dialog']") ?? root.value;

const { pin, pressDigit, backspace, clear } = useIdentityCapture({
  frame,
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
const numberedCount = computed(() =>
  Math.min(props.people.length, MAX_NUMBERED),
);

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
watch(
  () => props.error,
  (e) => {
    if (e) clear();
  },
);

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
  emit("pin", {
    person: picked.value,
    username: username.value,
    pin: pin.value,
  });
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
  <div ref="root" class="grid w-full gap-4">
    <!-- Escolher quem é -->
    <template v-if="hasList && !picked">
      <p class="text-center text-sm text-muted-foreground">{{ prompt }}</p>
      <div class="grid grid-cols-2 gap-2" role="group" :aria-label="prompt">
        <!-- Alvo de dedo (`xl`), e o nome inteiro: nome não se corta, quebra
             linha ("Elaine Cristina Souza" a 390 px). -->
        <NuxtButton
          v-for="(person, index) in people"
          :key="person.username"
          block
          color="neutral"
          variant="outline"
          size="xl"
          class="h-auto min-h-12 whitespace-normal"
          :aria-keyshortcuts="
            index < numberedCount ? String(index + 1) : undefined
          "
          @click="pick(person)"
        >
          <NuxtKbd
            v-if="index < numberedCount"
            :value="String(index + 1)"
            aria-hidden="true"
          />
          <span class="min-w-0 text-balance [overflow-wrap:anywhere]">{{ person.name }}</span>
        </NuxtButton>
      </div>
      <p v-if="numberedCount" class="text-center text-xs text-muted-foreground">
        Digite o número para escolher{{
          badgeEnabled !== false ? ", ou passe o crachá" : ""
        }}.
      </p>
      <NuxtAlert
        v-if="error && !showPad"
        color="error"
        variant="subtle"
        :title="error"
      />
    </template>

    <!-- PIN -->
    <template v-if="showPad">
      <!-- Quem foi escolhido, no centro, e o voltar logo abaixo do nome: o
           gesto fica junto da coisa que ele troca. -->
      <div v-if="picked" class="grid justify-items-center gap-1">
        <p class="text-base font-semibold" data-operator-identify-picked>
          {{ picked.name }}
        </p>
        <NuxtButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-chevron-left"
          :label="changeLabel"
          @click="unpick"
        />
      </div>
      <NuxtInput
        v-else-if="allowTypedName"
        v-model="typedName"
        class="w-full"
        :placeholder="nameLabel"
        :aria-label="nameLabel"
        autocomplete="off"
        size="xl"
      />

      <OperatorPinPad
        :pin="pin"
        :error="error"
        :can-submit="canSubmit"
        :busy="busy"
        @digit="pressDigit"
        @backspace="backspace"
        @submit="submit"
      />

      <!-- O crachá segue valendo aqui: a frase existe para o operador saber que
           não precisa terminar de digitar se estiver com ele no pescoço. -->
      <p
        v-if="badgeEnabled !== false"
        class="text-center text-xs text-muted-foreground"
      >
        Ou passe o crachá no leitor.
      </p>

      <slot name="footer" />
    </template>
  </div>
</template>
