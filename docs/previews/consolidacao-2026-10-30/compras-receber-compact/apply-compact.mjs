// PRÉVIA C (compacto) do Compras: SÓ o Receber (`/receive`) ganha a linha compacta no
// celular. Painel, Comprar e Base seguem o cabeçalho PADRÃO (gerencial), intactos.
// Roda numa CÓPIA temporária (git archive); nunca escreve na árvore do produto.
// Âncoras de string: se o Receber mudar, o aplicador FALHA alto em vez de adivinhar.
import {readFile,writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe surfaces/purchase-nuxt da cópia temporária.');
// As duas peças compartilhadas do compacto (selo com chip e a linha única).
execFileSync(process.execPath,[new URL('../compact-kit/apply-kit.mjs',import.meta.url).pathname,join(root,'../operator-kit')],{stdio:'inherit'});
const file=join(root,'app/pages/receive.vue');let s=await readFile(file,'utf8');
function swap(from,to){const n=s.split(from).length-1;if(n!==1)throw Error(`Encaixe ${n===0?'ausente':'repetido ('+n+')'}: `+from.slice(0,70));s=s.replace(from,to);}

// 1. Estado do compacto. Compras não tem SSE: a leitura é ao abrir e em Atualizar. O
//    chip do selo usa o tom neutro (↻), nunca o verde "ao vivo"; sem leitura = ×.
//    A gaveta (seções, operador, Atalhos) perde o ☰ no celular e o Compras NÃO tem "Mais"
//    na barra inferior (4 seções, todas rápidas): ela vai para o fim das Opções.
swap('\n</script>\n\n<template>',`
// ── PRÉVIA C: o Receber compacto no celular ─────────────────────────────────
const { pending: compactPending } = usePurchaseDesk();
const compactReadAt = useState("purchase-read-at", () => "");
const compactTone = computed(() => (readonlyFallback.value ? "off" : "calm"));
const compactConnLabel = computed(() => (compactPending.value ? "Lendo a base de compras" : "Leitura ao abrir e em Atualizar"));
const compactAvisos = computed(() => (route.query.avisos === "options" ? "options" : "own"));
const compactSummary = computed(() => \`\${visibleReceiptRows.value.length} de \${plural(receiptRows.value.length, "item", "itens")} da entrada.\`);
function openSuiteDrawer() {
  // O menu fecha e devolve o foco ao ⋮; abrir a gaveta no mesmo tique a fecharia.
  setTimeout(() => document.querySelector<HTMLElement>("[data-compact-drawer-toggle]")?.click(), 180);
}
const compactOptions = computed(() => [
  headerActions.value,
  [{ label: "Menu completo", description: "Seções, operador e atalhos", icon: "i-lucide-menu", onSelect: openSuiteDrawer }],
]);
</script>

<template>`);

// 2. A linha compacta antes do cabeçalho padrão (que some abaixo de md, pelo CSS).
//    Começo: selo | Busca (a da suíte, como em A) | Opções | Avisos.
//    Conferência: ‹ | fornecedor + NF + volumes (#identity) | Busca | Opções | Avisos.
swap(`  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Receber"`,`  <main class="flex min-h-0 flex-1 flex-col" data-compact-page>
    <OperatorCompactBar
      title="Receber"
      :tone="compactTone"
      :time="compactReadAt"
      :conn-label="compactConnLabel"
      :query="receiveStart ? '' : receiveQuery"
      :search-label="receiveStart ? 'Buscar no Compras e na suíte' : 'Buscar item da entrada'"
      :summary="compactSummary"
      :options="compactOptions"
      :avisos="compactAvisos"
      to="https://sim-washing-refers-roberts.trycloudflare.com/"
      @clear="receiveQuery = ''"
    >
      <template v-if="conferenceOpen" #lead>
        <NuxtButton
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          class="size-11 shrink-0 justify-center"
          aria-label="Voltar ao começo do Receber"
          data-receipt-back
          @click="receiptParked = true"
        />
      </template>
      <template v-if="conferenceOpen" #identity>
        <p class="line-clamp-2 break-words text-sm font-semibold leading-tight" data-compact-identity-name>{{ phoneTitle }}</p>
        <p class="text-xs leading-tight text-muted tabular-nums" data-compact-identity-doc>
          {{ documentLine }}<template v-if="volumesBadge"> · <span class="text-success">{{ volumesBadge }}</span></template>
        </p>
      </template>
    </OperatorCompactBar>
    <NuxtDashboardSidebarToggle class="hidden" tabindex="-1" aria-hidden="true" data-compact-drawer-toggle />
    <OperatorPageHeader title="Receber"`);

// 3. O ‹ do cabeçalho padrão sai no celular junto com ele; na mesa ele já era md:hidden.
await writeFile(file,s+`
<style>
/* PRÉVIA C: abaixo de md a linha compacta é o cabeçalho inteiro do Receber. */
@media (max-width: 767.98px) {
  [data-compact-page] > [data-operator-page-header-landmark] { display: none !important; }
}
</style>
`);
console.log('apply-compact: Receber compacto aplicado em',file);
