<script setup lang="ts">
// A faixa do cabeçalho (D, dono 13/11/2026, variante 3: "descolada, invertida"). O
// aviso da tela e o que o sistema fez sozinho ("O sistema fez" do Gestor) moram aqui:
// descolado, com cantos e sombra, na cor invertida da tela, como a barra flutuante
// (escuro no claro, creme no escuro). É o `NuxtAlert` oficial dentro de um escopo
// `.op-inverse` (`operator-theme.css`): o texto, os botões e o fechar leem os tokens da
// polaridade oposta e saem certos sem classe própria. A gravidade (`tone`) fica no
// ícone e na ação, que a tela passa por `alertActions(tone, ...)`; o fundo é um só.
// Tudo o que não é tom passa direto ao aviso (`title`, `description`, `icon`,
// `actions`, `close`, `orientation` e os slots).
import { computed } from "vue";

type BandTone = "primary" | "info" | "success" | "warning" | "error" | "neutral";

defineOptions({ inheritAttrs: false });
const props = withDefaults(
  defineProps<{ tone?: BandTone; ui?: Record<string, string> }>(),
  { tone: "neutral", ui: () => ({}) },
);

const TONE_ICON: Record<BandTone, string> = {
  primary: "text-primary",
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
  error: "text-error",
  neutral: "",
};

const bandUi = computed(() => ({
  ...props.ui,
  icon: [TONE_ICON[props.tone], props.ui.icon].filter(Boolean).join(" "),
}));
</script>

<template>
  <NuxtAlert
    v-bind="$attrs"
    color="neutral"
    variant="outline"
    class="op-inverse"
    :ui="bandUi"
    :data-tone="tone"
    data-operator-band
  >
    <template v-for="(_, name) in $slots" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps ?? {}" />
    </template>
  </NuxtAlert>
</template>
