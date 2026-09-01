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
//   3. **Leitor de tela.** O texto legível sai num `role="status"` à parte; a
//      rotação é transformação visual e não muda a ordem de leitura.
//
// ## Calma, mesmo sendo impossível de ignorar
//
// Âmbar e não vermelho. O cliente do alpha vê isso em TODA página; alarme
// repetido vira ruído e a pessoa para de ler. Chamar atenção pela POSIÇÃO (o
// canto, sempre ali) custa menos que chamar pela cor.
//
// O âmbar vem do token `warning` da casa, não de `amber-400` cru. O default do
// CSS é o mesmo âmbar (`#f59e0b` claro / `#fbbf24` escuro), mas a MARCA
// sobrescreve `--warning` em tempo de execução — na Nelson ele chega `#e09a4a`,
// o dourado da casa. É por isso que o token vale mais que a cor solta: ele
// acompanha a marca e o tema, e usa o par bg/foreground já provado em Badge e
// Alert. Custo medido contra o fundo escuro da loja: 7,5:1 em vez dos 10,6:1 do
// `amber-400` cru. Continua acima de AAA — a fita não perde o grito.
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
    class="pointer-events-none fixed right-0 top-0 z-50 size-44 overflow-hidden"
    aria-hidden="true"
  >
    <!-- ⚠️ GEOMETRIA — os quatro números abaixo (top-11, -right-21, w-72, h-8)
         são UM sistema. Mexer em um sozinho quebra a fita, e já quebrou duas
         vezes. `tests/surfaceGuardrails` prende a regra; leia aqui o porquê.

         A janela recorta nas quatro bordas, mas só DUAS são borda de viewport
         (topo e direita). Corte nessas some na tela; corte nas outras duas vira
         uma quina reta boiando no meio da página.

         Daí duas condições, e elas puxam para lados opostos:

         (1) BLEED — as quatro quinas da barra têm de cair fora da tela.
             Sobra hoje: 30px além de cada borda.
         (2) CENTRAGEM — o texto está centrado na BARRA, então a barra tem de
             estar centrada no TRECHO VISÍVEL, senão o texto sai torto. Isso
             acontece quando o centro cai na antidiagonal do canto, e a conta
             que garante isso é:

                 w = 2·(right) + 2·(top) + h        288 = 168 + 88 + 32 ✓

         Encostar mais a barra no canto melhora (1) e encurta o trecho visível;
         afastar faz o contrário. O comprimento visível é `2·√2·(top + h/2)`
         ≈ 170px, e a frase ocupa 105px — sobra ~32px de cada lado.

         A JANELA (size-44) só precisa ser grande o bastante para que suas duas
         bordas falsas fiquem longe: a barra mergulha até 143px, a janela corta
         em 176px. Aumentar a janela é seguro; DIMINUIR traz a quina de volta. -->
    <div
      class="absolute -right-21 top-11 flex h-8 w-72 rotate-45 items-center justify-center bg-warning shadow-md"
    >
      <!-- flex/items-center e não padding: o `span` inline assentava na linha de
           base de uma caixa de 24px e o texto ficava fora do centro vertical. -->
      <span class="text-xs font-semibold uppercase tracking-wide text-warning-foreground">
        {{ notice }}
      </span>
    </div>
  </div>

  <!-- A mesma verdade para quem não vê a fita. Fora do contêiner rotacionado
       porque `rotate` em texto lido por voz não ajuda ninguém. -->
  <span v-if="notice" role="status" class="sr-only">{{ notice }}</span>
</template>
