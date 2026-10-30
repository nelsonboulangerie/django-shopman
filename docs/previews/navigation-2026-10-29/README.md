## Estado da revisão após retorno do dono

A rodada transversal genérica foi retirada da recomendação de aprovação. Entrada atual: `operator-review.html#pdv`, com análise por tarefa na ordem PDV → KDS → Gestor. `operator-preservation.json` registra o inventário de preservação e os cenários. Essa página é análise de fonte/contratos, não uma nova prévia fiel dos apps ou teste de runtime.

O exemplo de fechamento simplificado foi retirado por violar a contagem cega: não serve para aprovar layout nem regra de caixa. Os demais exemplos transversais mantêm aviso de reavaliação e ficam somente como histórico. As decisões explícitas de navegação/visual de Gestor e Compras continuam registradas, sem representar autorização para substituir seus componentes funcionais.

# Prévias locais do Gestor e Compras

Estado: proposta para avaliação. Nenhuma variante aprovada. Protótipo independente,
autorizado pelo dono em 29/10/2026. Sem alteração dos apps, kit, Core, dados, baselines
ou deploy. Dados fictícios e estado em memória; recarregar restaura a amostra.

## Direção vigente: preservar o design amadurecido

O dono esclareceu que o escopo é navegação e composição, não redesenho do design
system. O silêncio sobre detalhes dos mocks não é aprovação. A proposta vigente
restaura o rail bronze e usa o kit real como referência para botões, badges soft,
cores, cards, avisos e receitas de overlay. As rodadas anteriores abaixo são histórico
de experimentação; o menu inteiro claro da sexta rodada foi retirado.

Abra o [roteiro completo](http://127.0.0.1:4186/review.html): 20 telas, 56 exemplos de
composição de fluxo e seletor de estados. O mesmo caminho funciona no túnel corrente.
O roteiro é ferramenta de revisão, sem entrar no produto proposto.

## Abrir

Na raiz desta worktree:

```bash
python3 docs/previews/navigation-2026-10-29/serve.py
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

## Correção mobile-first, quinta rodada

O dono apontou excesso de controles e quebras evitáveis no mobile. A correção parte
agora de 320 px, antes de conferir o desktop. No catálogo móvel, a barra de ferramentas
vira uma linha única: busca, acesso a filtrar/ordenar e opções. Coleção e ordenação
ficam juntas no painel de filtros; a ordem aplicada permanece legível na contagem.
Lista/grade e densidade ficam nas opções de apresentação, sem seletores permanentes
competindo com a busca. No desktop, controles explícitos continuam disponíveis.

Os cards da lista móvel foram recompostos: nome e SKU, coleção como informação
secundária, preço e disponibilidade lado a lado, situação abaixo. Não é apenas redução
de tamanho de fonte. A primeira linha de registro observada em 390 px tem 163 px.
Alvos dos botões da toolbar, paginação e ação primária têm caixa de 44 px ou mais.

Na conferência, a nota usa ícone e identificação em grade; a divergência diz diretamente
Manteiga: faltam 2 kg / Na nota: 10 kg. Recebido: 8 kg. O botão redundante Ver divergências
sai da composição móvel, já atendida pelos recortes. Ler outra nota e Rever critérios
são acessíveis nas opções da página quando aplicáveis; não desaparecem por falta de
espaço. Botões primários do cabeçalho não quebram o rótulo; títulos longos podem ocupar
duas linhas sem truncamento. As capturas da quinta rodada substituem as anteriores
como referência de composição mobile, sem reescrever sua evidência histórica.

## Consolidação visual e invariantes da proposta, sexta rodada

Direção solicitada pelo dono: filtro → busca → opções; três pontos verticais; opções
dos registros e controles de fechar/dispensar sem borda; experimentação de menu mobile em tela inteira;
cabeçalho com hambúrguer para o app e ícone do app atual como acesso à Central. Saiu
o botão com texto que abria a troca de apps e saiu o segundo acesso destacado à
Central no cabeçalho. A Central continua nomeada dentro do menu, e suas tiles trocam
os apps. A descoberta desse gesto pelo ícone precisa de teste com operador de primeiro
uso: tooltip/aria ajudam, mas não substituem reconhecimento visual no celular.

As telas limpas antigas, inclusive links com variante explícita, passam a seguir a
composição responsiva consolidada. A/B permanecem no laboratório e seus iframes.

A árvore mobile agora ocupa a largura toda, com fundo claro, grupos sem caixas,
subitens recuados e apenas o destino atual com destaque de seleção. Evita deixar uma
faixa sem utilidade da tela de fundo. O cabeçalho do menu identifica o app atual; o
fechamento continua acessível por X e Escape; o restante da aplicação fica inerte.

A família de overlays usa bordas suaves, espaçamento e campos consistentes, título
claro, X discreto, corpo rolável e rodapé apenas quando há ações. No mobile, formulários
curtos são painéis centrados; busca global usa um painel ancorado no alto, com altura conforme os resultados e
resultados roláveis agrupados por app, nome do destino e assunto em linhas distintas.
Busca inclui Gestor e Compras, aceita acentos/caixa e apresenta estado vazio. Enter
abre o primeiro resultado e ArrowDown leva a ele. O campo permanece na mesma posição durante a filtragem. Não há dois scrolls no painel de busca.
Os avisos de simulação foram retirados das telas limpas, sem alterar sua natureza local.

### Invariantes para a revisão final do Shopman

Estes critérios consolidam as decisões existentes de Omotenashi e os pedidos desta
conversa. Não aprovam implementação nem substituem os contratos dos componentes reais.

| Critério | O que reprova a proposta |
|---|---|
| Primeiro inequívoco, depois curto | Rótulo bonito mas ambíguo; depender de memória ou completar sentido; esconder unidade ou consequência |
| Mobile como ponto de partida | Controles quebrando linha por herdar toolbar desktop; diminuir alvo de toque para caber; conteúdo atrás de barra |
| Um conceito, um nome | Reabrir vocabulário canônico sem decisão; nomes distintos para o mesmo gesto ou grandeza |
| Hierarquia de trabalho | Principal escondida nos três pontos; todas as ações com o mesmo peso; escolha sem relação com a tarefa |
| Navegação previsível | Hambúrguer e ícone de app com o mesmo efeito; atalhos com destino variável; trocar de representação perde recorte |
| Funções visíveis na medida certa | Mostrar grade em matriz comparativa; densidade como controle permanente; barra sem tarefa real |
| Contexto preservado | Perder filtro, ordem ou posição ao consultar registro; navegar adiante descartando edição sem decisão |
| Feedback preciso | Cor como único sinal; erro que some por tempo; sucesso que cobre a ação; problema sem caminho de correção |
| Overlay operável | Foco atrás do painel; Escape inoperante; fechamento sem nome acessível; formulário com dupla rolagem desnecessária |
| Beleza com propósito | Bordas em cada ícone; caixas aninhadas sem significado; contraste fraco; detalhe decorativo roubando espaço útil |
| Coerência cross-system | Mesma função com composição e gesto incompatíveis sem motivo de tarefa, audiência ou dispositivo |
| Produto separado do Core | Organização visual ditando dependências de domínio ou contornando orquestrador/projeções |

Referências internas obrigatórias: [copy Omotenashi](../../reference/omotenashi-copy.md)
e [vocabulário da suíte](../../reference/suite-vocabulary.md). A meta de 44 px é uma
escolha de conforto desta proposta, não uma afirmação de que WCAG AA exige 44 px:
o [critério mínimo da W3C](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
trata 24 px e exceções. Para foco, teclado e fundo inerte, consultar o
[padrão de diálogo modal W3C](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).

O que não deve virar dogma: quantidade de colunas, altura de modal, grade em qualquer
cadastro, número fixo de ações e menu sempre recolhido ou expandido. Essas são escolhas
que devem responder à tarefa. O que ainda falta provar: descoberta do acesso à Central
pelo ícone; teclado virtual físico; leitor de tela e contraste formal; recuperação de
falhas; proteção completa de edição ao fechar/cancelar. A prévia bloqueia próximo
registro com edição pendente, mas ainda não cobre todas as saídas. A posição da lista
e os filtros no endereço ainda precisam da mesma disciplina quando implementados.


## Revisão integral de Gestor e Compras, sétima rodada

### Fronteira de preservação

Leitura confrontada com `origin/main` em `677f0e8ae` e com as fontes da worktree.
Referências: `operator-kit/app/app.config.ts`, `assets/css/operator-theme.css`,
`OperatorButton`, `OperatorMoreMenu`, `OperatorConfirmDialog`, `OperatorReadingCard`,
`OperatorSonner`, `docs/reference/operator-kitchen-sink.md` e os componentes dos apps.

| Preservar | Aplicação na proposta |
|---|---|
| Rail bronze | Desktop e menu mobile usam a cor de rail #8b6b2e; árvore em tela inteira conserva a identidade, com subitens leves |
| Conjunto mínimo de botões | Principal sólido, neutro outline/ghost e destrutivo error; adaptação ao espaço sem cortar significado |
| Badges soft | Estados com cores semânticas e texto, sem transformar badge em ação |
| Cards e tipografia | Tokens e respiro da suíte como referência; nenhuma nova identidade de componentes é aprovada pelo mock |
| Cinco receitas de overlay | Confirmação, formulário curto, workspace, detalhe e captura conservam propósitos distintos; cadastro longo deixa de caber numa caixa curta |
| Confirmação segura | Voltar/continuar editando recebe foco antes do ato sensível; erro mantém o rascunho |
| Fluxos atuais | A redistribuição conserva cadastros, estados, motivos, histórico, reversões, conversões e ações existentes |
| Core/orquestrador/projeções | Nenhuma alteração; preview não chama serviço de negócio |

Exceções explícitas pedidas nesta conversa: pontos verticais em vez da reticência
horizontal do OperatorMoreMenu atual; opções do registro e dispensar sem borda; ordem
filtro/busca/opções; ícone atual como acesso à Central; experimentação B desktop/árvore A
mobile; composição das barras. O kit não foi alterado para impor essas exceções.
A aparência estática é aproximação para avaliar composição, não um componente novo
canônico nem uma aprovação de substituição das primitivas reais.

### Correções funcionais da proposta

- Unificações volta a ser histórico com desfazer. Comparar duplicidade fica no cliente.
- Produto conserva Geral, Preço e config, Ingredientes e nutrição, Redes sociais,
  Fiscal e Vínculos, além do tabelão, histórico e Permitir compra.
- Cliente conserva cadastro, pedidos, endereços, preferências, fidelidade, edição,
  etiquetas, grupos e unificação. Grupos têm membros, duplicação e edição.
- Pedido conserva atendimento, motivo, saída/retirada, retorno, troco, maquininha,
  pagamento, fiscal, nota e ouvidoria na distribuição dos acessos.
- Canais conservam operação, pausa com duração/motivo, categorias e sincronização;
  rotinas conservam evidência e dupla conferência; postos conservam cadastro e desativação.
- Compras conserva pedido de compra/cancelamento, custo, fornecedor e unidade de compra.
- Receber conserva NF por chave, captura/foto, sem NF, item/vínculo/conversão/validade/
  volumes, diferença, ressalva, devolução e comprovante.
- Insumos conservam identificação, situação, conversões, fornecedores/custos, mínimos,
  duplicação, embalagem aberta e Permitir revenda; fornecedores conservam contatos e
  condições comerciais; CSV conserva acesso à revisão/importação e exportação do recorte.
- Contagem volta a mostrar o saldo do sistema e exige motivo da divergência, como no
  app atual. A contagem cega tinha sido uma alteração não autorizada e foi retirada.
  A revisão percorre os valores efetivamente digitados no formulário da amostra.

Os 56 exemplos têm fonte registrada no [inventário de cobertura](coverage.json).
Todo caminho de composição é acessível pelo roteiro. Funções contextuais também entram
nas opções da página ou do registro. Esse acesso de revisão não equivale a afirmar que
todas merecem o mesmo peso ou um menu enorme na implementação final.

### Estados, fidelidade e limites

O seletor do roteiro oferece normal, carregando, vazio, erro, sem permissão, sem conexão
e conflito; os links abrem telas limpas. `scenario=` só existe no protótipo. Erro fica
no topo, com Tentar novamente. Falhas de campo apontam o campo e mantêm o texto; conflito
e falta de conexão não fingem salvamento. Fechar um formulário alterado abre a decisão
de descartar, sem apagar o rascunho ao escolher Continuar editando.

Não se está reimplementando toda regra ou integração dos apps em JavaScript estático:
câmera/OCR, NF real, validação fiscal, estorno, contato externo, cotação de entrega,
permissão real, concorrência do servidor, saldo/ledger, upload e exportação real estão
fora. Os formulários mostram grupos de informação e decisões, com valores fictícios;
seletores remotos, relações complexas e validações profundas continuam sendo os dos
componentes existentes. Nenhuma redução de funcionalidade está autorizada. A futura
implementação, se aprovada, deverá compor esses componentes e serviços, não substituir
seus contratos pelos campos simplificados do protótipo.

Antes de implementar, a prova de não regressão deve cruzar rota/ação/permissão/estado
com o ledger canônico e testes dos apps. `coverage.json` registra fontes, não substitui
`operator-component-ledger.json`, não muda status pending de nenhuma superfície e não
é uma certificação de paridade funcional. Testes de dispositivo físico, leitor de tela,
teclado virtual e contraste formal continuam pendentes.


Passagem visual final: a lista de fornecedores passou a ter um alvo de navegação
consistente por linha, sem o botão Abrir cair em linhas diferentes. No Painel de
Compras, tarefas vêm antes das métricas e os atalhos de entrada com/sem NF substituem
a explicação sobre a organização do app. Badges permanecem ajustados ao texto, sem
virarem faixas de largura total. A instrução da contagem deixou de usar cor de aviso
para uma ação normal. A nota de conversão de farinha só aparece quando o item está
no recorte. Os ícones PWA reais de Gestor/Compras foram copiados sem alteração para
os assets da prévia; o gesto de voltar à Central pelo ícone já existe no OperatorRail.

A conferência com o main identificou quatro fontes de fluxo com alterações desde a
base da worktree. As diferenças de composição foram lidas: em particular, formulários
de insumo/fornecedor em papel quente com seções brancas foram refletidos nos exemplos.
O inventário registra hashes da worktree e de origin/main, sem reescrever os arquivos
reais. O mapa de cores de tempo de outra frente não foi modificado nem redefinido.


Ajuste solicitado durante a revisão: o botão do ícone de app compartilha o envelope
exato dos demais botões do cabeçalho (44 × 44 px no mobile; 32 × 32 px no desktop).
O PNG oficial acompanha o envelope, sem um segundo tamanho independente. O servidor
local agora envia Cache-Control no-store e assets versionados para evitar mistura de
rodadas; os links internos preservam a revisão.

As funções compartilhadas da suíte (sessão/trava, tema, confiança do dispositivo,
instalação, notificações, atalhos e capacidade/conexão) também são obrigações de
preservação do kit. A prévia de composição não reproduz esses runtimes nem autoriza
removê-los. Aparência estática e mensagens de estado não substituem seus contratos.

### Identidade e respiro no desktop

Correção do caso apontado pelo dono: quando o rail está visível, só ele mostra o ícone
do app, agora também como acesso funcional à Central. O cabeçalho mantém esse ícone
quando o rail não está na tela, como no mobile. O botão de compactar a lateral é uma
função distinta e permanece. O Painel de Compras mantém 24 px entre o bloco de tarefas/
atalhos e as métricas, além do padding externo; esses blocos não devem se encostar.

### Composição das ferramentas e posição da identidade no mobile

Experimentação solicitada: a identidade do app ancora o canto esquerdo; busca global
e menu do app ficam agrupados à direita. São funções distintas, com a mesma caixa de
toque e ordem DOM igual à visual. O ícone oficial e sua cor não foram redesenhados.

Filtro, busca e opções passam a ocupar uma faixa branca contínua, da mesma família
do rodapé fixo. A faixa acompanha a largura útil da área rolável, sem radius de card
ou sombra adicional. Ela continua rolando com o conteúdo; o pedido de uma superfície
coesa não vira automaticamente mais uma barra fixa no mobile. A ordem dos controles
permanece filtro → busca → opções. A composição usa os gutters da página nos três
perfis, sem encolher controles ou criar overflow.

## Rodada transversal: demais apps de operador

Entrada: `suite-review.html`. Central: `suite.html?app=hub&view=home`. Compartilha o mesmo servidor e túnel temporário das prévias anteriores. Arquivos independentes de `preview.js`, sem mudar as composições já aprovadas de Gestor/Compras.

Casos principais: PDV (inclusão, comanda, revisão do pagamento, caixa e fechamento); Cozinha (estações reais da casa, pronto/desfazer e Saída no Gestor); Produção (ciclo do lote, quantidade real, confirmação e ferramentas); Marketing (conteúdo/destino antes da autorização); B.I. (período, unidade, leitura detalhada e cenário). Os nomes de estações e registros são amostras, nunca um cadastro fixo proposto.

Foram consultadas as seções e os shells atuais dos apps, os componentes de Produção, a página de B.I. e as identidades oficiais. Cozinha escura preservada. No PDV, Fim do dia é corredor sem laterais/barra inferior, com retorno ao Caixa. Não há intenção de tornar todas as telas iguais: a segunda lateral só aparece quando há destinos no assunto; as barras contextuais dependem da tarefa.

**Limites:** rodada de validação transversal de navegação e anatomias representativas. Páginas auxiliares reservam composição e localização, com limitações na própria tela. Não substitui inventário exaustivo de cada funcionalidade ou seus componentes maduros. Sem API, dados reais, permissões, impressoras, câmera, pagamentos, envio de anúncios ou estoque. Período do B.I. demonstra contexto com valores estáticos; timers não correm. Receitas/configurações não foram reimplementadas nem consideradas aprovadas por esses exemplos parciais.

Evidência: `transverse-evidence.json`, capturas `transverse-<app>-mobile.jpg` e `transverse-<app>-desktop.jpg`. Geometria de 38 destinos em 320/390/1024 px; fluxos principais testados pelo navegador. Somente dados em memória.
