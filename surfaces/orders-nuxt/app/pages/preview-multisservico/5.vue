<script setup lang="ts">
// Prévia 5 (DEV-2026-030): a corrida do entregador da casa de ponta a ponta, em hiperfoco.
// Cada momento tem uma tela; a tela muda sozinha quando o momento muda. Dados fictícios.
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

const steps: Step[] = [
  {
    n: "0", moment: "call", title: "A chamada chega",
    when: "O balcão toca \"Enviar para Diego\". Chega como aviso no celular (o link instalado).",
    tap: "Nenhum: tocar no aviso só abre.",
    gestor: "Corrida A · Diego avisado às 12h31.",
    cliente: "Nada muda.",
  },
  {
    n: "1", moment: "pickup", title: "Na loja: conferir e sair",
    when: "O celular está a menos de 60 m da loja. Longe dela, a mesma tela diz \"Venha para a loja. Fica pronta às 12h40.\"",
    tap: "Saí da loja.",
    gestor: "Diego chegou à loja. Ao tocar Saí: A47 e C03 saem para entrega.",
    cliente: "\"Diego está a caminho. Deve chegar por volta de 12h46.\"",
  },
  {
    n: "2", moment: "drive", landscape: true, title: "Dirigindo: só o caminho",
    when: "Depois de Saí, e de novo depois de cada entrega. Em movimento a tela trava neste modo: nada para ler, nada para tocar.",
    tap: "Nenhum.",
    gestor: "Diego na rua · 0 de 2 · posição ao vivo no mapa.",
    cliente: "A hora prevista se ajusta sozinha.",
  },
  {
    n: "3", moment: "door", title: "Na porta: entregar certo",
    when: "A 80 m da parada e parado há 15 s. Sem sinal de GPS, aparece \"Cheguei\" quando passa a hora prevista.",
    tap: "Entreguei.",
    gestor: "A47 entregue às 12h47.",
    cliente: "Ao chegar: \"Diego chegou.\" Ao entregar: \"Entregue às 12h47.\"",
  },
  {
    n: "3b", moment: "failed", title: "Se não deu",
    when: "Só quando ele toca \"Não consegui\". Nunca automático.",
    tap: "O motivo (1 toque).",
    gestor: "Aviso com o motivo e \"Ligar para Marina\". A sacola volta com Diego.",
    cliente: "A loja liga; nenhuma mensagem automática.",
  },
  {
    n: "4", moment: "door-card", title: "Na porta seguinte (cartão)",
    when: "Igual ao 3. Cartão mostra o valor e qual maquininha; já pago mostra só \"Já pago. Só entregar.\"",
    tap: "Entreguei.",
    gestor: "C03 entregue às 12h55.",
    cliente: "O mesmo do 3, só para o Paulo.",
  },
  {
    n: "5", moment: "back", landscape: true, title: "Voltando: o acerto",
    when: "Depois da última parada. A tela diz o que entregar no caixa, já com o troco descontado.",
    tap: "Nenhum.",
    gestor: "Diego volta com R$ 100,00 em dinheiro e a maquininha azul.",
    cliente: "Nada.",
  },
  {
    n: "6", moment: "closed", title: "Fechada",
    when: "Quem fecha é o balcão, ao conferir o dinheiro e a maquininha no Gestor (\"Entregador voltou\").",
    tap: "Nenhum.",
    gestor: "Corrida A fechada. A pagar a Diego hoje: R$ 27,00.",
    cliente: "Nada.",
  },
];
</script>

<template>
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default pb-32" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-8 py-8">
          <header class="flex flex-col gap-1">
            <MsPreviewNav :current="5" />
            <h1 class="op-title font-semibold text-highlighted">Prévia 5 · A corrida do entregador da casa, em hiperfoco</h1>
            <p class="op-body text-toned">
              Uma tela por momento, e a tela muda sozinha quando o momento muda: na loja, dirigindo (carro ou moto), na porta. Em cada uma, só o
              que importa ali. A corrida inteira de duas entregas custa <strong class="text-highlighted">3 toques</strong> ao entregador: Saí,
              Entreguei, Entreguei.
            </p>
            <p class="op-micro text-muted">
              Cores: a cor da corrida (azul, a da corrida A) é só identidade, na letra e na rota. Botão principal é preto, um por tela. Não há botão
              verde: verde seria o resultado, não o gesto.
            </p>
          </header>

          <div class="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-x-8 gap-y-10">
            <article v-for="s in steps" :key="s.n" class="flex flex-col gap-3" :class="s.landscape ? 'col-span-2' : ''">
              <div class="flex items-baseline gap-2">
                <span class="grid size-8 shrink-0 place-items-center rounded-lg bg-inverted text-sm font-bold text-inverted">{{ s.n }}</span>
                <h2 class="op-title text-highlighted">{{ s.title }}</h2>
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

          <section class="flex flex-col gap-1 rounded-xl border border-dashed border-accented p-4 op-body text-toned">
            <p class="font-semibold text-highlighted">Regras que fazem isso funcionar</p>
            <p>· O momento vem de três sinais, nesta ordem: o toque dele, a distância (loja, parada) e o movimento. Nunca marca entregue sozinho.</p>
            <p>· Dirigindo, a tela não pede nada: só a próxima manobra e o destino em letra grande. Funciona deitado no suporte.</p>
            <p>· Na porta, a conta já vem feita: quanto receber, com quanto o cliente paga e quanto devolver.</p>
            <p>· O troco que sai da gaveta é o que a porta pede (R$ 100,00 menos R$ 58,00 = R$ 42,00), e o acerto da volta já desconta o que ele devolveu.</p>
            <p>· "Voltei à loja" não existe: quem fecha é o balcão, que confere o dinheiro e a maquininha.</p>
            <p>· Sem sinal, o toque fica guardado e vai quando a rede volta; a tela não espera a rede para seguir.</p>
          </section>
        </main>
      </div>
    </Teleport>
  </div>
</template>
