<script setup lang="ts">
// Prévia 5 (DEV-2026-030): a corrida do entregador da casa de ponta a ponta, em hiperfoco,
// depois da revisão adversarial de 16/11. Cada momento tem uma tela; a tela muda sozinha
// quando o momento muda. Dados fictícios.
import type { FocusMoment } from "~/components/MsFocusScreen.vue";

interface Step {
  n: string;
  moment: FocusMoment;
  title: string;
  landscape?: boolean;
  when: string;
  tap: string;
  gestor: string;
  cliente: string;
}

const happy: Step[] = [
  {
    n: "i", moment: "home", title: "Tela inicial (sem corrida)",
    when: "Quando não há corrida. É o único lugar de configuração: tema e \"Adicionar à tela inicial\". Dentro da corrida, nada disso aparece.",
    tap: "Nenhum.",
    gestor: "Diego na escala, livre.",
    cliente: "Nada.",
  },
  {
    n: "0", moment: "call", title: "A chamada chega",
    when: "O balcão envia a corrida. Com vários pedidos o aviso diz \"Rota A\"; com um só, o código do pedido (\"Pedido B12\"). A primeira de um entregador novo vai pelo link no WhatsApp.",
    tap: "Nenhum: tocar no aviso só abre.",
    gestor: "Corrida A · Diego avisado às 12h31.",
    cliente: "Nada muda.",
  },
  {
    n: "1", moment: "pickup", title: "No balcão: pegar e sair",
    when: "Celular a menos de 60 m da loja. Um bloco por pedido, o código sempre à esquerda e no mesmo peso; dentro dele, as sacolas e o que vai junto (troco ou maquininha).",
    tap: "Saí da loja.",
    gestor: "Diego chegou à loja. Ao tocar Saí: A47 e C03 saem para entrega.",
    cliente: "\"Diego está a caminho. Deve chegar por volta de 12h46.\"",
  },
  {
    n: "2", moment: "drive", landscape: true, title: "Dirigindo: o endereço",
    when: "Depois de Saí e depois de cada entrega. Em movimento, nada para ler nem tocar. \"Abrir no Waze\" fica à mão, mas a nossa página é o mapa (é ela que manda a posição).",
    tap: "Nenhum.",
    gestor: "Diego na rua · 2 entregas a fazer · posição no mapa.",
    cliente: "Aos 80 m: \"Diego está chegando.\"",
  },
  {
    n: "3", moment: "door", title: "Na entrega: quem, o quê, quanto",
    when: "A tela da entrega é a da entrega aberta mais perto, parado há 15 s (ele pode mudar a ordem). Fica na tela até ele tocar, ou até se afastar 200 m por 30 s.",
    tap: "Entreguei A47.",
    gestor: "A47 entregue às 12h47.",
    cliente: "\"Entregue às 12h47.\" (sai depois do Desfazer)",
  },
  {
    n: "4", moment: "door-card", title: "Na entrega seguinte (cartão)",
    when: "Igual à 3. Já pago mostra \"Já pago. Só entregar.\"; com a instrução de deixar na portaria, o botão vira \"Deixei na portaria\" (nunca em pedido a cobrar).",
    tap: "Entreguei C03.",
    gestor: "C03 entregue às 12h55.",
    cliente: "O mesmo da 3, para o Paulo.",
  },
  {
    n: "5", moment: "back", title: "Voltando: só o acerto",
    when: "Depois da última parada. O valor já desconta o troco que ele devolveu e muda sozinho se alguém pagou de outro jeito.",
    tap: "Nenhum.",
    gestor: "Diego volta com R$ 100,00 em dinheiro e a maquininha Azul.",
    cliente: "Nada.",
  },
  {
    n: "6", moment: "closed", title: "Fechada",
    when: "Quem fecha é o balcão, ao conferir no Gestor. Em seguida a página volta à tela inicial.",
    tap: "Nenhum.",
    gestor: "Corrida A fechada. A pagar a Diego hoje: R$ 27,00.",
    cliente: "Nada.",
  },
];

const detours: Step[] = [
  {
    n: "1b", moment: "pickup-wait", title: "Um pedido ainda não ficou pronto",
    when: "Algum pedido da corrida não está pronto. A hora vem da cozinha e, se mudar, chega como aviso: \"Agora fica pronta às 12h48.\"",
    tap: "Nenhum: o botão aparece quando C03 fica pronta.",
    gestor: "Diego espera C03.",
    cliente: "Nada.",
  },
  {
    n: "3+", moment: "undo", title: "Logo depois de Entreguei",
    when: "10 s para desfazer um toque sem querer (bolso, chuva, luva). O aviso ao cliente só sai depois.",
    tap: "Desfazer, se precisar.",
    gestor: "Nada até os 10 s.",
    cliente: "Nada até os 10 s.",
  },
  {
    n: "3c", moment: "which-door", title: "Duas entregas perto",
    when: "Duas paradas abertas a menos de 150 m (mesmo prédio, GPS entre torres). Pergunta uma vez, em vez de adivinhar.",
    tap: "A entrega (1 toque, só nesse caso).",
    gestor: "Nada.",
    cliente: "Nada.",
  },
  {
    n: "3b", moment: "problem", title: "Problema",
    when: "Só quando ele toca \"Problema\" na entrega. Abre uma folha com os casos; nada é automático.",
    tap: "O caso (1 toque).",
    gestor: "Aviso com o caso e \"Ligar para Marina\".",
    cliente: "A loja liga; nada automático.",
  },
  {
    n: "3d", moment: "other-pay", title: "Pagou de outro jeito",
    when: "Escolhido na folha de Problema. O acerto da volta se refaz sozinho. Pix só pela maquininha: ele não tem como conferir outro Pix.",
    tap: "Como pagou (1 toque).",
    gestor: "A47 pago no cartão. O acerto de Diego passa a R$ 42,00.",
    cliente: "Nada.",
  },
  {
    n: "3b'", moment: "failed-wait", title: "A espera curta",
    when: "Com \"Ninguém atendeu\", 3 minutos enquanto a loja liga. Sem resposta, a tela leva para C03 e a sacola volta com ele.",
    tap: "Nenhum, ou \"Marina atendeu\".",
    gestor: "Ligando para Marina.",
    cliente: "A ligação da loja.",
  },
  {
    n: "7", moment: "cancelled", title: "A loja cancelou com ele na rua",
    when: "Passa na frente de qualquer tela. A volta passa a incluir a sacola de C03.",
    tap: "Entendi (para ter certeza de que ele viu).",
    gestor: "C03 cancelado; Diego avisado e confirmou às 12h44.",
    cliente: "O aviso de cancelamento da loja.",
  },
];

const palette = [
  { name: "Tela", light: "#ffffff", lightFg: "#000000", dark: "#000000", darkFg: "#ffffff" },
  { name: "Bloco, escolha e botão secundário", light: "#f5f5f5", lightFg: "#000000", dark: "#262626", darkFg: "#ffffff" },
  { name: "Badge do código", light: "#d4d4d4", lightFg: "#000000", dark: "#525252", darkFg: "#ffffff" },
  { name: "Forte (botão principal, aviso)", light: "#000000", lightFg: "#ffffff", dark: "#ffffff", darkFg: "#000000" },
];

const typeScale = [
  { name: "Grande", spec: "28 · 800", sample: "R$ 58,00", cls: "text-[28px] font-extrabold leading-tight text-highlighted" },
  { name: "Normal", spec: "18 · 500", sample: "2 sacolas", cls: "text-[18px] font-medium leading-snug text-highlighted" },
  { name: "Pequeno", spec: "15 · 500", sample: "Faltam 2 · chega 12h46", cls: "text-[15px] font-medium leading-snug text-muted" },
];

const dark = ref(false);

const sections = [
  { title: "O caminho feliz: 3 toques numa corrida de duas entregas", steps: happy },
  { title: "Quando sai do roteiro: um toque a mais só na exceção", steps: detours },
];

const fixes = [
  "Toque sem querer em Entreguei: 10 s para desfazer, e o cliente só é avisado depois.",
  "Mesmo prédio ou GPS entre torres: o botão leva o código (\"Entreguei A47\") e, com duas entregas perto, a tela pergunta \"Qual entrega é esta?\".",
  "Pagou de outro jeito: cartão ou Pix na maquininha, e o acerto da volta se refaz sozinho.",
  "Rodapé da entrega: um botão principal e dois iguais, \"Ligar\" e \"Problema\"; os casos moram na folha de Problema.",
  "Pedido cancelado com ele na rua: tela que passa na frente de todas, com \"Entendi\".",
  "\"Diego chegou.\" saía no semáforo: virou \"Diego está chegando.\", e o \"chegou\" saiu.",
  "A tela trocava enquanto ele lia: a tela da entrega só sai com o toque dele ou com 200 m de distância por 30 s.",
  "Não consegui mandava seguir cedo: 3 minutos de espera enquanto a loja liga, e o motivo \"Pedido com problema\".",
  "Portaria e condomínio: torre e a instrução do cliente sem edição; \"Deixei na portaria\" só em pedido já pago.",
  "Pedido que atrasa: cada linha diz se está pronta, e o botão só aparece com tudo pronto.",
  "Troco somado: o troco e a maquininha vão dentro do bloco do pedido que precisa deles.",
  "Ordem trocada: vale a entrega aberta mais perto; \"Falta 1\" no lugar de \"1 de 2\".",
  "Link encaminhado: preso ao primeiro celular que abre; os outros veem \"Esta corrida está aberta em outro celular.\"",
  "Esqueceu de tocar Saí: fora da loja por 1 minuto, aviso a ele e ao Gestor; nunca automático.",
  "Balcão não fechou: a corrida seguinte começa com \"Antes: entregue R$ 100,00 da corrida A no caixa.\"",
  "Maquininha com bolinha azul confundia com a rota A: agora vai só pelo nome, \"Maquininha Azul\".",
  "Fonte grande ou tela de 360 px: o botão principal fica preso no rodapé, e o resto rola.",
  "Tema: o entregador escolhe na tela inicial e o sistema lembra; sem escolha, segue o celular. Nada de configuração dentro da corrida.",
  "Ruído: saíram o \"combinado até\" da entrega, o \"Você recebe\" repetido na loja, o mapa da volta e a nota \"os endereços somem\".",
  "Gênero: \"Marina paga com\" no lugar de \"Ela paga com\"; o nome não diz o gênero.",
];
</script>

<template>
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default pb-32" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-8 px-8 py-8">
          <header class="flex flex-col gap-1">
            <MsPreviewNav :current="5" />
            <div class="flex items-center gap-2 op-body text-toned">
              <span>Tema das telas:</span>
              <NuxtButton size="sm" color="neutral" :variant="!dark ? 'solid' : 'outline'" icon="i-lucide-sun" label="Claro" @click="dark = false" />
              <NuxtButton size="sm" color="neutral" :variant="dark ? 'solid' : 'outline'" icon="i-lucide-moon" label="Escuro" @click="dark = true" />
              <span class="op-micro text-muted">A paleta das telas é própria: branco, preto, dois cinzas claros. No aviso de cancelamento (7), o tom forte é o oposto do tema.</span>
            </div>
            <h1 class="op-title font-semibold text-highlighted">Prévia 5 · A corrida do entregador da casa, em hiperfoco (linguagem do Painel)</h1>
            <p class="op-body text-toned">
              Uma tela por momento, e a tela muda sozinha quando o momento muda: no balcão, dirigindo (carro ou moto), na entrega. Em cada uma, só o
              que importa ali. O caminho feliz custa <strong class="text-highlighted">3 toques</strong>; cada exceção custa no máximo um a mais, e só
              quando acontece.
            </p>
            <p class="op-micro text-muted">
              Cores: a cor da corrida (azul, a da corrida A) é só identidade, na letra e na rota. Botão principal é preto e único; escolha entre
              iguais é contorno. Nada verde: verde seria o resultado, não o gesto.
            </p>
          </header>

          <section class="flex flex-col gap-4">
            <h2 class="op-title text-highlighted">A linguagem, com rigor: só estas peças</h2>
            <div class="flex flex-wrap items-start gap-8">
              <div class="flex w-[420px] flex-col gap-3 rounded-2xl bg-default p-5 ring-1 ring-default">
                <p class="op-micro font-semibold text-muted">Texto: 3 tamanhos, e só eles</p>
                <p v-for="t in typeScale" :key="t.name" class="flex items-baseline justify-between gap-4">
                  <span :class="t.cls">{{ t.sample }}</span>
                  <span class="op-micro shrink-0 text-muted">{{ t.name }} · {{ t.spec }}</span>
                </p>
                <p class="flex items-baseline justify-between gap-4">
                  <span class="inline-flex w-fit items-center rounded-lg bg-[#d4d4d4] px-2 py-0.5 text-[15px] font-bold tabular-nums text-black">A47</span>
                  <span class="op-micro shrink-0 text-muted">Código do pedido · sempre este badge, na linha de cima</span>
                </p>
              </div>
              <div class="flex w-[420px] flex-col gap-3 rounded-2xl bg-default p-5 ring-1 ring-default">
                <p class="op-micro font-semibold text-muted">Paleta: branco, preto e dois cinzas claros (#f5f5f5 e #d4d4d4; no escuro, #262626 e #525252)</p>
                <div v-for="row in palette" :key="row.name" class="flex items-center gap-3">
                  <span class="flex overflow-hidden rounded-lg ring-1 ring-black/20">
                    <span class="grid size-10 place-items-center text-[11px] font-bold" :style="{ background: row.light, color: row.lightFg }">Aa</span>
                    <span class="grid size-10 place-items-center text-[11px] font-bold" :style="{ background: row.dark, color: row.darkFg }">Aa</span>
                  </span>
                  <span class="op-body text-toned">{{ row.name }}</span>
                </div>
              </div>
              <div class="flex w-[420px] flex-col gap-2 rounded-2xl bg-default p-5 ring-1 ring-default op-body text-toned">
                <p class="op-micro font-semibold text-muted">Regras</p>
                <p>· O código do pedido é sempre o mesmo badge, na linha de cima, à esquerda. O que pertence a um pedido mora dentro do bloco dele.</p>
                <p>· Tudo alinhado à esquerda; centralizado só o texto dentro de botão.</p>
                <p>· Grande só para o título da tela e para o dinheiro.</p>
                <p>· Espaço: 20 px na borda, 16 px dentro do bloco, 12 px entre blocos, 28 px entre grupos.</p>
                <p>· Tema claro ou escuro: o entregador escolhe na tela inicial e o sistema lembra, no celular e no cadastro dele. Sem escolha, segue o celular.</p>
                <p>· Medido em toda tela, nos dois temas: só 3 tamanhos, só as 4 cores, badge sempre na linha de cima, nada centralizado fora de botão. Contraste de texto: 14,2:1 no claro e 7,8:1 no escuro (AAA). Bloco contra a tela 1,09:1 e badge contra o bloco 1,36:1: leve, como os tons do Painel.</p>
                <p>· A cor da rota só no quadrado da letra e na linha do mapa.</p>
              </div>
            </div>
          </section>

          <section v-for="sec in sections" :key="sec.title" class="flex flex-col gap-4">
            <h2 class="op-title text-highlighted">{{ sec.title }}</h2>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-x-8 gap-y-10">
              <article v-for="s in sec.steps" :key="s.n" class="flex flex-col gap-3" :class="s.landscape ? 'col-span-2' : ''">
                <div class="flex items-baseline gap-2">
                  <span class="grid h-8 min-w-8 shrink-0 place-items-center rounded-lg bg-inverted px-1.5 text-sm font-bold text-inverted">{{ s.n }}</span>
                  <h3 class="op-title text-highlighted">{{ s.title }}</h3>
                </div>
                <div
                  class="overflow-hidden rounded-[2.2rem] border-[10px] border-black/85 shadow-xl"
                  :class="s.landscape ? 'h-[360px] w-[740px]' : 'h-[700px] w-[340px]'"
                >
                  <MsFocusScreen :moment="s.moment" :landscape="s.landscape" :dark="dark" />
                </div>
                <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 op-micro" :class="s.landscape ? 'max-w-[740px]' : 'max-w-[340px]'">
                  <dt class="font-semibold text-highlighted">Quando</dt><dd class="text-toned">{{ s.when }}</dd>
                  <dt class="font-semibold text-highlighted">Toque</dt><dd class="text-toned">{{ s.tap }}</dd>
                  <dt class="font-semibold text-highlighted">Gestor</dt><dd class="text-toned">{{ s.gestor }}</dd>
                  <dt class="font-semibold text-highlighted">Cliente</dt><dd class="text-toned">{{ s.cliente }}</dd>
                </dl>
              </article>
            </div>
          </section>

          <section class="flex flex-col gap-1 rounded-xl border border-dashed border-accented p-4 op-body text-toned">
            <p class="font-semibold text-highlighted">O que a revisão adversarial mudou (19 achados)</p>
            <p v-for="f in fixes" :key="f">· {{ f }}</p>
          </section>
        </main>
      </div>
    </Teleport>
  </div>
</template>
