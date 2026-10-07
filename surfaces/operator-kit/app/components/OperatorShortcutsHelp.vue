<script setup lang="ts">
// A ajuda de atalhos da suíte (V6-KIT, K03/T-02): uma peça, oito apps.
//
// Nasceu no PDV (`PosShortcutsHelp`) e na Produção (`ProductionShortcutsHelp`), cada um
// com a sua cópia; os outros seis não tinham painel nenhum, e a v4 põe "Atalhos (?)"
// no pé do rail de todo app. Aqui ela LISTA o que o teclado faz: o grupo "Em todo o
// app" sai das seções do rail (Alt 1…9), e a tela que tem teclas próprias entrega os
// grupos dela com `provideOperatorShortcuts`. Só lista: quem executa é o handler de
// cada tela (e o Alt+N, que é do rail).
//
// Abre pelo "Atalhos" do rail e pela tecla "?". AlertDialog não: é Dialog, e Esc ou
// toque fora fecham, porque não há nada a perder.
import { computed } from "vue";

import type { OperatorSection } from "../presentation/appBar";
import {
  mergeShortcutGroups,
  suiteShortcutGroup,
} from "../presentation/suiteChrome";

const props = withDefaults(
  defineProps<{
    /** As seções de cima do rail, na ordem (dão o Alt 1…9). */
    sections: readonly OperatorSection[];
    /** "Gestor", "PDV": o título do grupo comum ("Em todo o Gestor"). */
    appLabel?: string;
  }>(),
  { appLabel: "" },
);

const { open, groups, description } = useOperatorShortcuts();

const allGroups = computed(() =>
  mergeShortcutGroups(
    suiteShortcutGroup(props.sections, { appLabel: props.appLabel }),
    groups.value,
  ),
);
</script>

<template>
  <NuxtModal
    v-model:open="open"
    title="Atalhos do teclado"
    :description="
      description ||
      'Toque e teclado fazem as mesmas coisas. Os atalhos pausam enquanto você digita ou com um diálogo aberto.'
    "
    data-operator-shortcuts-help
  >
    <template #body>
      <div class="grid gap-4">
        <template v-for="(group, index) in allGroups" :key="group.title">
          <section class="grid gap-3" data-shortcut-group>
            <h3 class="font-medium text-highlighted">{{ group.title }}</h3>
            <ul class="grid gap-2">
              <li
                v-for="item in group.items"
                :key="`${item.keys.join('+')}-${item.label}`"
                class="flex items-center justify-between gap-3"
              >
                <span class="min-w-0">{{ item.label }}</span>
                <span class="flex shrink-0 items-center gap-1">
                  <NuxtKbd v-for="key in item.keys" :key="key" :value="key" />
                </span>
              </li>
            </ul>
          </section>
          <NuxtSeparator v-if="index < allGroups.length - 1" />
        </template>
      </div>
    </template>
  </NuxtModal>
</template>
