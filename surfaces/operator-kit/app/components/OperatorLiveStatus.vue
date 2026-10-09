<script setup lang="ts">
// O selo "ao vivo" do cabeçalho, pelo contrato do README do kit ("o ponto ao vivo com
// a hora; fora do ao vivo o estado se escreve por extenso"), confirmado pelo dono em
// 08/10/2026 (onda 0.M; o ponto vermelho do "Sem conexão" é do PR #1539):
//
//   live  ponto verde e a hora da última leitura ("10:12").
//   calm  neutro, sem ponto, a cadência por extenso ("Atualiza a cada 60 s", o rótulo
//         que o app passa, porque a cadência é dele).
//   late  âmbar, com ponto: "Última leitura às 10:04".
//   off   ponto vermelho e "Sem conexão".
//
// A cor nunca fala sozinha: cada tom tem texto próprio. O rótulo completo do app, a
// hora e o detalhe vão para o nome acessível e o `title`. Não existe "On"/"Off"
// visível. Badge sem `variant`: é o `soft` do tema; o Chip leva o anel `ring-2` do
// tema (conjunto mínimo, PR #1539).
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

const OFF_LABEL = "Sem conexão";

const TONE_COLOR = {
  live: "success",
  calm: "neutral",
  late: "warning",
  off: "error",
} as const;

const badgeColor = computed(() => TONE_COLOR[props.tone]);
/** Ponto só onde o estado é uma leitura no tempo (ao vivo, atrasada) ou a falta dela. */
const dotted = computed(() => props.tone !== "calm");

const display = computed(() => {
  if (props.tone === "live") return props.time || props.label;
  if (props.tone === "late")
    return props.time ? `Última leitura às ${props.time}` : props.label;
  if (props.tone === "off") return OFF_LABEL;
  return props.label;
});

// Desligado não anuncia "hora da última leitura" como se fosse vigente: a hora só
// entra no nome acessível pelo detalhe que o app escreve.
const accessible = computed(() =>
  [
    props.tone === "off" ? OFF_LABEL : props.label,
    props.tone === "off" && props.label !== OFF_LABEL ? props.label : "",
    props.tone !== "off" && props.time && `última leitura ${props.time}`,
    props.detail,
  ]
    .filter(Boolean)
    .join(". "),
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
    <template v-if="dotted" #leading>
      <NuxtChip as="span" :color="badgeColor" size="xl" inset standalone />
    </template>
  </NuxtBadge>
</template>
