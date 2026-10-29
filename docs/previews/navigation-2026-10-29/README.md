# Prévias locais do Gestor e Compras

Estado: proposta para avaliação. Nenhuma variante aprovada. Protótipo independente,
autorizado pelo dono em 29/10/2026. Sem alteração dos apps, kit, Core, dados, baselines
ou deploy. Dados fictícios e estado em memória; recarregar restaura a amostra.

## Abrir

Na raiz desta worktree:

```bash
python3 -m http.server 4186 --bind 127.0.0.1 --directory docs/previews/navigation-2026-10-29
```

- [Gestor lado a lado](http://127.0.0.1:4186/?app=gestor&view=catalog&compare=1).
- [Compras lado a lado](http://127.0.0.1:4186/?app=compras&view=receiving&compare=1).
- [Gestor com lateral única](http://127.0.0.1:4186/?app=gestor&view=catalog&variant=single).
- [Gestor em dois níveis](http://127.0.0.1:4186/?app=gestor&view=catalog&variant=double).
- [Compras com lateral única](http://127.0.0.1:4186/?app=compras&view=receiving&variant=single).
- [Compras em dois níveis](http://127.0.0.1:4186/?app=compras&view=receiving&variant=double).

O servidor escuta somente em loopback e entrega apenas este diretório. A política da
página impede conexão de dados (`connect-src 'none'`). Fonte, script e estilos são
locais. Não há configuração nem credencial de serviço real.

## Comparação justa e organização por assuntos

As variantes têm os mesmos destinos, dados de partida e conteúdo. A lateral única
mostra o grupo selecionado aberto e os demais recolhidos por padrão. Em dois níveis,
a primeira barra escolhe o assunto e a segunda mostra apenas seus destinos.

A alternância A/B mantém a tela. A comparação simultânea sincroniza o destino e
preserva o recolhimento independente das barras. As simulações de edição são próprias
de cada quadro; recarregue para recuperar a mesma amostra. No desktop, os quadros são
reduzidos de 1280 × 840. No celular, ficam empilhados usando a largura real. O link
Abrir em tamanho real permite avaliar conforto sem redução.

| App | Assunto | Destinos propostos | Correspondência funcional atual |
|---|---|---|---|
| Gestor | Pedidos | Em andamento, Saída, Histórico | Quadro com recortes e `/history` |
| Gestor | Produtos | Catálogo, Coleções | `/catalog`, incluindo gestão de coleções |
| Gestor | Clientes | Cadastro, Grupos, Unificações | `/customers`, `/customers/groups`, `/customers/merges` |
| Gestor | Canais | Canais de venda, Catálogo por canal | `/feeds`, `/channels/[ref]/catalog` e matriz do catálogo |
| Gestor | Operação | Rotinas, Postos | `/checklists`, `/workstations` |
| Compras | Visão geral | Visão geral | Painel `/` |
| Compras | Compras | Reposição, Fornecedores, Custos de compra | `/buy`, `/base/suppliers`, `/base/costs` |
| Compras | Recebimentos | Conferência, Divergências | `/receive`; divergências são recorte da mesma conferência |
| Compras | Estoque | Insumos, Contagem | `/base/materials`, `/base/count` |

Destinos mais explícitos não criam novos domínios ou capacidades. Histórico e cadastros
saem de Ajustes; Base deixa de ser uma categoria do trabalho.

## Mobile primeiro e cabeçalho da suíte

O celular tem navegação inferior, cards com campos identificados, foco no registro e
alvos principais de toque com pelo menos 44 px. A variante A tem árvore agrupada numa
gaveta. A B separa assunto e destino, com retorno a Todos os assuntos. O cabeçalho
também abre os destinos do assunto atual. Tablet em pé segue essa lógica móvel;
desktop mantém tabelas e barras expandida/compacta/oculta.

O botão com o nome do app permite trocar de app ou voltar à Central. A Central oferece
Gestor, Compras e tarefas com destino exato; outros apps não são simulados nesta rodada.
A troca preserva o último destino de cada app na sessão. O navegador pode voltar
entre destinos, e a Central permite retomar a tarefa anterior.

Há uma travessia concreta: buscar **Geleia**, abrir o produto e escolher **Abrir insumo
em Compras**. SKU e saldo são os mesmos. O retorno pelo cabeçalho restaura busca e
detalhe do produto de origem.

## Roteiro para avaliação

1. Localizar um pedido concluído sem passar por Ajustes.
2. Buscar Geleia, consultar o preço, atravessar para seu insumo e voltar ao produto.
3. Encontrar grupos de clientes e catálogo por canal.
4. Distinguir reposição, recebimento e contagem em Compras.
5. Resolver a falta de 2 kg de manteiga na nota fictícia e observar a confirmação
   desbloqueada, sem escrita em estoque real.
6. Retornar à Central, abrir a tarefa de saída e trocar de app pelo cabeçalho.
7. Comparar tudo no celular e desktop; recolher as duas barras separadamente.

Registrar preferência e motivo por tarefa e dispositivo. Aprovação visual não autoriza
implementação ou deploy. Esta não é uma simulação de todas as permissões ou falhas das
APIs; vários detalhes de cadastro apenas representam o acesso à função.

## Evidências

O [registro de verificação](verification.md) distingue o que foi conferido e o que
continua fora desta rodada. As capturas são da prévia, não são baselines dos apps:

- [Gestor com lateral única](captures/gestor-single.jpg).
- [Gestor em dois níveis](captures/gestor-double.jpg).
- [Compras com lateral única](captures/compras-single.jpg).
- [Compras em dois níveis](captures/compras-double.jpg).
- [Gaveta móvel em uma árvore](captures/gestor-mobile-single.jpg).
- [Gaveta móvel em dois níveis](captures/gestor-mobile-two-levels.jpg).
