<script setup lang="ts">
// Tem mais abaixo — a dica de que ainda há conteúdo, e onde ela flutua.
//
// Some sozinha quando o fim do conteúdo aparece. Vive acima do que flutua na
// base (card de ação, barra), lendo o mesmo `data-focus-obstruction` que o
// próximo foco usa para saber o que está mesmo à vista.
//
// Decorativa: `aria-hidden` e sem captura de clique. Quem usa leitor de tela
// já sabe que a lista continua — a dica existe para o olho que não rolou.
//
// O QUE A IMPEDE DE SE LER COMO BOTÃO É A TRANSLUCIDEZ, NÃO O TAMANHO. Fundo
// sólido com sombra vira chip clicável em qualquer medida; com o fundo a 33% e
// sem sombra, o que sobra é o CHEVRON, e o círculo só o separa do conteúdo.
// Por isso ela pôde crescer: 28 (a versão antiga, inline no bottom-sheet)
// passava despercebida, e o tamanho deixou de ser o que a define. Está em 48
// por decisão do Pablo — encosta no alvo de toque, e mesmo assim não se lê como
// controle, porque não tem fundo sólido nem sombra. O anel fica bem fraco para
// garantir a borda sobre fundo escuro (KDS). Comparado em 375x667.
//
// ⚠️ Sobre o DEGRADÊ a translucidez rende pouco, porque ele já lava o fundo
// para a cor da página — fundo translúcido sobre a mesma cor parece opaco. Ela
// trabalha nas bordas e onde o conteúdo atrás tem contraste, que é o caso das
// telas de operador. Está em 33% por decisão do Pablo.
import { hintMotionClass } from '../presentation/moreBelow'

const { sentinel, visible, offset } = useMoreBelow()

// Menos movimento: a dica fica PARADA, não some. A informação é a mesma.
const reducedMotion = ref(false)
onMounted(() => {
  if (typeof window.matchMedia !== 'function') return
  const consulta = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = consulta.matches
  useEventListener(consulta, 'change', event => { reducedMotion.value = (event as MediaQueryListEvent).matches })
})
const motionClass = computed(() => hintMotionClass(reducedMotion.value))
</script>

<template>
  <!-- O sentinela nasce AQUI, no fim do conteúdo: é a posição dele que responde
       "já cheguei ao fim?". A dica é teleportada para fora, para não herdar
       recorte nem contexto de empilhamento de quem a chamou. -->
  <span ref="sentinel" aria-hidden="true" class="block h-px w-full" data-more-below-sentinel />
  <ClientOnly>
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-300"
        leave-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <div v-if="visible" class="pointer-events-none fixed inset-x-0 z-30" :style="{ bottom: `${offset}px` }" aria-hidden="true" data-more-below>
          <!-- O degradê é metade da dica: sem ele a pílula boia sobre um texto
               qualquer e vira artefato. Com ele, o conteúdo DISSOLVE para baixo,
               que é a própria mensagem. Mesmo par do bottom-sheet da loja. -->
          <div class="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-background to-transparent" />
          <div class="relative flex justify-center">
            <span
              class="flex size-12 items-center justify-center rounded-full bg-background/33 text-foreground ring-1 ring-border/40 backdrop-blur-sm"
              :class="motionClass"
            >
              <Icon name="lucide:chevron-down" class="size-6" />
            </span>
          </div>
        </div>
      </Transition>
    </Teleport>
  </ClientOnly>
</template>
