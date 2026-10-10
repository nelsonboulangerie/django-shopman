WP-OPERADOR-NUXTUI-ONDAS: planejar e coordenar a migração dos 8 apps de operador para Nuxt UI

MISSÃO
O Gestor (surfaces/orders-nuxt) é o molde canônico: Nuxt UI 4 tematizado uma vez no operator-kit. Faltam os outros 8 apps do surfaces/registry.json: Central, PDV, Cozinha, Produção, Marketing, Compras, B.I. e Kitchen Sink. Entregue o PLANO e a COORDENAÇÃO dessa migração. Você não migra os 8 apps nesta sessão. Você decide a ordem, o que sobe para o kit primeiro, como cada app migra sem perder gesto e quem roda o quê em paralelo. Depois executa a ONDA 0 e o PRIMEIRO APP PILOTO, para provar o método.

Regra de ouro: zero regressão funcional. Todo gesto que existe continua existindo, mesmo que mude de lugar. Expansão só quando for pertinente, e com o motivo escrito.

CRITÉRIO DE PRONTO DE CADA APP (o mesmo do Gestor, mais estes pontos)
1. 100% canônico: só componente oficial do Nuxt UI, tematizado no app.config.ts do kit. Nada de :ui= por instância, HTML cru, input nativo do sistema (type="date|time"), classe que imita componente, valor arbitrário sem motivo escrito ou primitiva paralela.
2. Omotenashi: a tela diz o que fazer e já traz a ação. Copy segundo o docs/reference/omotenashi-copy.md e o docs/reference/suite-vocabulary.md.
3. Herança: o que o app resolver e servir a outro sobe para o kit, nunca é copiado.
4. Zero regressão: inventário de gestos ANTES (main) conferido um por um DEPOIS, com arquivo:linha dos dois lados.
5. Visto em tela: antes e depois em 390, 768, 1024, 1280 e 1440 px, claro e escuro, com os diálogos e overlays abertos.
6. CI verde do app e dos vizinhos. Uma mudança no kit só sai com a CI de todos os apps verde.

O QUE A RODADA DO GESTOR ENSINOU (aplique, não redescubra)
Leia antes: docs/plans/WP-GESTOR-CANON-LAUDO.md (#1523) e os PRs #1518 a #1528.
- Mudança no kit quebrou 4 apps que ninguém abriu: o slot #below foi apagado (as abas de Ajustes do PDV sumiram), o OperatorLiveStatus virou "On/Off" e o período virou type="date". Regra: o kit muda por opt-in, com peça ou variante nova, até cada app migrar. Mudança de comportamento compartilhado só no PR que também migra ou confere todos os consumidores.
- Dublês de teste escritos à mão esconderam um 500: o NuxtSelect com value "" derrubava a página no navegador e passava no teste. Regra: dublê fiel ao componente real (lança onde o real lança) ou teste contra o Nuxt UI real. Nada é declarado pronto sem build de produção aberto no navegador.
- Trava que confere string cristaliza decisão. Quando a decisão muda, mude primeiro a decisão, depois a trava, com o motivo escrito no teste. Exceção à trava é nomeada e única.
- Componentes canônicos já escolhidos (usar, não reabrir):
  - data, hora e período: UiDateField, UiDateRangeField, UiTimeField, UiTimeRangeField e UiDateTimeField (camada fina sobre InputDate, InputTime e Calendar);
  - o menu ⋯: DropdownMenu;
  - aviso com prazo: OperatorUrgentAlert (origem, assunto, prazo, detalhe, ações; lembrete proporcional ao prazo);
  - toast: useToast no kit (o OperatorSonner morre);
  - destaque do item da vez: PageCard highlight, ou data-highlight no NuxtCard;
  - cartões com a altura do próprio conteúdo;
  - tabela integrada ao card.
- Hydration mismatch aparece em todas as telas, inclusive no main. Ataque no shell do kit, uma vez.
- Decisões abertas no laudo (UiNativeSelect ou NuxtSelect, Saída do celular, card dentro de card): confira o que o Pablo já respondeu antes de assumir.
- Quem recebe aviso é a pessoa logada, pelas permissões. O financeiro panorâmico (caixa, contagem, totais do dia) só o dono vê.

ENTREGÁVEIS
1. docs/plans/WP-OPERADOR-NUXTUI-ONDAS.md, com:
   - Inventário por app:
     - telas, gestos, atalhos e SSE;
     - peças do kit que usa;
     - componentes locais;
     - escapes do cânon com arquivo:linha;
     - testes e travas que vão quebrar;
     - mock visual disponível ou não.
   - Grafo de dependência kit para app: quais peças do kit cada app precisa já canônicas antes de migrar.
   - Ondas:
     - Onda 0, só kit: o que precisa estar canônico e opt-in antes de qualquer app. Candidatos:
       - shell e rail com NavigationMenu;
       - useToast no kit;
       - OperatorPageHeader com os slots que os 9 apps usam;
       - LiveStatus com os 4 tons;
       - período com os Ui*;
       - UiNativeSelect, UiButton e UiFilterChip;
       - hydration;
       - OperatorUrgentAlert montável em qualquer shell.
     - Ondas 1 a N: a ordem dos apps, justificada por risco, uso real no balcão e dependências. Sugestão a validar: B.I. e Compras (escritório, menos gesto de chão) antes de PDV e Cozinha (chão, toque, posto).
   - Por app (uma frente = um branch = um PR):
     - o que muda;
     - o que sobe para o kit;
     - a trava nova;
     - o critério visual de pronto;
     - o que roda em paralelo;
     - a estimativa em frentes.
   - Coordenação:
     - quem pode rodar ao mesmo tempo sem colidir no kit (mudança de kit é serial; migração de app é paralela);
     - a regra de empilhamento;
     - como cada sessão relata.
2. Executar a onda 0 em PRs pequenos. Cada PR prova em tela que os 9 apps continuam iguais ou melhores, com captura antes e depois de cada app tocado.
3. Migrar o app piloto escolhido no plano, com o inventário de gestos conferido e o laudo de regressão.
4. Um prompt pronto por app para as próximas sessões, neste mesmo formato, com o inventário do app embutido.

SEGURANÇA E ESTEIRA (o CLAUDE.md inteiro vale)
- Antes de começar:
  - rode make inflight, gh pr list e git worktree list;
  - não duplique frente que já tem dono;
  - #1518 a #1528 estão em rascunho e só saem dele com a palavra do Pablo.
- Worktree e branch:
  - worktree própria, sempre;
  - base no topo da pilha do Gestor enquanto ela não entrar no main, depois no main;
  - o título diz sobre o que está empilhado.
- Git:
  - git add só de arquivo nomeado;
  - sem git stash;
  - scratchpad com nome único por frente.
- Migração e contrato:
  - migração nova: confira colisão de numeração;
  - contrato TS: regere pelos export_*_schema (com DJANGO_DEBUG=true).
- Testes Python na worktree: .venv próprio (uv venv + make install) ou PYTHONPATH explícito.
- Retratos e baselines: não regere. Só quem tem o browser da CI.
- Fora de alcance sem a palavra do Pablo: alpha, produção, reseed, apagar branch alheio, tirar PR do rascunho.

MÉTODO: PROVA VEM DE TELA
- Build de produção de cada app contra o mock dele. Se o app não tem mock, criar o mock é a primeira frente do app: fixtures gravadas do seed, forma completa das projections. Mock incompleto esconde defeito (foi o caso do 500 no Gestor).
- Playwright nas 5 larguras, claro e escuro, com:
  - todos os diálogos;
  - os estados carregando, vazio, erro, offline e sessão expirada;
  - teclado e foco.
- Cada achado: arquivo:linha, captura, regra violada, severidade (P0 perde função ou mente ao operador; P1 fuga do cânon que se espalha; P2 polimento) e a correção nomeando o componente oficial.

RELATÓRIO NO CHAT EM FORMATO ELEVATOR PITCH (o Pablo não lê o MD)
- as ondas, uma linha cada;
- o que a onda 0 entregou e o que ela muda em cada app;
- o piloto: o que foi migrado, os gestos conferidos e o que expandiu;
- as decisões que são dele, cada uma respondível com "1", "2" ou "sim";
- o estado de cada frente (mergeado, na fila, PR vermelho com a causa, rascunho esperando decisão), com o número;
- o que NÃO foi verificado, com o nome e o motivo.

AS REGRAS MAIS VIOLADAS
- Não declare pronto sem ver. Separe sempre: implementado, testado, visto no navegador, pendente.
- Não afrouxe trava para passar. Corrija a decisão, depois o teste.
- Não mude o kit sem abrir os 9 apps.
