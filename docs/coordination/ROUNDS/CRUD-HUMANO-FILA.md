# CRUD humano nas superfícies de operador

Fila contínua iniciada em 23/10/2026 a partir da unificação de Receita e ficha técnica
na Produção. A Produção permanece fora desta frente: a sessão original continua dona
daquele app.

## Critério transversal de aceitação

Cada app é fechado sozinho, em PR próprio e na fila de merge, antes do seguinte.
Antes de começar o próximo, a ordem abaixo deve ser conferida novamente contra
`origin/main`, PRs abertos, worktrees e `make inflight`.

1. O objeto da tela tem um nome só. Não há um segundo cadastro ou destino que represente
   a mesma coisa com outro rótulo.
2. A rota principal acompanha a tarefa real. Abas servem apenas a visões irmãs, estáveis;
   tarefas e comandos não fingem ser abas de cadastro.
3. No celular, lista, detalhe, formulário e ações cabem na sequência natural da página.
   Gaveta ou modal só entra quando o gesto é curto e secundário, nunca para cobrir o
   caminho principal.
4. Formulário usa fundo de página neutro, cards claros consistentes e campos no creme de
   entrada. Cor diferente precisa comunicar estado, não alternar arbitrariamente entre
   blocos.
5. A ação persistente da tarefa fica na base no celular, ao alcance do polegar, com o
   `OperatorActionBar`: Salvar, Publicar, Concluir e Descartar quando couber. Em leitura,
   anterior e próximo ocupam essa zona. Na mesa, a mesma semântica sobe para o cabeçalho
   ou para a região contextual, sem duplicar uma toolbar inteira.
6. Edição não mistura navegação destrutiva. Arquivar, excluir e trocar de registro não
   disputam a barra de Salvar/Descartar.
7. A primeira validação visual é `mobile-narrow` (320×568), depois `mobile-standard`,
   tablet e mesa. O gate inclui teclado, foco, zoom, tema claro/escuro e texto longo.
8. Componentes e tokens continuam canônicos do Nuxt UI e do `operator-kit`; copy segue
   omotenashi, acessibilidade, rotas em inglês e texto de tela em português.

## Inventário e ordem revalidável

| Ordem | App | CRUDs e superfícies relacionadas | Hipótese de maior risco |
|---:|---|---|---|
| 1 | Compras | Insumos, fornecedores, conversões, custos, contagem | `Base` mistura objetos com tarefas; detalhe principal abre como gaveta no celular |
| 2 | Pedidos | Catálogo, clientes, grupos, canais, postos e checklists | muitos destinos e edições em grade; há frente ativa, portanto não iniciar enquanto houver colisão |
| 3 | Marketing | campanhas, ofertas, plataformas e modelos | configurações irmãs e composição podem competir com a fila de decisões |
| 4 | PDV | terminais, maquininhas, impressoras, salão, atalhos e cozinha | ajustes numerosos dentro de um app de execução crítica |
| 5 | B.I. | perfis, cenários e exploração | parâmetros de análise podem parecer cadastros independentes sem necessidade |
| 6 | Cozinha | postos e retirada | pouco CRUD, mas alto custo de gesto e espaço em tablet/celular |
| 7 | Central | organização e entrada nas superfícies | não é CRUD clássico; revisar por último como índice humano da suíte |

`kitchensink-nuxt` é catálogo interno de componentes e `status-nuxt` é superfície pública;
não entram como apps operacionais desta fila. O Storefront também fica fora por ter voz e
arquitetura próprias.

## WP transversal destacado

O padrão móvel de lista compacta, registro em foco e trilha anterior/próximo ganhou um
levantamento próprio em
[WP-OPERATOR-MOBILE-FOCUS-TRAIL](../../plans/WP-OPERATOR-MOBILE-FOCUS-TRAIL.md).
Ele deve ser consultado durante o diagnóstico de cada app, mas não autoriza aplicação
mecânica: ação operacional, estabilidade da ordem e risco de rascunho decidem a forma.

## WP 1: Compras

Decisão de informação:

- `Insumos` e `Fornecedores` são as duas coleções irmãs da Base.
- `Lançar custos` e `Contar estoque` são tarefas com nome e entrada próprios, não abas.
- o detalhe de insumo ou fornecedor é página no celular e tablet; somente a mesa larga
  preserva o painel ao lado da lista.
- a leitura usa anterior/próximo na barra inferior do celular; edição conserva a barra
  canônica Salvar/Descartar do casco.
- formulários de insumo e fornecedor usam superfície neutra, seções em cards claros e
  campos no creme canônico. Formulários auxiliares não ganham uma terceira cor.

Limites deste WP: não muda regra de compra, projeção, API, banco ou o fluxo de Receber.
