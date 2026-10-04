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
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from "reka-ui";

import type { OperatorSection } from "../presentation/appBar";
import { mergeShortcutGroups, suiteShortcutGroup } from "../presentation/suiteChrome";

const props = withDefaults(defineProps<{
  /** As seções de cima do rail, na ordem (dão o Alt 1…9). */
  sections: readonly OperatorSection[];
  /** "Gestor", "PDV": o título do grupo comum ("Em todo o Gestor"). */
  appLabel?: string;
}>(), { appLabel: "" });

const { open, groups, description } = useOperatorShortcuts();

const allGroups = computed(() => mergeShortcutGroups(
  suiteShortcutGroup(props.sections, { appLabel: props.appLabel }),
  groups.value,
));
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-[80] bg-black/40" />
      <DialogContent
        class="fixed top-1/2 left-1/2 z-[80] flex max-h-[85dvh] w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-border bg-card text-card-foreground shadow-lg sm:max-w-md"
        data-operator-shortcuts-help
      >
        <div class="flex items-start gap-2 border-b border-border py-3 pr-2 pl-5">
          <div class="min-w-0 flex-1">
            <DialogTitle class="op-title">Atalhos do teclado</DialogTitle>
            <DialogDescription class="mt-0.5 op-micro text-muted-foreground">
              {{ description || "Toque e teclado fazem as mesmas coisas. Os atalhos pausam enquanto você digita ou com um diálogo aberto." }}
            </DialogDescription>
          </div>
          <DialogClose
            class="grid size-10 shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
            aria-label="Fechar os atalhos"
          >
            <Icon name="lucide:x" class="size-5" aria-hidden="true" />
          </DialogClose>
        </div>
        <div class="grid min-h-0 gap-4 overflow-y-auto px-5 py-4">
          <section v-for="group in allGroups" :key="group.title" class="grid gap-1.5" data-shortcut-group>
            <p class="op-micro font-semibold tracking-wide text-muted-foreground uppercase">{{ group.title }}</p>
            <ul class="grid gap-1">
              <li
                v-for="item in group.items"
                :key="`${item.keys.join('+')}-${item.label}`"
                class="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 op-body odd:bg-muted/40"
              >
                <span class="min-w-0">{{ item.label }}</span>
                <span class="flex shrink-0 items-center gap-1">
                  <OperatorKbd v-for="key in item.keys" :key="key">{{ key }}</OperatorKbd>
                </span>
              </li>
            </ul>
          </section>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
