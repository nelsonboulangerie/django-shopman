<script setup lang="ts">
// Documento legal — a moldura comum de /privacy e /terms.
//
// POR QUE NÃO É ACORDEÃO, COMO NA FAQ. Na FAQ cada resposta é independente e o
// leitor procura UMA. Texto legal é o contrário: é lido (ou deveria poder ser
// lido) de ponta a ponta, é o documento que o cliente declara aceitar ao entrar,
// e quem chega por link quer cair na cláusula certa já aberta. Acordeão fechado
// piora as três coisas: esconde texto do Ctrl+F em parte dos navegadores, faz o
// "li e aceito" depender de cliques, e transforma o link `#cancellation` num
// cabeçalho mudo. Aqui tudo fica aberto; o que resolve o comprimento é o ÍNDICE.
//
// O que a moldura dá, e a página não precisa repetir:
//   - título, data de vigência (slot `#meta`), resumo (slot `#summary`) e breadcrumb;
//   - índice clicável: coluna sticky no desktop, bloco recolhível no celular;
//   - seções numeradas (contador de CSS: o número não é texto do documento);
//   - medida de leitura ~65ch e a tipografia do corpo (`.shop-legal*` no tailwind.css);
//   - âncoras compartilháveis: o salto usa o PRÓXIMO FOCO (`useNextFocus`), que
//     respeita o cabeçalho sticky e o viewport interno do PWA instalado, e grava
//     `#id` na URL;
//   - "Voltar ao topo" no fim e a dica de "tem mais abaixo".
//
// O ÍNDICE SAI DAS PRÓPRIAS SEÇÕES. A página só escreve `<LegalSection id>` com o
// título no slot `#title`; o índice lê isso do slot na renderização (inclusive no
// servidor). Não há segunda lista de títulos para desencontrar da primeira.
import { Fragment, type VNode } from 'vue'
import LegalSection from '~/components/LegalSection.vue'
import { legalGoToKey, legalSectionNumberKey, sectionNumber } from '~/presentation/legal'

const props = defineProps<{ title: string }>()
const slots = useSlots()
const { reveal } = useNextFocus()

interface TocEntry {
  id: string
  title: () => VNode[]
}

function flatten (nodes: VNode[]): VNode[] {
  return nodes.flatMap(node => (node.type === Fragment && Array.isArray(node.children))
    ? flatten(node.children as VNode[])
    : [node])
}

/** Lido a cada renderização: o índice é o espelho das seções, nunca uma cópia. */
function tocEntries (): TocEntry[] {
  return flatten(slots.default?.() ?? [])
    .filter(node => node.type === LegalSection && typeof node.props?.id === 'string')
    .map(node => {
      const sectionSlots = (node.children || {}) as Record<string, (() => VNode[]) | undefined>
      return { id: node.props!.id as string, title: sectionSlots.title ?? (() => []) }
    })
}

/** Renderiza o título da seção (o mesmo slot) dentro do link do índice. */
const TocTitle = (p: { render: () => VNode[] }) => p.render()

const TOP = 'legal-top'
const mobileToc = useTemplateRef<HTMLDetailsElement>('mobileToc')

function goTo (id: string) {
  reveal(id)
  // A âncora vai para a URL sem virar navegação: é o link que se compartilha.
  // O `history.state` do router é preservado, senão o "voltar" se perde.
  if (id === TOP) history.replaceState(history.state, '', location.pathname + location.search)
  else history.replaceState(history.state, '', `#${id}`)
  if (mobileToc.value) mobileToc.value.open = false
}

// O resumo ("ver §4") pergunta o número pela âncora. A resposta sai da mesma
// leitura do slot que monta o índice — chamada durante a renderização do item.
provide(legalSectionNumberKey, anchor => sectionNumber(tocEntries().map(entry => entry.id), anchor))
provide(legalGoToKey, goTo)

// Quem chega por link (`/terms#cancellation`) cai na seção, abaixo do cabeçalho.
onMounted(() => {
  const id = decodeURIComponent(location.hash.slice(1))
  if (id && document.getElementById(id)?.hasAttribute('data-legal-section')) reveal(id)
})
</script>

<template>
  <main class="shop-section pt-0" data-legal-document>
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: props.title }]" />
      </div>
    </div>

    <div class="shop-container lg:grid lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-12">
      <aside class="hidden lg:block">
        <nav aria-label="Índice do documento" class="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto pb-6" data-legal-toc="desktop">
          <p class="shop-kicker px-2 pb-2">Nesta página</p>
          <ol class="shop-legal-toc space-y-1">
            <li v-for="entry in tocEntries()" :key="entry.id">
              <a :href="`#${entry.id}`" @click.prevent="goTo(entry.id)"><span><TocTitle :render="entry.title" /></span></a>
            </li>
          </ol>
        </nav>
      </aside>

      <article class="min-w-0 max-w-[65ch]">
        <header :id="TOP" :data-focus-target="TOP" class="scroll-mt-24 outline-none">
          <h1 class="shop-title">{{ props.title }}</h1>
          <div class="mt-2 flex items-center gap-2 shop-muted">
            <Icon name="lucide:calendar-check" class="size-4 shrink-0" aria-hidden="true" />
            <slot name="meta" />
          </div>
        </header>

        <slot name="summary" />

        <details ref="mobileToc" class="group mt-6 rounded-lg border bg-card lg:hidden" data-legal-toc="mobile">
          <summary class="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 font-semibold [&::-webkit-details-marker]:hidden">
            <span class="flex items-center gap-2">
              <Icon name="lucide:list" class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              Nesta página
            </span>
            <span class="flex items-center gap-2 text-sm font-normal text-muted-foreground">
              {{ tocEntries().length }} seções
              <Icon name="lucide:chevron-down" class="size-4 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
            </span>
          </summary>
          <nav aria-label="Índice do documento" class="border-t px-2 py-2">
            <ol class="shop-legal-toc space-y-1">
              <li v-for="entry in tocEntries()" :key="entry.id">
                <a :href="`#${entry.id}`" @click.prevent="goTo(entry.id)"><span><TocTitle :render="entry.title" /></span></a>
              </li>
            </ol>
          </nav>
        </details>

        <div class="shop-legal mt-8">
          <slot />
        </div>

        <div class="mt-8 border-t pt-4">
          <a
            :href="`#${TOP}`"
            class="inline-flex items-center gap-2 text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            data-legal-back-to-top
            @click.prevent="goTo(TOP)"
          >
            <Icon name="lucide:arrow-up" class="size-4 shrink-0" aria-hidden="true" />
            Voltar ao topo
          </a>
        </div>
        <MoreBelow />
      </article>
    </div>
  </main>
</template>
