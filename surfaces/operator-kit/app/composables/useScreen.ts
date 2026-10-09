// A régua de tela da suíte no script, segura para o SSR.
//
// O servidor não sabe a largura. Uma tela que decidia `v-if` com `useMediaQuery` cru
// desenhava a mesa no servidor e, no celular, o cliente montava OUTRA árvore durante a
// hidratação: no Gestor (09/10/2026) a Fila ficava no esqueleto para sempre
// (`Cannot read properties of null (reading 'emitsOptions')`) e a toolbar do Histórico,
// dos Clientes e do Catálogo sumia, só na carga direta (recarregar, PWA, link).
//
// O contrato: até a hidratação terminar, toda leitura daqui responde "mesa" (falso),
// no servidor e no cliente; a árvore hidratada é a mesma que o servidor mandou. Depois,
// a largura real entra como reatividade comum (a troca que a navegação interna já fazia).
// Montada depois da hidratação (navegação interna), a tela lê a largura real de saída,
// sem piscar. O que é só apresentação continua no CSS (`max-sm:hidden`, `md:inline-flex`):
// o servidor já desenha certo e nada troca.
import { computed, readonly, ref, type ComputedRef, type Ref } from "vue";
import { useMediaQuery } from "@vueuse/core";

import { belowQuery, type ScreenBreakpoint } from "../presentation/screen";

type NuxtAppWithScreen = NonNullable<ReturnType<typeof tryUseNuxtApp>> & { _operatorScreenReady?: Ref<boolean> };

/** A hidratação terminou (no servidor, nunca). Um por app, no `nuxtApp`. */
export function useScreenReady(): Readonly<Ref<boolean>> {
  // Fora de um app Nuxt (teste de componente montado sem Nuxt) não há SSR nem
  // hidratação: a largura real vale desde o início.
  const nuxtApp = (typeof tryUseNuxtApp === "function" ? tryUseNuxtApp() : null) as NuxtAppWithScreen | null;
  if (!nuxtApp) return readonly(ref(true));
  if (!nuxtApp._operatorScreenReady) {
    const serverRendered = Boolean(nuxtApp.payload?.serverRendered);
    const ready = ref(import.meta.client && (!nuxtApp.isHydrating || !serverRendered));
    if (import.meta.client && !ready.value) {
      nuxtApp.hooks.hookOnce("app:suspense:resolve", () => {
        ready.value = true;
      });
    }
    nuxtApp._operatorScreenReady = ready;
  }
  return readonly(nuxtApp._operatorScreenReady);
}

export interface OperatorScreen {
  /** A hidratação terminou: daqui em diante as leituras são a largura real. */
  ready: Readonly<Ref<boolean>>;
  /** Abaixo de `sm` (640 px): o celular da barra do topo e da toolbar do kit. */
  belowSm: ComputedRef<boolean>;
  /** Abaixo de `md` (768 px): celular e celular deitado (colunas em abas). */
  belowMd: ComputedRef<boolean>;
  /** Abaixo de `lg` (1024 px): até o tablet em pé. */
  belowLg: ComputedRef<boolean>;
  /** Abaixo de `xl` (1280 px). */
  belowXl: ComputedRef<boolean>;
}

/**
 * A régua de tela da suíte: `belowSm`, `belowMd`, `belowLg`, `belowXl`, as mesmas
 * bordas do `max-sm:`/`max-md:`/`max-lg:`/`max-xl:` do CSS. Falso (mesa) até a
 * hidratação terminar. Única fonte de largura para decidir árvore (`v-if`, slot,
 * prop) nos apps de operador; `useMediaQuery` de largura fora daqui reprova
 * (`tests/guardrails.screen.test.ts`).
 */
export function useScreen(): OperatorScreen {
  const ready = useScreenReady();
  const below = (bp: ScreenBreakpoint) => {
    const media = useMediaQuery(belowQuery(bp));
    return computed(() => ready.value && media.value);
  };
  return {
    ready,
    belowSm: below("sm"),
    belowMd: below("md"),
    belowLg: below("lg"),
    belowXl: below("xl"),
  };
}
