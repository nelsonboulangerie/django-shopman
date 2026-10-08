<script setup lang="ts">
// Estado compacto da atualização automática. O texto visível responde somente à
// pergunta operacional (ON/OFF) e mantém a hora da última leitura; o rótulo completo
// continua no nome acessível e no title.
//
// Cor binária do estado: todo On é success; Off é error. `calm` e `late`
// continuam enriquecendo o rótulo acessível, sem criar uma terceira leitura
// cromática para um estado que permanece ligado.
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    tone?: "live" | "calm" | "late" | "off";
    /** A hora da última leitura útil ("22:03"). */
    time?: string;
    /** Rótulo curto do estado ("Ao vivo", "Atualiza a cada 30 s", "Sem conexão"). */
    label: string;
    /** Detalhe para o toque/hover e leitor de tela. */
    detail?: string;
  }>(),
  { tone: "live", time: "", detail: "" },
);

const badgeColor = computed(() => {
  return props.tone === "off" ? ("error" as const) : ("success" as const);
});
const accessible = computed(() =>
  [
    props.label,
    props.tone !== "off" && props.time && `última leitura ${props.time}`,
    props.detail,
  ]
    .filter(Boolean)
    .join(". "),
);
const state = computed(() => (props.tone === "off" ? "Off" : "On"));
// Desligado não tem “hora da última leitura” no rótulo: ela pareceria a hora em
// que o modo foi desligado ou uma leitura ainda vigente. O detalhe acessível
// continua explicando o estado completo.
const display = computed(() =>
  props.tone === "off"
    ? state.value
    : [state.value, props.time].filter(Boolean).join(" "),
);
</script>

<template>
  <NuxtBadge
    :color="badgeColor"
    :label="display"
    role="status"
    :aria-label="accessible"
    :title="accessible"
    :data-live-tone="tone"
    data-operator-live-status
  >
    <template #leading>
      <NuxtChip as="span" :color="badgeColor" size="xl" inset standalone />
    </template>
  </NuxtBadge>
</template>
