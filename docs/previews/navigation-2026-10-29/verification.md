# Verificação das prévias de navegação

Data: 29/10/2026. Escopo: protótipo local, sem execução dos apps ou escrita em APIs.

## Evidência de interação

A verificação no navegador percorreu os destinos abaixo, nas duas variantes. Em cada
seleção, o título esperado ficou visível nos dois quadros da comparação.

| App | Destinos conferidos |
|---|---|
| Gestor | Em andamento, Saída, Histórico de pedidos, Catálogo, Coleções, Clientes, Grupos de clientes, Unificações, Canais de venda, Catálogo por canal, Rotinas da loja, Postos de trabalho |
| Compras | Visão geral, Reposição, Fornecedores, Custos de compra, Conferência de recebimento, Divergências no recebimento, Insumos, Contagem de estoque |

Outros ensaios e resultados observados:

| Gesto | Resultado observado |
|---|---|
| Compactar a primária no Gestor B | Largura de 76 px, mantendo contextual de 218 px |
| Recolher contextual com primária compacta | Contextual oculta e controle Mostrar opções de Produtos disponível |
| Alternar A/B em Catálogo | Destino e dados mantidos |
| Navegar em um quadro da comparação | Outro quadro muda para o mesmo destino |
| Buscar Geleia, abrir produto, atravessar para Compras | Insumos mostra o mesmo SKU e oferece retorno ao produto |
| Retornar pelo cabeçalho | Detalhe Geleia de frutas vermelhas reaberto e busca Geleia preservada |
| Entrar na Central pelo nome do app e retomar | Central de apps visível; retorno para Divergências no recebimento |
| Navegação rápida móvel → Pedidos → Em andamento | Destino aberto e gaveta fechada |
| Voltar pelo navegador | Catálogo restaurado após sair para Em andamento |
| Resolver falta de manteiga com recebimento parcial | Confirmar entrada passa a estar habilitado; valor recebido continua R$ 1.156,00 |
| Abrir gaveta móvel em dois níveis | Primeiro assuntos, depois destinos, com Todos os assuntos como retorno |
| Abrir gaveta A | Grupos e destinos na mesma árvore |
| Abrir gaveta ou diálogo de detalhe | Fundo inerte; foco na camada aberta |

O recebimento é fictício. Nenhum gesto acima cria entrada, cobrança, cadastro, pedido
ou movimento real. As simulações existem para avaliar a navegação e a consequência
visível das escolhas.

## Perfis observados

As medidas abaixo foram lidas do navegador, não inferidas do nome da captura.

| Perfil | Resultado |
|---|---|
| 390 × 844 | Navegação inferior presente; gaveta em etapas ou árvore; cards de recebimento; largura da página sem transbordamento horizontal |
| 768 × 1024 | Barra lateral permanente oculta e navegação inferior visível; Contagem acessível pela gaveta |
| 1280 × 720 | Conferência B sem transbordamento da página ou tabela; resumo reorganizado em uma coluna, largura observada de 805 px |
| 1024 × 768 | Primária compacta de 76 px; contextual independente; sem transbordamento horizontal da página, da navegação ou da tabela |
| 1440 × 900 | Tabelas e barras laterais disponíveis; Conferência B com resumo ao lado; sem transbordamento horizontal da página ou tabela |

Capturas desktop: 1440 × 900. Capturas móveis: 390 × 844. Nenhuma baseline de CI foi
gerada ou alterada. Zoom de 200% continua fora desta rodada de verificação; não se afirma aprovação
nesse perfil.

## Verificação estática

- `node --check docs/previews/navigation-2026-10-29/preview.js`: sem erro de sintaxe.
- `git diff --check`: sem erro de whitespace.
- `python3 scripts/check_docs_governance.py`: verificação documental aprovada.
- O script não contém fetch, XHR, WebSocket, beacon ou armazenamento persistente.
- Os únicos recursos carregados pela prévia são locais, incluindo a fonte já usada
  pelo projeto. `connect-src 'none'` impede chamadas de dados.
- Arquivos alterados restritos a documentação e `docs/previews/navigation-2026-10-29/`.

Durante a observação dos quadros, a ferramenta de navegador registrou um erro de
`MutationObserver` sem identificar origem no log retornado. O script da prévia não usa
essa API. As interações acima concluíram; este registro não declara o console inteiro
livre de erros nem atribui a causa sem stack. A verificação funcional documentada é
do protótipo, não uma certificação dos apps Nuxt.

## Segunda rodada: atalhos e composição

Conferido no navegador após a revisão das barras:

- Mobile 390 × 844: os seis atalhos de destino da tabela do README foram acionados
  individualmente nas duas variantes. Cada toque abriu o título esperado, com
  `data-drawer=false`. Não houve etapa adicional em B.
- Desktop 1440 × 900 com `quick=1`: repetido o mesmo percurso dos seis atalhos nas
  duas variantes, com os mesmos títulos.
- Composição no celular: mover recortes para baixo ocultou a faixa superior e
  manteve exatamente três controles de filtro, sem duplicação.
- Catálogo: próxima página mudou de 1–6 de 9 para 7–9 de 9 produtos.
- Comparação: os dois iframes receberam `local=bottom` e `quick=1` na configuração.
- Recebimento: resolver a diferença mudou a ação flutuante para Confirmar entrada.
  No desktop padrão, a mesma decisão atualizou a ação do cabeçalho; dock oculto.
- Troca Gestor → Compras pelo cabeçalho abriu Conferência de recebimento. Retorno
  à Central pelo mesmo controle exibiu a Central e seus apps.
- Mobile 320 × 740: largura observada 320, sem transbordamento da página; conteúdo
  rolável com 252 px no estado inicial de Contagem. Ao editar uma quantidade, dock
  oculto e foco preservado no campo. Ao sair, Revisar contagem habilitado e progresso
  de 1 de 6 insumos. Ajustada a posição do estado Registrado para não disputar espaço
  com o nome do insumo.
- Mobile 390 × 844 e desktop 1440 × 900: conteúdo, ação contextual e atalhos ocupam
  regiões sucessivas em fluxo, sem sobreposição fixa.

As capturas individuais de A/B e de Compras mobile foram atualizadas. As capturas
anteriores de comparação e de Central registram a primeira rodada. Não foi executado
ensaio em dispositivo físico com teclado virtual, leitor de tela ou zoom de 200%.
Os perfis tablet da seção anterior pertencem à primeira rodada, sem revalidação nesta.

## Modo sem controles do laboratório

No perfil 390 × 844, `clean=1` resultou em laboratório com display none, aplicação
iniciando em y=0 e conteúdo rolável de 501 px na Conferência. O toque em Reposição
preservou `clean=1` na URL. Captura: `captures/compras-mobile-clean.jpg`.
O script atualizado também foi obtido com sucesso pelo túnel público temporário.

## Estado de aprovação

Prévia entregue para avaliação do dono. Não há preferência aprovada entre A e B.
Implementação e deploy continuam dependendo de autorização explícita posterior.

## Terceira rodada: ferramentas de lista e registro

No mobile 390 × 844:

- Coleção Viennoiseries aplicada: três produtos. Maior preço ordenou Brioche (22),
  Pain au Chocolat (15,50), Croissant (13), em reais.
- Abrir Brioche e próximo: Pain au Chocolat, posição 2 de 3, respeitando filtro e ordem.
- Preço zero e salvar: mensagem vermelha no topo do detalhe com role alert.
- Edição pendente e próximo: aviso de alterações; mesmo registro permanece aberto.
- Preço válido e salvar: confirmação no topo da lista; fechamento manual disponível.
- Limpar filtro e ordenar por nome: nove produtos. Próxima página: 7–9 de 9.
  Esgotados: primeira e única página, um produto.
- Capturas catalog-controls-mobile.jpg e product-error-mobile.jpg.

No desktop 1440 × 900: página sem transbordamento horizontal; conteúdo termina em
852 px, rodapé começa em 852 e termina em 900. Filtro, ordenação e registro seguinte
repetidos com o mesmo resultado. Captura catalog-controls-desktop.jpg.
A rodada não revalida todos os destinos nem implementa o painel completo de filtros,
ações em lote, retenção de filtros no endereço ou proteção completa ao fechar edição.

## Quarta rodada: composição responsiva, vistas e opções

- `layout=adaptive`: mesma aba em 1440 × 900 mostrou variante double; em 390 × 844
  e 320 × 740 mostrou single. Gaveta mobile exibiu grupos e filhos na mesma árvore.
- 390 px: cabeçalho sem laboratório, com Central explícita, troca de app, busca de
  destinos e título. Toolbar de catálogo com 95 px após composição em duas linhas.
- Grade e lista alternam sobre os mesmos dados. Filtro Viennoiseries + maior preço
  manteve três resultados e Brioche primeiro ao mudar a representação.
- Compacta aplicada nas opções: dataset compact preservado ao recarregar, junto com
  display grid na URL. No desktop, confortável produziu linha de tabela de 65 px.
- Opções de Brioche → Disponibilidade nos canais: detalhe Canais de Brioche.
- Escape no popover fechou a camada e o foco voltou a Mais opções do catálogo.
- Central direta exibiu Central de apps; Voltar a Gestor preservou layout adaptativo,
  representação e densidade no endereço.
- 1440 px: largura da página 1440, sem transbordamento; rodapé entre y=842 e y=900,
  abaixo do conteúdo. 320 px: página e cabeçalho com largura 320, conteúdo rolável
  de 460 px no Catálogo; sem transbordamento horizontal da página.
- Compras mobile: flutuante com Nota 004821 / Resolver diferença; toque Reposição
  abriu Reposição diretamente e gaveta continuou fechada.

Capturas: adaptive-grid-mobile.jpg, adaptive-list-desktop.jpg,
adaptive-record-footer-mobile.jpg e adaptive-receiving-mobile.jpg.
Os cenários da matriz de decisão não foram todos prototipados ou revalidados nesta
rodada. Sem testes dos apps, Core, baselines ou deploy.

## Quinta rodada: correção a partir do celular

- Auditoria DOM dos 20 destinos em 320 × 740: largura da página 320 em todos;
  nenhum botão visível com classe button transbordou sua caixa horizontalmente.
  Essa verificação não equivale a aprovação visual integral dos 20 destinos.
- Inspeção visual do Catálogo em 320 e 390 px; toolbar em uma única linha de 44 px,
  contra os 95 px medidos na quarta rodada em 390. Preço, saldo e situação preservados.
- Filtrar/ordenar → Maior preço → Aplicar: contagem mostra 9 produtos · Maior preço.
- Opções → Grade: seis cards na página. Lista/grade e densidade acessíveis pelo popover
  no mobile. Não há o seletor duplicado permanente de apresentação.
- Recebimento inspecionado em 320 e 390: nota e aviso reorganizados; opções da página
  mostram Ler outra nota. Escape fecha a camada.
- Caixa externa de ação primária com 44 px em 320. Toolbar 44 px; clientHeight dos
  botões 42 px mais bordas de 1 px em cada lado, total externo de 44 px.
- Desktop 1440 × 900 conferido depois: variante double, sort e vista explícitos;
  alternar grade produziu seis cards; largura da página sem transbordamento.

Capturas atuais: mobile-first-catalog-320.jpg, mobile-first-catalog-390.jpg e
mobile-first-receiving-390.jpg. Sem validação em dispositivo físico ou afirmação de
que todos os fluxos de produto foram aprovados.

## Sexta rodada: hierarquia e família visual

- Em 320 px, ordem DOM e visual da toolbar: Filtrar e ordenar produtos, Buscar produto,
  Mais opções do catálogo. Largura da página 320; borda computada das opções do registro
  transparente. Três pontos verticais no SVG compartilhado.
- Menu mobile inspecionado em 390 px: largura total; grupos e filhos juntos; destino
  atual selecionado; fechamento sem borda. Captura polish-navigation-mobile.jpg.
- Ícone Compras no cabeçalho → Central de apps; Voltar a Compras retoma a tela.
  O antigo link limpo com variant=single também exibiu o cabeçalho consolidado.
- Busca global → contagem: grupo Compras e destino Contagem / Estoque. Enter abriu
  Contagem de estoque no outro app. Consulta zzzz exibiu o estado vazio.
- Diálogo de busca com clientHeight=scrollHeight=818 em 390 × 844, sem rolagem externa;
  resultados com área própria 640 px e conteúdo rolável 1278 px.
- Escape com texto no campo fechou a busca em um acionamento; foco retornou ao botão
  Buscar destino na suíte. Campo inicialmente focado; fundo do diálogo nativo inerte.
- Filtro inspecionado em 320 px; form de Brioche inspecionado com campos e rodapé de
  navegação/ações e fechamento discreto. Capturas polish-form-mobile.jpg e
  polish-search-mobile.jpg. Demais overlays herdam a família, sem afirmar inspeção
  individual de todos os estados de erro/permissão.

Ajuste final da busca: painel ancorado ao alto e altura pelo conteúdo. Em 390 × 844,
a altura passou de 816 px (lista completa) para 292 px (Contagem), com o campo no
mesmo y=107 nos dois estados; clientHeight e scrollHeight iguais. No desktop 1440,
a busca teve 796 px sem rolagem externa. Captura polish-search-mobile.jpg atualizada.

## Sétima rodada: revisão integral e preservação

Escopo: composição estática dos dois apps, com fontes reais como referência. Não é
execução dos apps Nuxt, do BFF ou dos serviços. Não altera o ledger canônico.

Fontes confrontadas: app.config.ts, operator-theme.css, OperatorButton, OperatorMoreMenu,
OperatorConfirmDialog, OperatorReadingCard e OperatorSonner; 32 arquivos de origem dos
56 exemplos registrados em coverage.json. Hashes da worktree e de origin/main estão
registrados; quatro arquivos de Compras divergiam e suas alterações de composição
foram consultadas. Assets PWA foram copiados byte a byte, sem redesenho.

### Matriz final, após corrigir cache do servidor

- 320 × 740: 20 telas × 7 estados = 140 visitas. Título e conteúdo presentes; sem
  transbordamento horizontal de página ou dos botões verificados.
- 320 × 740: 56 fluxos, com 78 casos de abertura/seleção de seção. Diálogo aberto;
  corpo e rodapé sem transbordamento horizontal na medição final.
- 390 × 844: 20 telas e 56 fluxos = 76 visitas; página e corpo sem overflow horizontal.
- 1440 × 900: os mesmos 76 exemplos, sem overflow horizontal da página/corpo.
- Passagem visual nas 20 capturas mobile: corrigidos fornecedores com ações em linhas
  variáveis, prioridade do painel de Compras, badges esticados, instrução de contagem
  indevidamente tratada como aviso e nota de conversão fora do recorte.
- Logs de erro retornados pela ferramenta na observação final: lista vazia. Isso não
  redefine o registro histórico de instrumentação nas rodadas anteriores.

Evidência por caso em review-evidence.json. As medidas demonstram a geometria visitada,
não certificam a completude de domínio, contraste ou acessibilidade de todo o produto.

### Interações percorridas

- Produto: visitar Fiscal, voltar ao Geral e alterar nome; fechar → Continuar editando
  preserva o valor; fechar → Descartar fecha o formulário. Salvar válido confirma a
  operação local. Navegação de seções não apaga os campos.
- Recusar pedido: motivo vazio aponta campo e aviso no topo. Motivo preenchido abre
  confirmação, com foco em Voltar à revisão e ato destrutivo na cor error; voltar
  preserva o texto.
- Conflito no produto: tentar salvar mantém o rascunho e retorna mensagem de conflito.
- Contagem: motivo ausente bloqueia revisão; quantidade 10 kg frente a 18 kg no sistema
  com motivo preenchido aparece na revisão; confirmação chega ao resultado local.
- Histórico de unificações: Desfazer → revisão → confirmação atualiza a amostra para
  Desfeita e desabilita a repetição da mesma ação.
- Rotinas: preencher evidência e confirmar atualiza 1 de 4 feitas.
- Recebimento: resolver diferença altera a próxima ação para Confirmar entrada.
- Menu: largura mobile completa e bronze rgb(139,107,46); os subitens continuam na árvore.

O teste de transições encontrou e corrigiu uma colisão de atributo entre identificação
do diálogo e acionadores de fluxo. Também foi detectado cache de scripts misturando
rodadas. A validação final usou assets v=20261029-7b, URLs revision=7b e servidor com
Cache-Control no-store. Os resultados anteriores a essa correção não são usados como
substitutos desta matriz final.

### Ajuste de tamanho solicitado durante a revisão

icon-size-evidence.json: no mobile 390, menu, app Gestor e busca mediram 44 × 44 px;
no desktop 1440, compactação, app Compras e busca mediram 32 × 32 px. Mesmo envelope
por cabeçalho, sem um tamanho independente para o PNG.

Capturas finais: complete-<app>-<view>-mobile.jpg para as 20 telas;
complete-bronze-navigation-mobile.jpg, complete-product-workspace-mobile.jpg,
complete-field-error-mobile.jpg e complete-confirmation-mobile.jpg. Galeria no roteiro.

Integrações, permissões reais, servidor concorrente, validação fiscal, câmera, uploads,
comunicação externa, estoque e pagamentos não foram executados. Nenhum fluxo está
aprovado para substituição dos componentes maduros pelo esquema estático destes mocks.

## Correção de duplicidade no desktop

- Caso reproduzido em 870 × 548: apenas um ícone de app visível; conteúdo com padding
  horizontal de 20 px e página sem transbordamento (largura 870). Ícone do rail abriu
  Central e o retorno retomou Compras.
- Desktop 1440 × 900: um ícone de app visível; padding 22px 26px 40px no conteúdo;
  distância medida de 24 px entre o split de tarefas/atalhos e as métricas.
- Mobile 390 × 844: rail fora da tela e ícone do cabeçalho presente. Abrir menu →
  Central → Voltar a Compras retorna à página com gaveta fechada.
- Captura desktop-identity-spacing.jpg. Correção somente na prévia.

## Faixa de ferramentas e ancoragem mobile

- 320 × 740: ícone do app em x=15, busca global em x=209 e menu em x=261; todos com
  44 px. Ordem dos controles no DOM corresponde à visual.
- Fundo computado da toolbar e do rodapé: rgb(255,255,255). Faixa de ferramentas com
  61 px incluindo respiro e borda; antes ocupava o conteúdo com padding superior,
  portanto não foi acrescentada uma segunda faixa fixa à área de trabalho.
- As 20 telas foram revisitadas em 320 px: página e conteúdo sem overflow horizontal.
- Abrir/fechar o menu continua operante após mudar seu posicionamento.
- Galeria mobile atualizada para refletir o cabeçalho reposicionado e a nova faixa.
