<script setup lang="ts">
// O selo do app na barra de 56px, onde o rail não existe (celular e tablet em pé):
// identidade e caminho para a Central, como o selo do topo do rail (V6-KIT, T-06).
// Uma peça para o `OperatorPageHeader` e para os cabeçalhos próprios (a venda do PDV, a
// Central). O alvo de toque é de 44px (a régua da casa); o selo desenhado tem 36.
// Na própria Central (sem `operatorHubUrl` para onde voltar, ou `home`), é só identidade.
import { computed, ref } from "vue";

import { operatorAppNamed } from "../../appIdentity";

const props = withDefaults(defineProps<{
  /** Na Central: o selo é identidade, sem caminho de volta. */
  home?: boolean;
  placement?: "header" | "rail";
}>(), { home: false, placement: "header" });

interface SealIdentity { label: string; icon: string; iconSrc: string; color: string }

const HUB_BACK = `voltar ${operatorAppNamed("hub", "a")}`;

const config = useRuntimeConfig().public as { operatorHubUrl?: string; operatorPwa?: { identity?: SealIdentity } };
const identity = config.operatorPwa?.identity;
const hubUrl = computed(() => (props.home ? "" : config.operatorHubUrl || ""));
const appColor = identity?.color || "var(--primary)";
const { attrsFor } = useOperatorAppLink();
const hubLink = computed(() => attrsFor(hubUrl.value));
const broken = ref(false);
const iconName = computed(() => {
  const icon = identity?.icon || "layout-grid";
  return icon.includes(":") ? icon : `lucide:${icon}`;
});
</script>

<template>
  <NuxtButton
    :to="hubUrl || undefined"
    :target="hubUrl ? hubLink.target : undefined"
    :rel="hubUrl ? hubLink.rel : undefined"
    color="neutral"
    variant="ghost"
    square
    :class="placement === 'header' ? '-mx-1 my-1.5 rail:hidden' : ''"
    :aria-label="hubUrl ? `${identity?.label || 'App'}: ${HUB_BACK}` : identity?.label || undefined"
    data-page-header-app
  >
    <NuxtAvatar :src="identity?.iconSrc && !broken ? identity.iconSrc : undefined" :icon="iconName" :style="{ background: appColor }" @error="broken = true" />
  </NuxtButton>
</template>
