<script setup lang="ts">
// "Ao vivo" discreto, ao lado do título (prévias v3: um ponto com a hora). Só cresce
// quando a leitura atrasa: aí o texto aparece por extenso ("Sem conexão", "Atualiza a
// cada 30 s"), porque a cor nunca fala sozinha. O detalhe completo fica no `title` e no
// nome acessível (`role="status"`).
//
// Tons:
//   live  → ponto verde, só a hora;
//   calm  → ponto neutro, a hora + o rótulo curto (o quadro segue atualizando sozinho);
//   late  → ponto âmbar, rótulo por extenso;
//   off   → ponto vermelho, rótulo por extenso.
import { computed } from "vue";

const props = withDefaults(defineProps<{
  tone?: "live" | "calm" | "late" | "off";
  /** A hora da última leitura útil ("22:03"). */
  time?: string;
  /** Rótulo curto do estado ("Ao vivo", "Atualiza a cada 30 s", "Sem conexão"). */
  label: string;
  /** Detalhe para o toque/hover e leitor de tela. */
  detail?: string;
}>(), { tone: "live", time: "", detail: "" });

const badgeColor = computed(() => {
  switch (props.tone) {
    case "late": return "warning" as const;
    case "off": return "error" as const;
    case "live": return "success" as const;
    default: return "neutral" as const;
  }
});
const showLabel = computed(() => props.tone !== "live" || !props.time);
const accessible = computed(() => [props.label, props.time && `última leitura ${props.time}`, props.detail].filter(Boolean).join(". "));
const display = computed(() => [showLabel.value ? props.label : "", props.time].filter(Boolean).join(" · "));
</script>

<template>
  <NuxtBadge
    :color="badgeColor"
    variant="subtle"
    icon="i-lucide-radio"
    :label="display"
    role="status"
    :aria-label="accessible"
    :title="accessible"
    :data-live-tone="tone"
    data-operator-live-status
  />
</template>
