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
    n: "0", moment: "call", title: "A chamada chega",
    when: "O balcão envia a corrida. A primeira de um entregador novo vai pelo link no WhatsApp; com a página instalada, chega como aviso.",
    tap: "Nenhum: tocar no aviso só abre.",
    gestor: "Corrida A · Diego avisado às 12h31.",
    cliente: "Nada muda.",
  },
  {
    n: "1", moment: "pickup", title: "Na loja: conferir e sair",
    when: "Celular a menos de 60 m da loja. Cada pedido diz se está pronto; um troco por linha, do pedido que precisa dele.",
    tap: "Saí da loja.",
    gestor: "Diego chegou à loja. Ao tocar Saí: A47 e C03 saem para entrega.",
    cliente: "\"Diego está a caminho. Deve chegar por volta de 12h46.\"",
  },
  {
    n: "2", moment: "drive", landscape: true, title: "Dirigindo: só o caminho",
    when: "Depois de Saí e depois de cada entrega. Em movimento, nada para ler nem tocar. \"Abrir no Waze\" fica à mão, mas a nossa página é o mapa (é ela que manda a posição).",
    tap: "Nenhum.",
    gestor: "Diego na rua · 2 entregas a fazer · posição no mapa.",
    cliente: "Aos 80 m: \"Diego está chegando.\"",
  },
  {
    n: "3", moment: "door", title: "Na porta: entregar certo",
    when: "A porta é a parada aberta mais perto, parado há 15 s (ele pode mudar a ordem). Fica na tela até ele tocar, ou até se afastar 200 m por 30 s.",
    tap: "Entreguei A47.",
    gestor: "A47 entregue às 12h47.",
    cliente: "\"Entregue às 12h47.\" (sai depois do Desfazer)",
  },
  {
    n: "4", moment: "door-card", title: "Na porta seguinte (cartão)",
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
    when: "Quem fecha é o balcão, ao conferir no Gestor. O convite para instalar aparece aqui, uma vez, nunca no meio da corrida.",
    tap: "Nenhum (instalar é opcional).",
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
    n: "3c", moment: "which-door", title: "Duas paradas perto",
    when: "Duas paradas abertas a menos de 150 m (mesmo prédio, GPS entre torres). Pergunta uma vez, em vez de adivinhar.",
    tap: "A porta (1 toque, só nesse caso).",
    gestor: "Nada.",
    cliente: "Nada.",
  },
  {
    n: "3d", moment: "other-pay", title: "Pagou de outro jeito",
    when: "Marina pagou no cartão ou no Pix em vez do dinheiro. O acerto da volta se refaz sozinho. Pix fora da maquininha não existe: ele não tem como conferir.",
    tap: "Como pagou (1 toque, só nesse caso).",
    gestor: "A47 pago no cartão. O acerto de Diego passa a R$ 42,00.",
    cliente: "Nada.",
  },
  {
    n: "3b", moment: "failed", title: "Não consegui",
    when: "Só quando ele toca. Nunca automático.",
    tap: "O motivo.",
    gestor: "Aviso com o motivo e \"Ligar para Marina\".",
    cliente: "A loja liga; nada automático.",
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

const sections = [
  { title: "O caminho feliz: 3 toques numa corrida de duas entregas", steps: happy },
  { title: "Quando sai do roteiro: um toque a mais só na exceção", steps: detours },
];

const fixes = [
  "Toque sem querer em Entreguei: 10 s para desfazer, e o cliente só é avisado depois.",
  "Mesmo prédio ou GPS entre torres: o botão leva o código (\"Entreguei A47\") e, com duas paradas perto, a tela pergunta a porta.",
  "Pagou de outro jeito: cartão ou Pix na maquininha, e o acerto da volta se refaz sozinho.",
  "Pedido cancelado com ele na rua: tela que passa na frente de todas, com \"Entendi\".",
  "\"Diego chegou.\" saía no semáforo: virou \"Diego está chegando.\", e o \"chegou\" saiu.",
  "A tela trocava enquanto ele lia: a porta só sai com o toque dele ou com 200 m de distância por 30 s.",
  "Não consegui mandava seguir cedo: 3 minutos de espera enquanto a loja liga, e o motivo \"Pedido com problema\".",
  "Portaria e condomínio: torre e a instrução do cliente sem edição; \"Deixei na portaria\" só em pedido já pago.",
  "Pedido que atrasa: cada linha diz se está pronta, e o botão só aparece com tudo pronto.",
  "Troco somado: um troco por linha, do pedido que precisa dele.",
  "Ordem trocada: a porta é a parada aberta mais perto; \"Falta 1\" no lugar de \"1 de 2\".",
  "Link encaminhado: preso ao primeiro celular que abre; os outros veem \"Esta corrida está aberta em outro celular.\"",
  "Esqueceu de tocar Saí: fora da loja por 1 minuto, aviso a ele e ao Gestor; nunca automático.",
  "Balcão não fechou: a corrida seguinte começa com \"Antes: entregue R$ 100,00 da corrida A no caixa.\"",
  "Maquininha com bolinha azul confundia com a corrida A: agora vai só pelo nome, \"Maquininha Azul\".",
  "Fonte grande ou tela de 360 px: o botão principal fica preso no rodapé, e o resto rola.",
  "Noite: tema escuro sozinho depois do pôr do sol, na direção e na porta.",
  "Ruído: saíram o \"combinado até\" da porta, o \"Você recebe\" repetido na loja, o mapa da volta e a nota \"os endereços somem\".",
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
            <h1 class="op-title font-semibold text-highlighted">Prévia 5 · A corrida do entregador da casa, em hiperfoco (revisada)</h1>
            <p class="op-body text-toned">
              Uma tela por momento, e a tela muda sozinha quando o momento muda: na loja, dirigindo (carro ou moto), na porta. Em cada uma, só o
              que importa ali. O caminho feliz custa <strong class="text-highlighted">3 toques</strong>; cada exceção custa no máximo um a mais, e só
              quando acontece.
            </p>
            <p class="op-micro text-muted">
              Cores: a cor da corrida (azul, a da corrida A) é só identidade, na letra e na rota. Botão principal é preto e único; escolha entre
              iguais é contorno. Nada verde: verde seria o resultado, não o gesto.
            </p>
          </header>

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
                  <MsFocusScreen :moment="s.moment" :landscape="s.landscape" />
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
