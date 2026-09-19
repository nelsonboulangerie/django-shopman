<script setup lang="ts">
// Tem mais abaixo — a dica de que ainda há conteúdo, e onde ela flutua.
//
// Some sozinha quando o fim do conteúdo aparece. Vive acima do que flutua na
// base (card de ação, barra), lendo o mesmo `data-focus-obstruction` que o
// próximo foco usa para saber o que está mesmo à vista.
//
// O CHEVRON LEVA ATÉ O FIM. Era decorativa e sem captura de clique; virou
// botão por decisão do Pablo, porque a dica já parecia tocável e não era —
// quem tentava não recebia nada, que é pior do que não convidar. O alvo
// interativo é SÓ o chevron (`pointer-events-auto` nele; o degradê continua
// inerte, senão ele engoliria o toque na faixa inteira da tela).
//
// O QUE A IMPEDE DE SE LER COMO BOTÃO GORDO É A TRANSLUCIDEZ, NÃO O TAMANHO.
// Fundo sólido com sombra vira chip clicável em qualquer medida; com o fundo a
// 33% e sem sombra, o que sobra é o CHEVRON, e o círculo só o separa do
// conteúdo. Por isso ela pôde crescer: 28 (a versão antiga, inline no
// bottom-sheet) passava despercebida, e o tamanho deixou de ser o que a define.
// Está em 48 por decisão do Pablo — é o alvo de toque, e mesmo assim não se lê
// como controle pesado. O anel fica bem fraco para garantir a borda sobre fundo
// escuro (KDS). Comparado em 375x667.
//
// ⚠️ Sobre o DEGRADÊ a translucidez rende pouco, porque ele já lava o fundo
// para a cor da página — fundo translúcido sobre a mesma cor parece opaco. Ela
// trabalha nas bordas e onde o conteúdo atrás tem contraste, que é o caso das
// telas de operador. Está em 33% por decisão do Pablo.
//
// ⚠️ O DEGRADÊ ENCOSTA NO OBSTÁCULO. A folga de 12px é do chevron e mora no
// recuo interno (`pb-3`), não no posicionamento: enquanto ela empurrava a dica
// inteira para cima, sobrava uma faixa de conteúdo cru entre a lavagem e o card
// suspenso — visível e feia no checkout da loja. A pílula fica exatamente onde
// estava; só o degradê desceu.
import { HINT_GAP, hintMotionClass, hintScrollBehavior } from '../presentation/moreBelow'

const { sentinel, visible, offset, scrollToEnd } = useMoreBelow()

// Menos movimento: a dica fica PARADA, não some. A informação é a mesma.
const reducedMotion = ref(false)
onMounted(() => {
  if (typeof window.matchMedia !== 'function') return
  const consulta = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = consulta.matches
  useEventListener(consulta, 'change', event => { reducedMotion.value = (event as MediaQueryListEvent).matches })
})
const motionClass = computed(() => hintMotionClass(reducedMotion.value))

function irAteOFim() {
  scrollToEnd(hintScrollBehavior(reducedMotion.value))
}
</script>

<template>
  <!-- O sentinela nasce AQUI, no fim do conteúdo: é a posição dele que responde
       "já cheguei ao fim?", e é para ele que o toque na dica leva. A margem de
       rolagem pela borda de baixo é o que faz o fim parar ACIMA do que flutua,
       em vez de atrás dele — o mesmo truque do `scroll-margin-top` do próximo
       foco, do outro lado da tela. A dica é teleportada para fora, para não
       herdar recorte nem contexto de empilhamento de quem a chamou. -->
  <span
    ref="sentinel"
    aria-hidden="true"
    class="block h-px w-full"
    :style="{ scrollMarginBottom: `${offset}px` }"
    data-more-below-sentinel
  />
  <ClientOnly>
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-300"
        leave-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <div v-if="visible" class="pointer-events-none fixed inset-x-0 z-30" :style="{ bottom: `${offset}px` }" data-more-below>
          <!-- O degradê é metade da dica: sem ele a pílula boia sobre um texto
               qualquer e vira artefato. Com ele, o conteúdo DISSOLVE para baixo,
               que é a própria mensagem. Mesmo par do bottom-sheet da loja.
               Mais alto que a pílula de propósito: ela precisa ficar DENTRO da
               lavagem, e a lavagem precisa chegar colada no card. -->
          <div class="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-background to-transparent" aria-hidden="true" />
          <div class="relative flex justify-center" :style="{ paddingBottom: `${HINT_GAP}px` }">
            <button
              type="button"
              class="pointer-events-auto flex size-12 items-center justify-center rounded-full bg-background/33 text-foreground ring-1 ring-border/40 backdrop-blur-sm transition hover:bg-background/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95"
              :class="motionClass"
              aria-label="Ir para o fim do conteúdo"
              data-more-below-jump
              @click="irAteOFim"
            >
              <Icon name="lucide:chevron-down" class="size-6" />
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>
  </ClientOnly>
</template>
