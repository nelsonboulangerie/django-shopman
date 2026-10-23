# WP destacado: lista compacta e foco sequencial no operador

**Estado:** levantamento inicial, sem autorização para aplicação em massa
**Origem:** prévia do CRUD humano do Compras, 23/10/2026
**Alcance:** superfícies Nuxt de operador; Storefront fica fora

## A hipótese

Em telas com muitos registros semelhantes e uma tarefa clara por registro, o celular
funciona melhor em dois tempos:

1. uma lista compacta para localizar, comparar e escolher;
2. uma página de foco para ler ou concluir um registro, com contexto `N de total` e
   passagem segura para anterior/próximo.

O padrão reduz disputa entre lista, formulário e ações. Ele não significa transformar
toda lista em carrossel, nem impor ordem onde prioridade, segurança ou tempo real mudam
enquanto a pessoa trabalha.

## O que já existe

| Superfície | Situação atual | Leitura |
|---|---|---|
| Compras: Insumos e Fornecedores | lista compacta; registro vira página abaixo de `xl`; trilha preserva a ordem filtrada; anterior/próximo na `OperatorActionBar` móvel | referência de leitura do padrão |
| Compras: Receber | lista de itens; item focado por `?line=<id>`; `OperatorRecordNav` percorre a ordem da entrada; ficha concentra conferência, quantidade, valor, validade e lote | o conceito já existe. No celular, anterior/próximo fica no cabeçalho da ficha porque a base pertence à ação da entrada; avaliar a composição, não copiar mecanicamente |
| Pedidos: fila e histórico | lista/tabela grava a trilha; detalhe do pedido tem anterior/próximo; a barra inferior prioriza a ação operacional do pedido | implementação madura, referência para tarefa transacional |
| Produção: receitas, qualidade e fechamento | trilhas entre receitas ou lotes e detalhe focado | implementação existente; Produção não faz parte desta frente |
| Cozinha: ticket em foco | tela focada e ação do momento na base | não é uma trilha estável: urgência e SSE podem reordenar a fila; anterior/próximo automático pode ser incorreto |
| PDV: encomendas | lista e detalhe endereçável; ação operacional na base | candidato a trilha, desde que preserve o retorno e não concorra com entregar/receber |

## Candidatos para diagnóstico, não para mudança automática

### Prioridade alta

1. **Pedidos: Clientes**. Há tabela compacta e página de cliente, mas não há trilha entre
   os clientes do recorte atual. É leitura extensa e relativamente estável.
2. **Pedidos: Catálogo**. Há tabela e detalhe endereçado por `?sku=`, porém o detalhe
   ainda é um workspace sobre a lista. Precisa separar leitura, edição e rascunho sujo
   antes de decidir a navegação móvel.
3. **Marketing: Campanhas e Modelos**. São coleções com edição focada em painel. O
   diagnóstico deve verificar se o objeto merece página móvel e Salvar/Descartar na
   base, mantendo anterior/próximo apenas na leitura.

### Prioridade média

4. **Marketing: Plataformas**. Lista pequena e workspace longo. Pode ganhar foco total,
   mas anterior/próximo só ajuda se a pessoa realmente revisar várias plataformas em
   sequência.
5. **PDV: Maquininhas e Impressoras**. CRUDs curtos e similares. Avaliar página focada
   somente se a edição atual estiver comprimida; modal curto pode continuar sendo a
   solução certa.
6. **PDV: Encomendas**. A trilha é plausível, mas a ação de entrega tem precedência
   sobre a navegação.

### Não aplicar sem uma razão nova

- **B.I.**: linhas são resultados analíticos, não registros de uma tarefa repetitiva.
- **Central**: é índice de destinos, não lista de registros.
- **Carrinho do PDV**: o contexto é a venda inteira; isolar uma linha quebra a visão do
  total e dos demais itens.
- **Fila viva da Cozinha**: a ordem muda por tempo real e prioridade. Uma trilha gravada
  pode levar o operador ao ticket errado no momento errado.
- **Comprar no Compras**: os cards formam uma decisão conjunta de reposição; não há hoje
  uma tarefa longa por item que justifique retirar a visão do conjunto.

## Contrato proposto

Um caso só entra no padrão se cumprir todos estes pontos:

1. A lista responde “qual item?” com nome, estado e próxima pendência, sem carregar o
   formulário inteiro.
2. O item focado tem URL ou query própria e sobrevive a atualizar, voltar e compartilhar
   o endereço dentro da operação.
3. A trilha guarda exatamente a ordem visível após busca, filtro e ordenação. O contexto
   diz `N de total` e nomeia a coleção.
4. No celular, o item principal ocupa a página. Gaveta fica para gesto curto ou
   secundário.
5. Em leitura, anterior/próximo pode morar na barra inferior. Em edição, a barra é de
   Salvar/Descartar. Em tarefa transacional, a ação do momento tem precedência; a
   navegação fica no cabeçalho ou em faixa própria, sem duplicar ações.
6. A ação concluída atualiza a lista. Avanço automático só existe quando for impossível
   confundir conclusão, prioridade ou registro.
7. Remoção, arquivamento e rejeição não dividem a barra principal com navegação.
8. A experiência passa primeiro em 320×568, depois 390×844, tablet e mesa, com tema
   claro/escuro, teclado, texto longo e retorno do histórico.

## Sequência do WP

1. Auditar cada candidato no turno do respectivo app, junto do CRUD humano já planejado.
2. Registrar para cada tela: objeto, lista de origem, estabilidade da ordem, ação do
   momento, risco de rascunho e comportamento após concluir.
3. Prototipar somente o candidato de maior valor e menor risco que não esteja em outra
   frente ativa.
4. Mostrar prévia local móvel e mesa para aprovação antes de qualquer push ou PR.
5. Só depois da aprovação transformar a decisão em componente ou orientação canônica.

Este WP não autoriza mudanças nas telas listadas. Ele impede que uma boa solução seja
copiada sem respeitar o trabalho real de cada superfície.
