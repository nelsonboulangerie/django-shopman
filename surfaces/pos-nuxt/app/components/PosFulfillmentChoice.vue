<script setup lang="ts">
// RETIRADA OU ENTREGA, a escolha em si. Uma peça só para os dois lugares do PDV
// que perguntam isso: o diálogo Recebimento e a etapa "Entrega ou retirada?" do
// assistente da encomenda. Eram dois pares de botões, e o do assistente ficou com
// o sinal antigo (o escolhido só mudava a borda e um tom de fundo) quando o do
// diálogo mudou (#2806, #2815).
//
// A peça é o grupo de rádio do Nuxt UI (variante cartão), o mesmo da lista de
// endereços do cliente (`PosSavedAddressList`): o rádio cheio, a borda e o fundo
// da cor da casa no escolhido, e o estado no papel (`role="radio"` +
// `aria-checked`). Nada vem marcado antes do toque: o recebimento é escolha
// explícita. As setas trocam (e escolhem, como em todo grupo de rádio); o Enter,
// que o grupo do Reka ignora de propósito, escolhe a opção em foco, como fazia no
// botão que ela substituiu.
//
// Quem decide o que acontece depois da escolha é quem usa a peça: o diálogo
// mostra o endereço; o assistente leva o foco ao gesto que segue.
import type { POSFulfillmentOptionProjection } from "~/types/pos";

type FulfillmentRef = "pickup" | "delivery";

const props = defineProps<{
  options: POSFulfillmentOptionProjection[];
  /** A forma escolhida; "" enquanto o operador não escolheu. */
  chosen: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  /** O operador escolheu (toque, espaço, Enter ou seta). */
  pick: [FulfillmentRef];
}>();

// O valor é texto (e não o tipo estreito "pickup" | "delivery") para o "" de
// nenhuma escolha caber no mesmo tipo do grupo.
const items = computed(() => props.options.map((option) => ({
  value: String(option.ref),
  label: option.label,
  description: option.description,
})));

function pick(value: unknown) {
  const ref = String(value ?? "");
  if (ref !== "pickup" && ref !== "delivery") return;
  emit("pick", ref);
}

const root = useTemplateRef<HTMLElement>("root");
const radios = () => Array.from(root.value?.querySelectorAll<HTMLElement>('[role="radio"]') ?? []);

function onEnter(event: KeyboardEvent) {
  if (event.isComposing || props.disabled) return;
  const radio = (event.target as HTMLElement | null)?.closest<HTMLElement>('[role="radio"]');
  if (!radio) return;
  const option = props.options[radios().indexOf(radio)];
  if (!option) return;
  event.preventDefault();
  pick(option.ref);
}

/** Onde o foco do teclado deve cair: na opção marcada, ou na primeira. */
function focusTarget(): HTMLElement | null {
  const all = radios();
  return all.find((radio) => radio.getAttribute("aria-checked") === "true") ?? all[0] ?? null;
}
defineExpose({ focusTarget });
</script>

<template>
  <div ref="root" @keydown.enter="onEnter">
    <NuxtRadioGroup
      :model-value="chosen"
      :items="items"
      variant="card"
      orientation="horizontal"
      aria-label="Como o cliente recebe"
      :disabled="disabled"
      :ui="{ fieldset: 'grid grid-cols-2 gap-2', item: 'w-full min-w-0', wrapper: 'min-w-0', label: 'break-words', description: 'break-words' }"
      @update:model-value="pick"
    />
  </div>
</template>
