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

const dotClass = computed(() => {
  switch (props.tone) {
    case "calm": return "bg-muted-foreground shadow-[0_0_0_3px_color-mix(in_oklab,var(--muted-foreground)_18%,transparent)]";
    case "late": return "bg-warning shadow-[0_0_0_3px_color-mix(in_oklab,var(--warning)_22%,transparent)]";
    case "off": return "bg-destructive shadow-[0_0_0_3px_color-mix(in_oklab,var(--destructive)_22%,transparent)]";
    default: return "";
  }
});
const showLabel = computed(() => props.tone !== "live" || !props.time);
const accessible = computed(() => [props.label, props.time && `última leitura ${props.time}`, props.detail].filter(Boolean).join(". "));
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center gap-1.5 op-micro tnum text-muted-foreground"
    role="status"
    :aria-label="accessible"
    :title="accessible"
    :data-live-tone="tone"
    data-operator-live-status
  >
    <span class="live-dot" :class="dotClass" aria-hidden="true" />
    <span v-if="time" class="max-[379px]:hidden" aria-hidden="true">{{ time }}</span>
    <span
      v-if="showLabel"
      aria-hidden="true"
      :class="tone === 'late' ? 'font-semibold text-warning' : tone === 'off' ? 'font-semibold text-destructive' : ''"
    >{{ label }}</span>
  </span>
</template>
