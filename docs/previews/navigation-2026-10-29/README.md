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

## Tela proposta sem controles de comparação

Use **Ver tela proposta** no laboratório ou nos quadros da comparação. O parâmetro
`clean=1` remove toda a faixa de estudo, sem acrescentar controle flutuante de teste.
O cabeçalho restante pertence à proposta do produto. O modo é preservado durante
navegação, troca de app e retorno à Central. A/B e composição ficam no laboratório,
acessível removendo `clean=1` do endereço ou voltando à aba de comparação.

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

## Rodada de composição das barras

O controle **Composição** (ícone de ajustes no celular) permite mover os recortes
entre a barra superior secundária e a inferior secundária, mostrar os atalhos
inferiores também no desktop e experimentar a ação flutuante no desktop.
A configuração acompanha os dois quadros da comparação. São alternativas para
avaliação, não preferências finais do produto.

Os atalhos abaixo abrem diretamente o mesmo destino em A e B, com um toque:

| App | Atalho | Destino |
|---|---|---|
| Gestor | Pedidos | Em andamento |
| Gestor | Produtos | Catálogo |
| Gestor | Clientes | Clientes |
| Compras | Visão geral | Visão geral |
| Compras | Reposição | Reposição |
| Compras | Receber | Conferência de recebimento |

**Mais** abre a navegação completa em ambas. Os atalhos são estáveis; o destaque
indica o assunto atual, sem transformar o toque em abertura de submenu na variante B.

| Recurso | Responsabilidade proposta |
|---|---|
| Cabeçalho | App atual, localização, Central, troca de app e ações da página no desktop |
| Lateral ou gaveta | Organização completa por assuntos e destinos |
| Superior secundária | Recortes locais do conteúdo, sem duplicar navegação entre páginas |
| Inferior secundária | Paginação e posição na lista; alternativa para recortes próximos ao polegar |
| Inferior principal | Atalhos estáveis para destinos frequentes |
| Flutuante contextual | Uma próxima ação da tarefa, acompanhada do contexto necessário |

A recomendação inicial é recortes no topo, paginação embaixo e atalhos inferiores
no mobile. A ação flutuante aparece quando há tarefa para concluir, como recebimento
ou contagem. No desktop, essa ação fica no cabeçalho por padrão. Ela não cobre o
conteúdo: fica em fluxo entre a área rolável e os atalhos; durante edição de campos
no mobile, sai de cena. O teclado virtual de dispositivo físico ainda precisa de
validação. Seleção em lote deve substituir a faixa contextual existente, conforme o
OperatorBulkBar, e não criar outra camada fixa. Esse cenário não é simulado aqui.

A lateral A ganhou superfície clara no assunto expandido, ícones e seleção com o
mesmo cuidado visual de B. O catálogo tem nove produtos fictícios, em páginas de seis,
para tornar o rodapé testável. A conferência troca Resolver diferença por Confirmar
entrada após a decisão; a contagem explica por que Revisar está indisponível.

A inspiração do Admin foi a separação entre navegação, ações da lista, ações de cada
registro e conclusão do formulário. Referências: [ações do ModelAdmin](https://unfoldadmin.com/docs/configuration/modeladmin/),
[tabs de listagem](https://unfoldadmin.com/docs/tabs/changelist/) e
[submit line](https://unfoldadmin.com/docs/actions/changeform-submitline/).
A semântica de salvar antes de executar do Admin não foi transportada para Nuxt.
A composição respeita como referência os componentes existentes
`OperatorActionBar.vue` e `OperatorBulkBar.vue` do operator-kit, sem editá-los.

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

## Avaliação crítica com telas limpas, terceira rodada

Recomendação de desenho, ainda sem aprovação: B no desktop e árvore agrupada A no
mobile, com a mesma taxonomia e os mesmos destinos/atalhos. A escolha é da apresentação
por largura e tarefa, não duas arquiteturas de informação concorrentes.

| Variante | Desktop | Mobile |
|---|---|---|
| A | Economiza largura e aproxima assunto/destino; a árvore longa pode exigir rolagem e acordeões esconderem alternativas | Expõe assunto e destino no mesmo percurso; exige grupos curtos e destaque claro da localização |
| B | Explicita contexto e escala melhor com muitos destinos; duas colunas podem roubar espaço de tabelas e ficar vazias em assuntos pequenos | Drill-down exige ida/volta e memória de contexto; não traz o ganho de duas colunas simultâneas |

B não deve impor uma segunda coluna vazia nem duas colunas expandidas em largura
intermediária. Preservar o último destino por assunto é um refinamento a avaliar.
O fluxo da tarefa tem mais peso que a preferência visual pela variante.

Refinamentos recomendados, sem transformar todos em controles adicionais:

- Cabeçalho: reduzir repetição do nome do app em marca/chip/breadcrumb, distinguir
  busca na suíte da busca na lista e testar um acesso inequívoco à Central. No mobile,
  validar se seletor de assunto e menu se complementam ou competem. Descrição longa
  de página não precisa consumir altura fixa durante toda a rolagem.
- Faixa superior secundária: manter recortes úteis e curtos, estado ativo inequívoco
  e overflow visível. Não colocar ações de salvar, destinos de apps e filtros avançados
  na mesma fila. Os controles Todos/À venda/Esgotados são filtros de uma lista com
  aparência de tabs, não navegação entre páginas; essa distinção precisa permanecer.
- Filtros: busca direta, recortes frequentes à vista, demais critérios em painel com
  Aplicar/Limpar, critérios ativos legíveis e contagem. Próximos cenários: período,
  fornecedor, múltiplos critérios, vazio, carregamento e falha de carregamento.
- Ordenação: explícita e estável. Mudar recorte ou ordem volta à primeira página.
  Preservar busca, filtros, ordem, página e posição ao abrir/fechar registro; ainda
  falta persistir esses estados no endereço para compartilhamento/reload.
- Rodapé fixo da lista: paginação e posição. Rodapé fixo do registro: anterior/próximo
  no recorte atual e ações do registro. Não empilhar uma barra flutuante de salvar
  sobre outro rodapé que já salva o mesmo registro.
- Seleção em lote: a faixa de seleção deve substituir o contexto de ações, com
  quantidade e alcance da seleção claros, sem acrescentar uma terceira barra inferior.
  Ainda não simulada.
- Feedback: confirmação de resultado em verde, erro em vermelho, aviso em âmbar, no
  topo do contexto que originou a mensagem, com texto e fechamento explícito. Erros
  não devem desaparecer por temporizador. Erro de campo também deve estar associado
  ao campo; esse vínculo e proteção completa ao fechar edição ainda estão pendentes.

Exemplos disponíveis no Catálogo: filtro por coleção, ordenação Nome/Menor preço/
Maior preço, paginação fixa de seis itens, detalhe com anterior/próximo no recorte
filtrado e ordenado, ações de registro em rodapé fixo e erro de preço no topo do detalhe.
Alterar o preço e tentar próximo exibe aviso sem descartar a edição. Salvar válido
exibe confirmação verde no topo da lista. Tudo é memória local.

O Admin/Unfold ensina a separar ações da lista, da linha, do detalhe e da conclusão;
a oferecer filtros horizontais ou em painel e aplicar filtros que exigem preenchimento.
Referências oficiais: [ModelAdmin](https://unfoldadmin.com/docs/configuration/modeladmin/)
e [filtros](https://unfoldadmin.com/docs/filters/introduction/).
São pistas de responsabilidade e comportamento, não justificativa para trazer a
organização por modelos ou a densidade do Admin para o posto de trabalho Nuxt.

## Caminho escolhido para experimentar, quarta rodada

Autorização do dono: experimentar B no desktop e árvore A no mobile, somente nas
prévias. Use `layout=adaptive&clean=1`. A navegação muda no mesmo ponto em que a
lateral permanente dá lugar à gaveta. Os links antigos com variante explícita seguem
como comparação histórica. A composição responsiva tem um único mapa de assuntos.

Cabeçalho: marca Shopman na lateral; app atual com troca; Central explícita; busca de
destinos; título da página uma vez. Saiu a descrição fixa de cada página, o seletor
de assunto redundante no mobile e a repetição do app e destino no breadcrumb. Uma
única ação no cabeçalho controla a compactação da primária. A contextual mantém seu
controle próprio. O retorno de uma travessia preserva sua faixa específica.

Rodapé fixo: superfície clara contínua, borda sutil, contador e paginação agrupada.
No detalhe, o navegador de registros e as ações usam a mesma família visual. Flutuante:
superfície escura destacada e uma ação operacional. Ambos reservam espaço em fluxo;
fixo descreve sua permanência durante a rolagem do conteúdo, não sobreposição sobre ele.

O catálogo tem lista/grade reais e densidade Confortável/Compacta no menu de três
pontos. Trocar representação preserva o recorte, ordem e página. Apresentação e densidade
ficam no endereço; recorte e busca ainda são memória local. A matriz por canal mantém
colunas e não oferece grade: cartões apagariam a comparação que dá sentido à tela.
Menus por registro oferecem Editar produto e Disponibilidade nos canais. Abrir pelo
nome continua direto. O menu geral contém densidade e edição de preços no tabelão;
Novo produto continua visível. Escape fecha o popover e devolve o foco ao acionador.

### Revisão adversarial da composição por tarefa

| Caso de uso | Composição recomendada | Evitar / próxima prova |
|---|---|---|
| Pedidos em andamento | Quadro por etapa, busca e recortes de entrega; ação no pedido | Grade decorativa sem etapas; ordenar por beleza em vez de urgência |
| Saída | Fila pela próxima ação, retirada/despacho claros | Esconder liberação ou divergência nos três pontos |
| Histórico | Lista, período, canal, situação, paginação fixa | Quadro de etapas para pedido já encerrado |
| Catálogo | Lista por padrão para preço/saldo; grade opcional para reconhecimento; filtros e ordenação coordenados | Grade só com ícones pouco agrega; avaliar com fotos reais antes de promovê-la a padrão |
| Coleções | Cards de agrupamento, ordem e composição explícitas | Misturar agrupamento de vitrine com cadastro de produto |
| Clientes e grupos | Lista, busca por nome/contato, detalhe e ações contextualizadas | Cards grandes sem informação útil; expor unificação como ação cotidiana sem consequência clara |
| Unificações | Comparação lado a lado e revisão do resultado; aviso no topo | Ação destrutiva escondida num menu sem explicação |
| Canais e matriz | Configuração por canal e tabela comparativa de publicação/disponibilidade | Confundir canal ativo, produto publicado e estoque disponível |
| Rotinas e postos | Checklist para execução; lista de postos para configuração | Mesma tela para configurar o posto e trabalhar nele |
| Visão geral de Compras | Exceções e tarefas acionáveis; links diretos ao contexto | Painel de números sem próxima ação |
| Reposição | Lista comparável de necessidade, quantidade, unidade e fornecedor; ação de preparar compra | Grade de produtos que esconda unidade de compra/conversão |
| Fornecedores e custos | Lista; detalhe do fornecedor; comparação de preço/unidade/período | Preço sem unidade ou histórico; seleção em lote com alcance ambíguo |
| Recebimento | Documento, itens e diferenças; recortes; flutuante Resolver/Confirmar no mobile | Outra barra fixa com a mesma confirmação; reordenar itens durante conferência sem aviso |
| Insumos | Lista, SKU, unidade, saldo e urgência; detalhe contextual | Inferir vendável do comprável; novo estoque paralelo para o mesmo SKU |
| Contagem | Sequência de entrada, foco preservado, progresso e revisão | Campos compactos demais, saldo esperado enviesando a contagem ou atalhos de trocar layout durante digitação |

Regras transversais: uma ação principal por contexto; três pontos só para secundárias;
prioridade e bloqueio nunca dependem de abrir menu. Compacta reduz respiro, não tamanho
de toque nem informação essencial. Densidade é preferência de leitura, não filtro.
Busca/filtros/ordem/paginação devem formar um estado único quando houver implementação
aprovada; nenhuma preferência deve vazar entre tarefas incompatíveis. Recolhimento de
barras não pode esconder a localização. Evitar colocar todas as faixas em toda página.

Próximas provas ainda necessárias: seleção em lote; centenas de registros; nomes longos;
permissões; carregamento, falha e recuperação; alterações concorrentes; salvar/cancelar
com edição pendente; teclado físico e virtual; contraste e leitores de tela; tablets
intermediários. Não há aprovação global de componentes ou de fluxos só porque a
estrutura de navegação foi escolhida para experimentar.

### Benchmarks consultados

- [Shopify: ResourceList](https://shopify.dev/docs/apps/build/app-home/migrate-from-polaris-react/resource-list): recomenda tabela quando comparar colunas é essencial; representação estreita adaptada ao dispositivo.
- [Shopify: IndexFilters](https://shopify.dev/docs/apps/build/app-home/migrate-from-polaris-react/index-filters): busca, filtros, ordenação e vistas devem compartilhar o estado da consulta. Não simular vistas salvas como se fossem persistentes sem suporte real.
- [Odoo: busca, filtros e agrupamento](https://www.odoo.com/documentation/19.0/applications/general/search.html): opções articuladas em torno do mesmo conjunto de registros.
- [Odoo: vistas](https://www.odoo.com/documentation/19.0/applications/productivity/studio/views.html): distintas representações conforme o trabalho. Não confundir kanban de etapas com grade visual de catálogo.

Aplicação crítica: usar esses princípios, sem copiar o excesso de controles de um ERP
generalista. Nenhuma dependência Shopify/Odoo/Unfold foi adicionada ao protótipo ou apps.
