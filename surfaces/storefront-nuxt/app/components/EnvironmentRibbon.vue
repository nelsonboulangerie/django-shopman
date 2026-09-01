<script setup lang="ts">
// AMBIENTE — a fita que diz "esta não é a loja de verdade".
//
// Existe porque a loja de teste é indistinguível da real: mesma marca, mesmo
// cardápio, mesmo checkout. Sem aviso, um amigo convidado para experimentar faz
// um pedido achando que vai receber pão, e o operador recebe um pedido achando
// que é de mentira. Os dois estão certos e os dois estão errados.
//
// ## Fita diagonal, e as três armadilhas dela
//
// A escolha é do dono: tem que ser impossível de passar despercebido. Fita de
// canto entrega isso — mas ela flutua sobre o conteúdo, e flutuar tem preço.
// Três coisas que a fazem custar caro, e o que cada uma exigiu:
//
//   1. **Sumir ao rolar.** `fixed`, não `absolute`. Um aviso que só aparece no
//      topo da página não avisa quem entrou por link direto de produto.
//   2. **Cobrir botão.** `pointer-events-none` no contêiner inteiro: o toque
//      atravessa. Ela cobre visualmente o canto do header (a sacola), e isso é
//      deliberado — mas nunca IMPEDE o toque nele.
//   3. **Leitor de tela.** `role="status"` no elemento e o texto legível dentro;
//      a rotação é só transformação visual, não muda a ordem de leitura.
//
// ## Calma, mesmo sendo impossível de ignorar
//
// Âmbar e não vermelho. O cliente do alpha vê isso em TODA página; alarme
// repetido vira ruído e a pessoa para de ler. Chamar atenção pela POSIÇÃO (o
// canto, sempre ali) custa menos que chamar pela cor.
//
// A frase vem do SERVIDOR (`public_config.environment_notice`), derivada de
// `SHOPMAN_ENVIRONMENT` — a mesma variável que já decide o gate de deploy, o
// mock de pagamento e o debug do OTP. Em produção ela volta vazia e este
// componente não renderiza nada. Sem interruptor próprio: dois interruptores
// para o mesmo fato é a garantia de que um dia eles vão discordar.
const { publicConfig } = useShopSession()

const notice = computed(() => publicConfig.value?.environment_notice || '')
</script>

<template>
  <!-- A janela quadrada recorta a fita no canto; sem ela a barra rotacionada
       vazaria para fora da viewport e criaria rolagem horizontal. -->
  <div
    v-if="notice"
    class="pointer-events-none fixed right-0 top-0 z-50 size-40 overflow-hidden"
    aria-hidden="true"
  >
    <!-- ⚠️ GEOMETRIA, não gosto — e ela tem UMA regra que decide se a fita
         parece fita ou parece retângulo colado torto:
         **as duas pontas têm que sair PELA TELA.**

         A janela recorta nas quatro bordas, mas só duas delas são borda de
         viewport (topo e direita). Ponta que termina nas outras duas fica com um
         corte reto boiando no meio da página — foi o defeito da primeira versão.

         Para a ponta de cima sair pelo TOPO antes de bater na esquerda, e a de
         baixo sair pela DIREITA antes de bater embaixo, o centro da barra tem de
         ficar mais perto da direita do que do topo (cx > cy), e a meia-diagonal
         da barra tem de caber em `max(cy, S−cx) < k < min(cx, S−cy)`.

         Com S=160 (`size-40`), cx≈92 e cy≈58: k≈85 satisfaz 68 < k < 92. Sobra
         de 36px acima e 22px à direita — folga suficiente para outra fonte ou
         zoom não trazerem o corte de volta para dentro.

         A LARGURA da janela também define quanto texto cabe: o trecho visível da
         barra é `(S − cx + cy)·√2` ≈ 178px, e "AMBIENTE DE TESTES" ocupa ~145px.
         Encolher a janela sem encurtar o texto o corta — foi o segundo defeito. -->
    <div
      class="absolute -right-11 top-11 w-60 rotate-45 bg-amber-400 py-1.5 text-center shadow-md"
    >
      <span class="text-xs font-semibold uppercase tracking-wide text-amber-950">
        {{ notice }}
      </span>
    </div>
  </div>

  <!-- A mesma verdade para quem não vê a fita. Fora do contêiner rotacionado
       porque `rotate` em texto lido por voz não ajuda ninguém. -->
  <span v-if="notice" role="status" class="sr-only">{{ notice }}</span>
</template>
