<script setup lang="ts">
// O selo "ao vivo" do cabeçalho, pelo contrato do README do kit ("o ponto ao vivo com
// a hora; fora do ao vivo o estado se escreve por extenso"), confirmado pelo dono em
// 08/10/2026 (onda 0.M; o ponto vermelho do "Sem conexão" é do PR #1539):
//
//   live  ponto verde e a hora da última leitura ("10:12").
//   calm  neutro, sem ponto, a cadência por extenso ("Atualiza sozinho a cada 60 s", o rótulo
//         que o app passa, porque a cadência é dele).
//   late  âmbar, com ponto: "Última leitura às 10:04".
//   off   ponto vermelho e "Sem conexão".
//
// A cor nunca fala sozinha: cada tom tem texto próprio. O rótulo completo do app, a
// hora e o detalhe vão para o nome acessível e o `title`. Não existe "On"/"Off"
// visível. Badge sem `variant`: é o `soft` do tema; o Chip leva o anel `ring-2` do
// tema (conjunto mínimo, PR #1539).
//
// O RÓTULO QUE CABE (dono, 10/10/2026; o selo do Gestor saía "Atualiza sozinho a
// cada" cortado a 800 px, 13/10/2026). Um invólucro é o contêiner (`op-fit-scope`):
// pede a largura do rótulo completo, encolhe com a barra, e o selo dentro dele troca
// de degrau pelo CSS do encaixe (`operator-fit.css`), sem JS. O selo tem a largura
// do texto que mostra; no degrau 2 a sobra do invólucro fica vazia à direita (o selo
// não estica para preencher):
//
//   1. o rótulo completo;
//   2. o curto ESCRITO pelo app (`shortLabel`, "A cada 30 s"); nunca um corte;
//   3. só o sinal: o ponto (live/late/off) ou o ícone de atualizar (calm), com o
//      rótulo completo no nome acessível e na dica.
//
// Quem põe o selo dentro de outro invólucro dá `min-w-0` a ele, ou o invólucro
// segura a largura do completo e o selo não encolhe. Atributos de fora (`class`,
// `data-*`) vão para o selo, não para o invólucro.
import { computed, useAttrs } from "vue";

import { labelWidthEm } from "../presentation/actionLabel";

const props = withDefaults(
  defineProps<{
    tone?: "live" | "calm" | "late" | "off";
    /** A hora da última leitura útil ("22:03"). */
    time?: string;
    /** Rótulo curto do estado ("Ao vivo", "Atualiza sozinho a cada 30 s", "Sem conexão"). */
    label: string;
    /** O rótulo curto do estado calmo, escrito pelo app ("A cada 30 s"). Sem ele, o
     *  selo vai do completo direto ao sinal. */
    shortLabel?: string;
    /** Detalhe para o toque/hover e leitor de tela. */
    detail?: string;
  }>(),
  { tone: "live", time: "", shortLabel: "", detail: "" },
);

defineOptions({ inheritAttrs: false });
const attrs = useAttrs();

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

// A anatomia do `NuxtBadge` `md` (tema oficial do Nuxt UI 4: `text-xs px-2 gap-1`,
// ícone `size-4`) e do `NuxtChip` `xl` (10 px), em `rem`.
const PAD_REM = 0.5;
const GAP_REM = 0.25;
const DOT_REM = 0.625;
const ICON_REM = 1;

/** O curto só existe no calmo: nos outros tons o texto já é a coisa (a hora, "Sem conexão"). */
const short = computed(() => {
  const value = props.tone === "calm" ? props.shortLabel.trim() : "";
  return value && value !== display.value ? value : "";
});

function length(text: string, leadRem: number): string {
  const em = Math.round(labelWidthEm(text) * 1000) / 1000;
  return `calc(${em}em + ${leadRem}rem)`;
}

// As larguras são do selo inteiro (texto, sinal e respiro), comparadas com o
// `100cqi` do invólucro. O quarto de pixel a mais é a folga do degrau 1: com o
// invólucro EXATAMENTE do tamanho do completo, a conta do encaixe dá zero e o texto
// sumiria no selo que tem espaço de sobra.
const fitStyle = computed(() => {
  const lead = (dotted.value ? DOT_REM + GAP_REM : 0) + PAD_REM * 2;
  const full = length(display.value, lead);
  return {
    "--op-fit-full": full,
    "--op-fit-short": short.value ? length(short.value, lead) : full,
    width: "calc(var(--op-fit-full) + 0.25px)",
    minWidth: `${PAD_REM * 2 + (dotted.value ? DOT_REM : ICON_REM)}rem`,
    maxWidth: "100%",
    flexShrink: "1",
  };
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
  <span class="op-fit-scope inline-flex items-center text-xs" :style="fitStyle" data-live-fit>
  <NuxtBadge
    v-bind="attrs"
    :color="badgeColor"
    class="max-w-full"
    role="status"
    :aria-label="accessible"
    :title="accessible"
    :data-live-tone="tone"
    data-operator-live-status
  >
    <template #leading>
      <NuxtChip v-if="dotted" as="span" :color="badgeColor" size="xl" inset standalone />
      <!-- Degrau 3 do calmo: o ícone de atualizar aparece só quando o texto some. -->
      <Icon
        v-else
        name="lucide:refresh-cw"
        class="op-live-sign size-4 shrink-0 overflow-hidden"
        aria-hidden="true"
        data-live-sign
      />
    </template>
    <span class="op-live-text inline-flex min-w-0" data-live-text>
      <span class="op-fit-text" :data-op-fit-variant="short ? 'full' : 'only'">{{ display }}</span>
      <span
        v-if="short"
        class="op-fit-text"
        aria-hidden="true"
        data-op-fit-variant="short"
        :data-op-fit-short="short"
      />
    </span>
  </NuxtBadge>
  </span>
</template>

<style scoped>
/* O sinal do degrau 3 (o ícone do calmo) só aparece abaixo do curto; acima, some e
   devolve o espaço do `gap`. O texto faz o contrário: abaixo do curto, some e devolve
   o `gap` que o separava do sinal. Mesma conta do `operator-fit.css`. */
.op-live-sign {
  max-width: clamp(0px, calc((var(--op-fit-short) - 100cqi) * 100000), 1rem);
  margin-inline-end: clamp(-0.25rem, calc((var(--op-fit-short) - 100cqi) * 100000 - 0.25rem), 0px);
}
.op-live-text {
  margin-inline-start: clamp(-0.25rem, calc((100cqi - var(--op-fit-short)) * 100000), 0px);
}
</style>
