# Marketing V2 — baseline de paridade funcional

**Estado:** gate obrigatório para implementação e cutover  
**Base verificada:** `origin/main` em `207232c20`  
**Superfície:** `surfaces/marketing-nuxt` e contratos canônicos de Marketing

## Decisão

A V2 é uma expansão do Marketing atual, não uma substituição da operação por uma
prévia visual. A prévia navegável define direção de experiência; o app atual define
o piso funcional e operacional.

Uma tela pode mudar de lugar, nome ou composição. Uma capacidade só pode deixar de
existir quando houver decisão explícita de produto, migração dos dados e telemetria
que prove desuso. Ausência acidental na V2 é regressão.

Paridade é medida por comportamento, consequência e proteção — não por quantidade
de páginas nem por semelhança visual. A V2 pode condensar cinco telas em um wizard,
desde que preserve todos os resultados e estados acessíveis hoje.

## Baseline que a V2 deve preservar

| Domínio | Capacidades atuais obrigatórias | Tratamento na V2 |
| --- | --- | --- |
| Acesso e casco | sessão de operador, `shop.view_marketing`, estados checking/expired/forbidden/offline, lock, retorno ao Hub, navegação, notificações e PWA | Reutilizar o casco e os componentes do `operator-kit`; nenhum atalho de preview contorna o gate |
| Painel | pendências e recentes, atualidade dos dados, limites de alcance, contadores separados entre pessoas e postagens, atualização manual | Reorganizar visualmente sem fundir grandezas nem esconder degradação |
| Revisão | editar conteúdo antes da decisão, prévia por formato, assistência de texto quando permitida, aprovar agora, agendar, recusar com motivo, retomar após reautenticação | O wizard desemboca na mesma decisão e nos mesmos Actions do servidor |
| Campanhas | listar, buscar, filtrar, paginar, criar, editar, ligar/desligar e acionar manualmente | Evoluir campanha para plano + destinos + composições, mantendo leitura e operação das campanhas existentes |
| Público | regras, tags, faixas, segmentos, produtos/ofertas, contagem viva, deduplicação, consentimento, janela silenciosa e limites | Público continua server-owned; composição multiplataforma não relaxa consentimento nem elegibilidade |
| Modelos | listar, criar, editar, excluir protegido por dependência, variáveis e variantes por plataforma | Preservar modelos existentes e acrescentar schemas por destino/formato |
| Plataformas | prontidão, bloqueio/degradação, configuração do WhatsApp, catálogo de templates/flows, avisos automáticos e teste seguro | Evoluir para conexões múltiplas e discovery; manter configuração/teste atuais durante a ponte |
| Histórico | filtros, paginação por cursor, resultado agregado e por plataforma, detalhes de anúncio e receipts | Evoluir para conjunto/destino/veiculação sem perder histórico legado |
| Recuperação | cancelar/reagendar quando permitido, repetir somente falha segura, reconciliar `unknown` sem reenvio e acompanhar estado até estabilizar | Reusar Actions, idempotência, outbox, ledger e reconciler atuais |
| Segurança operacional | capabilities por ação, CAS/versionamento, confirmação proporcional à consequência, step-up, duplo controle, freeze, quotas e idempotency keys | Nenhuma ação V2 infere permissão ou transição no cliente; tudo vem resolvido pelo servidor |
| Integridade de rascunho | autosave local, dono do rascunho, conflito, recuperação após expiração de sessão e limpeza após receipt | Migrar de forma compatível antes de retirar o editor atual |

Fontes factuais do baseline:

- rotas e componentes em `surfaces/marketing-nuxt/app`;
- projeções e Actions em `shopman/backstage/projections`;
- API em `shopman/backstage/api/marketing.py`;
- contrato em `docs/reference/marketing-surface-contract.md`;
- cliente gerado em `surfaces/marketing-nuxt/app/generated/marketingClient.ts`.

## Expansões esperadas

A paridade acima é somente o piso. A V2 acrescenta, incrementalmente:

1. uma intenção comum com destinos concretos por conta, plataforma e formato;
2. duas ou mais composições da mesma plataforma na mesma campanha;
3. opções específicas somente quando o destino as suporta;
4. previews com proporção, corte e conteúdo do artefato que será veiculado;
5. múltiplas Pages, contas e locations conectadas;
6. mídia rica e formatos adicionais liberados adapter por adapter;
7. promoções e cupons com lifecycle, ledger e resgate auditáveis;
8. resultado e recuperação independentes por veiculação;
9. catálogo teórico visível para planejamento, sem transformar capacidade não
   implementada em opção executável;
10. TikTok somente depois de conexão aprovada, sandbox proof e revisão da
    plataforma; até lá, no máximo handoff explicitamente não executável.

## Regra para generalização

Um campo entra na etapa comum somente quando todas as plataformas selecionadas
compartilham a mesma semântica. Caso contrário, ele pertence à composição do destino.

Exemplos:

- objetivo, promoção, mensagem-base, ativos e janela desejada podem ser comuns;
- `Atualização`, `Evento` e `Oferta` pertencem ao Google;
- CTA do Google pertence ao formato Google e não é inventado para Instagram;
- template, variáveis e botões aprovados pertencem ao WhatsApp;
- capa, carrossel, Reel e Story pertencem aos formatos elegíveis da conta Meta.

Adaptação automática só é permitida quando for reversível, explícita na revisão e
não mudar a consequência. Nunca é permitido “dar um jeito” silencioso no adapter.

## Estratégia de integração sem regressão

1. A V1 permanece o caminho padrão e plenamente funcional.
2. A V2 nasce autenticada dentro de `marketing-nuxt`, usando o mesmo casco.
3. Primeiro, a V2 lê as projeções canônicas e compara resultado sem efeito externo.
4. Cada escrita é liberada por capacidade/destino reutilizando o Action, comando,
   confirmação, receipt e idempotência atuais.
5. Funcionalidade ainda não portada abre o fluxo atual no mesmo app; não desaparece.
6. A flag/coorte seleciona experiência, nunca concede autorização.
7. O kill switch volta para a V1 sem cancelar nem duplicar comandos em voo.
8. A V1 só pode ser removida depois de a matriz abaixo estar verde e de a janela de
   rollback terminar.

## Matriz de aceite do cutover

Cada linha recebe evidência automatizada e operacional. `Pendente` não bloqueia o
desenvolvimento da V2; bloqueia torná-la padrão ou remover a V1.

| Jornada | Prova mínima | Estado inicial |
| --- | --- | --- |
| Abrir o app e respeitar acesso | testes de sessão/capability + smoke autenticado | Compartilhada por `/` e `/v2` |
| Criar e editar campanha | component/e2e contra contrato real | Pendente na V2 |
| Ligar/desligar campanha | teste de Action e CAS | Pendente na V2 |
| Acionar campanha para revisão | receipt único e nenhum efeito no `fire` | Pendente na V2 |
| Revisar, editar, aprovar, agendar e rejeitar | matriz por modo e cerimônia | Painel compartilhado; matriz completa pendente |
| Configurar e testar plataforma | capability + teste seguro por conector | Pendente na V2 |
| Criar/editar/excluir modelo | CRUD e dependência protegida | Pendente na V2 |
| Consultar histórico e detalhe | cursor, legado e resultado por destino | Pendente na V2 |
| Recuperar falha/`unknown` | retry seguro e reconcile sem reenvio | Pendente na V2 |
| Retomar rascunho/sessão | conflito, expiração e owner boundary | Pendente na V2 |
| Operar cada formato novo | golden contract + sandbox proof + canário | Pendente por formato |
| Promoção/cupom | concorrência, reserva, aplicação, estorno e auditoria | Pendente |

## Gate de PR para cada fatia V2

Todo PR da V2 deve declarar:

- qual linha da matriz preserva ou expande;
- quais rotas, contratos e efeitos externos toca;
- qual fluxo atual continua disponível durante a convivência;
- se há nova capacidade teórica ou nova capacidade executável;
- como provar que não houve ampliação de permissão;
- como desligar a fatia sem perder rascunho, comando ou receipt;
- evidência de lint, typecheck, testes, build e, quando visual, viewport mobile e
  desktop.

É proibido aprovar um PR cuja única evidência seja a fidelidade à prévia estática.

## Área assumida nesta entrega

Somente documentação de produto/arquitetura:

- este baseline de paridade;
- referência a ele no plano do Capability Composer.

Não há mudança de runtime, API, migration, adapter, configuração, lockfile ou deploy.
