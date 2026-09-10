# Verificação manual E2E — Marketing — 2026-09-09

Estado: **em execução no simulador local hermético**.

Gate MKT-044: **confirmado pelo operador não autor em 2026-09-10**, após o pacote
canônico fechar 19 testes backend e 4 testes BFF. A aprovação é local/técnica e não
autoriza produção, deploy, provider externo ou rollout.

## Regras de avaliação

1. Contratos, consentimento, autorização, CAS, confirmação e fail-closed não
   podem ser reduzidos para melhorar a experiência.
2. Em seguida, o operador deve concluir a tarefa com o mínimo de memória,
   navegação, redigitação, espera, conferência externa e incerteza.
3. UI normal é pt-BR. Termos internos em inglês (`receipt`, `announcement`,
   `ledger`, `target`, `attempt`, `outbox`, `flow`) só permanecem quando forem
   identificadores técnicos necessários e acompanhados de explicação clara.
4. Cada ensaio registra resultado funcional e custo operacional. “Seguro, mas
   trabalhoso” é achado de UX, não aceite automático.
5. Nenhum ensaio usa provider, pessoa, credencial ou ambiente externo.

## Matriz viva

| Fluxo | Estado | Evidência | Atrito/achado |
|---|---|---|---|
| Login local `admin/admin` | passou | sessão autenticada na UI | credencial é apenas do seed local |
| Toggle de campanha | passou após correção | hit target 44×44 e pill 36×20; teste automatizado | pill era esticado pela regra global de acessibilidade |
| Configurar fluxo do WhatsApp | passou após correção de linguagem | catálogo local → CAS → confirmação → TOTP → auditoria | “flow”, “template” e “sandbox” foram substituídos na UI por fluxo, modelo e ambiente de teste |
| Aprovar Instagram | passou | 1/1 confirmado, agregado `succeeded` | UI mostra anúncio, comprovante e estado “concluído”; códigos permanecem só no contrato técnico |
| Aprovar Instagram + WhatsApp | passou | 2 outboxes, 13/13 targets/attempts confirmados | sem Redis local, atualização entre processos depende de poll/recarga |
| Bypass noturno local | passou | aviso visível; testes provam que flags isoladas não liberam | restrito ao adapter `SIMULATION_ONLY` |
| Diagnóstico do receipt | passou | `result=OK`, `provider_calls=0`, `pii=false` | comando técnico pode manter vocabulário interno; UI não |
| Disparo manual na tela Campanhas | bloqueado com honestidade após correção | Action canônica desabilitada com `command_not_available`; nenhum formulário ou POST é aberto | continua lacuna técnica: exige versão/CAS, idempotência, confirmação vinculada e comprovante antes de ser habilitado |
| Recusa com motivo | passou após correção de apresentação | anúncio 2 recusado por Admin, com motivo visível e sem outbox | resultado diz “Anúncio recusado”, não oferece cancelamento nem cartões 0/0 |
| Agendamento e confirmação | passou | anúncio 5 agendado para 20:40 BRT; resumo mostrou data absoluta e UTC−03 | sugestão inicial permaneceu em 08:00 após retirar WhatsApp; revisar derivação reativa |
| Cancelamento antes do limite | passou após correção | motivo → consequência de 12 destinos → confirmação; receipt `16a4d28c-e73b-49f2-9960-6f8f63c4ff4f`; outbox Instagram cancelado, zero targets | UI não coletava o motivo obrigatório e repetia erro; corrigido sem remover o gate |
| Recuperação de rascunho | passou | texto e hashtags sobreviveram à recarga, com hora do salvamento; descarte restaurou o servidor | 0 redigitações, 0 navegações e 1 clique para descartar |
| Conflito de versão/CAS | passou após correção de UX | abas A/B: recusa v1→v2 venceu; aprovação antiga ficou `conflict`; zero outbox/targets | diálogo inválido ficava aberto; agora fecha e abre o resultado canônico |
| Sessão expirada e retomada | passou | sessão removida entre challenge e step-up; login → nova confirmação → 13/13 confirmados | intenção preservada, token antigo descartado, zero redigitação editorial |
| Criação/edição de campanha e modelo | passou após correção de linguagem | campanha QA criada, editada, desligada/religada; modelo criado e editado por variável | formulário usa anúncio/não voltar e botões de variável em pt-BR; tokens técnicos ficam restritos ao corpo editável |
| Exclusão de modelo em uso | passou após correção de omotenashi | “Saiu do forno” preservado; dependências “E2E local…” e “Fornada pronta” aparecem antes da ação | botão destrutivo some quando há dependência e há atalho “Ver campanhas” |
| Estados parcial/incerto/reconciliação | passou após correção | fixture: 11 confirmados + 1 falha repetível + 1 incerto; retry chamou só 1; lookup resolveu só 1 | worker bloqueava retry de anúncio encerrado; simulador não processava lookup |
| Alerta, assunção, deep-link e resolução | passou | visto → assumido sem sumir → `/announcements/1#review` → recusa resolveu badge 1→0 | ação e contexto permaneceram na mesma superfície |
| Repetição E2E após revisão pt-BR | passou | anúncio 9 → confirmação de 12 destinos/2 plataformas → Instagram 1/1 + WhatsApp 12/12; comprovante `c976843d-3e4a-494b-a55b-65e9fc8b002f` | 3 ações significativas; uma recarga local por ausência de Redis; zero navegação externa ou identificador copiado |
| Histórico após conclusão | passou no MKT-045 | anúncio 9 aparece “Entrega concluída”, Instagram 1/1 + WhatsApp 12/12 e “Ver resultado”; filtro WhatsApp reduz 5→3 e persiste no reload | v2/ledger é a fonte; CTA de resolução só existe com Action contextual habilitada |

## Achado transversal de omotenashi

A segurança técnica avançou mais que a ergonomia. O produto já impede vários
efeitos perigosos corretamente, mas ainda transfere conceitos internos e etapas
de preparação ao operador. O critério para a rodada de UX será reduzir e provar:

- entradas e redigitações;
- navegações entre Campanhas, Painel e Plataformas;
- decisões que podem ser derivadas com segurança;
- tempo sem feedback e necessidade de recarga;
- conferências fora da própria tela;
- termos internos que o operador precisa memorizar;
- ações visíveis que estão indisponíveis ou contidas no backend.

O relatório será atualizado durante os ensaios. Correções não poderão esconder
ou contornar gates; devem explicar o gate, preservar o trabalho já feito e indicar
o próximo gesto seguro.

### Resultado da primeira rodada de redução de esforço

| Situação observada | Antes | Depois comprovado no navegador |
|---|---|---|
| Decisão recusada | leitura falsa de entrega ainda não iniciada + cartões 0/0 | estado terminal correto, sem próxima ação impossível |
| Identificar operação concluída | `Receipt` + estado cru `completed`/`succeeded` | “Comprovante” + “concluído”, no mesmo contexto |
| Encontrar variável de modelo | interpretar/memorizar `store_name`, `product_name` etc. | botões e lista usam “Nome da loja”, “Nome do produto” etc.; 1 clique insere o token correto |
| Tentar disparo manual contido | abrir painel, preencher e receber 409 | zero preenchimento e zero POST; Action do servidor desabilita a promessa |
| Descobrir por que um modelo não apaga | confirmar exclusão e interpretar toast genérico | 1 clique mostra nomes das campanhas e atalho para corrigi-las; exclusão não é oferecida |

Isso melhora tarefas reais sem reduzir autorização ou consequência. A lacuna do
disparo manual não foi maquiada: permaneceu indisponível porque ainda não possui o
contrato completo exigido pelo próprio plano.

## Evidência: recusa, agendamento e cancelamento

- Recusa: o anúncio 2 foi recusado com o motivo “Ensaio local: validar recusa
  sem envio”. A decisão, o ator e o motivo reapareceram após a atualização.
- Agendamento: o anúncio 5 foi aprovado para 9 de setembro de 2026 às 20:40,
  com fuso `America/Sao_Paulo` explícito e uma única faixa Instagram.
- Cancelamento: a primeira versão da UI chamou o comando sem o campo obrigatório
  `reason`; o backend recusou corretamente, mas o diálogo não oferecia entrada e
  “Tentar de novo” repetia a mesma requisição inválida.
- Correção: o diálogo agora coleta “Motivo do cancelamento” antes de consultar a
  consequência. O mesmo motivo, versão e chave de idempotência acompanham a
  abertura e o consumo da confirmação.
- Ensaio após correção: a consequência do servidor mostrou 12 destinos e
  Instagram; a confirmação levou o anúncio à versão 3, cancelou uma faixa ainda
  reversível e materializou zero destinos. O ledger manteve a outbox em
  `cancelled`, sem `dispatched_at`.
- Custo operacional observado no cancelamento: 2 cliques, 1 texto livre, nenhuma
  navegação externa, nenhuma redigitação, consequência conferível no próprio
  diálogo e confirmação final inequívoca.

## Evidência: recuperação de rascunho

- No anúncio pendente, o operador trocou o texto por “Rascunho E2E preservado —
  não publicar” e as hashtags por `#ensaio-local`.
- Após recarregar a página, ambos reapareceram automaticamente e o cartão informou
  “Rascunho restaurado às 20:38”. Não houve envio nem pedido para reescrever.
- “Descartar” exigiu um clique e restaurou imediatamente texto e hashtags vindos
  do servidor.
- Budget observado: zero navegações, zero conferências externas, zero
  redigitações e um clique para abandonar o rascunho.

## Evidência: conflito de versão e autofill

- Em duas abas autenticadas, a aba A abriu a confirmação de aprovação da versão
  1; a aba B recusou o mesmo anúncio e produziu a versão 2.
- A confirmação antiga foi bloqueada com `version_conflict`. O ledger preservou
  a tentativa como conflito e não criou outbox nem destino.
- Na primeira rodada, o diálogo continuava aberto com o botão de confirmação,
  embora aquele token/base já não pudesse ter sucesso. Após a correção, a
  confirmação inválida é descartada e o app abre automaticamente o resultado
  canônico do anúncio, com mensagem de que a ação antiga não teve efeito.
- Na primeira rodada, o gerenciador de senhas do navegador preencheu `admin` no
  campo da frase de segurança e chegou a contaminar um rascunho local. O campo
  foi trocado por uma entrada textual que não é classificada como usuário pelo
  autofill; na repetição ele iniciou vazio. O rascunho contaminado foi descartado.
- O ensaio corrigido foi repetido com o anúncio 7: recusa versão 1→2, aprovação
  antiga `conflict`, navegação automática para `/announcements/7`, zero
  outboxes e zero targets.
- Budget após correção: nenhuma repetição impossível, nenhuma busca manual pelo
  anúncio atual e uma transição automática até a fonte canônica.

## Evidência: sessão expirada e retomada

- O anúncio 8 abriu uma confirmação da versão 1. Antes do step-up, a única sessão
  do banco local descartável foi removida para reproduzir expiração real.
- A tentativa recebeu 401; o conteúdo protegido fechou e a tela informou “Sua
  sessão terminou”, esclarecendo que rascunho e decisão não enviada estavam
  preservados.
- Após `admin/admin` local, apareceu “Sua sessão voltou. A decisão não foi
  enviada” e a ação única “Retomar e reconfirmar”. O servidor emitiu uma nova
  confirmação; nenhum token da sessão anterior foi reutilizado.
- A segunda confirmação produziu o receipt
  `385b1bbe-3734-4dad-b67b-8c39eb25fa75`. O worker local materializou 2 outboxes,
  13 destinos e confirmou 13/13, sempre com `external_effect=false`.
- Budget: uma autenticação inevitável, um clique para retomar, nenhuma
  redigitação do texto/plataformas/público e nenhuma busca manual pelo anúncio.

Para impedir o gerenciador de senhas de escolher uma hashtag como “usuário”, o
diálogo passou a mostrar o usuário autenticado, somente leitura, ao lado da
senha; campos editoriais têm nomes e autocomplete não credenciais. Na repetição,
frase, texto e hashtags permaneceram limpos.

## Evidência: campanha e modelo

- Foi criada pela UI a campanha “E2E local — omotenashi”, gatilho manual,
  Instagram e etiqueta “QA Marketing E2E (12)”. A lista confirmou a criação.
- Na edição, o nome passou a “E2E local — omotenashi revisada”, o modelo mudou
  para “Saiu do forno” e WhatsApp foi incluído. A lista refletiu as duas
  plataformas e o mesmo público.
- O switch foi desligado e religado; desligado, o botão “Disparar” ficou
  desabilitado. O trilho visual permaneceu 36×20 dentro do alvo de toque 44×44.
- Foi criado o modelo “E2E local — modelo”, depois editado para “E2E local —
  modelo revisado”. O botão `store_name` inseriu `{{store_name}}` no ponto de
  edição sem exigir memorização ou redigitação.
- Budget observado: criação e edição ocorreram cada qual em um único painel,
  com prévia ao lado, sem ida ao Admin e sem copiar identificadores externos.
- A rodada pt-BR substituiu “announcement”, “churn” e os rótulos snake_case na
  apresentação normal. A lista de modelos apresenta `[Nome da loja]`,
  `[Nome do produto]` e `[Preço]`; o token interno só aparece no corpo editável,
  onde é necessário ao contrato e pode ser inserido por um botão traduzido.

## Evidência: exclusão com dependências

- A primeira tentativa de apagar “Saiu do forno” foi corretamente recusada pelo
  backend, mas só depois de confirmar; o toast não dizia quais campanhas impediam.
- A projeção passou a trazer nomes de dependências em duas consultas estáveis. Na
  repetição, o primeiro diálogo já listou “E2E local — omotenashi revisada” e
  “Fornada pronta”, suprimiu “Apagar” e ofereceu “Ver campanhas”.
- Um modelo sem dependências continuou mostrando a confirmação destrutiva normal.
  Budget: 1 clique para entender o bloqueio, zero tentativas inválidas, zero busca
  externa e 1 atalho para a superfície de correção.

## Evidência: parcial, repetição seletiva e resultado incerto

- Com o worker parado, uma fixture adversarial local transformou o ledger do
  anúncio 8 em 11 confirmados, 1 `failed_retryable` no Instagram e 1 `unknown`
  no WhatsApp. Nenhum dado ou serviço externo participou da injeção.
- A tela priorizou a incerteza com “Há resultados incertos — não reenvie”,
  mostrou as contagens por plataforma e ofereceu duas ações distintas:
  “Tentar novamente 1 falha” e “Reconciliar 1 resultado incerto”.
- A repetição exigiu frase `PUBLICAR 1` e senha. O receipt
  `059716ac-5d86-4b39-b420-c5cda9c85d16` enfileirou exatamente um alvo e
  declarou que aceitos, confirmados e incertos não foram repetidos.
- O primeiro ciclo real revelou `announcement_not_dispatchable`: o worker
  impedia a repetição porque o anúncio agregado já estava `settled`. A correção
  permite esse caminho apenas quando o anúncio está encerrado **e** o alvo já
  possui tentativa anterior; target inicial encerrado continua fail-closed.
- Após a correção, o worker chamou somente o alvo Instagram e o confirmou. O
  WhatsApp permaneceu com 11 confirmados + 1 incerto.
- A reconciliação exigiu TOTP e criou uma consulta para exatamente um alvo, com
  receipt `3edbd621-fe83-4611-9f1c-14574c390d66`; a UI desabilitou nova abertura
  enquanto a consulta estava pendente.
- O simulador ganhou um boundary `lookup` determinístico e somente leitura; o
  worker local o processa com `--with-reconciliation`. O log registrou
  `operation=lookup external_effect=false`, e não houve chamada a `send`.
- Resultado final: Instagram 1/1 e WhatsApp 12/12 confirmados; apenas o alvo
  falho ganhou uma segunda tentativa, e o incerto foi monotonicamente resolvido
  por consulta.
- Budget observado: 3 cliques para pedir/confirmar cada recuperação, 1 frase +
  1 senha para o retry, 1 TOTP para lookup, zero IDs copiados, zero console para
  o operador e feedback na mesma rota. O worker de demonstração elimina o passo
  técnico manual após `make marketing-simulator`.

## Evidência: ciclo de vida do alerta

- O sino mostrou um anúncio pendente com owner Produto, prazo absoluto/relativo,
  origem e regra de escalonamento.
- “Assumir” mudou “Visto” para “Assumido”, mas manteve o alerta pendente; leitura
  e responsabilidade não foram confundidas com resolução.
- “Revisar anúncio” abriu diretamente `/announcements/1#review`, sem procurar na
  fila e sem perder a âncora.
- A recusa canônica com motivo resolveu a condição e reconciliou o badge de 1
  para 0. O alerta não desapareceu por ter sido visto ou assumido.
- Budget: 1 clique para assumir, 1 para abrir o objeto exato, nenhuma busca e
  reconciliação automática após a decisão.

## Verificação após o limite do agendamento

Depois das 20:40, o anúncio 5 permaneceu `cancelled`, versão 3, entrega
`not_started`; sua única outbox Instagram continuou `cancelled`, sem
`dispatched_at`, e não havia qualquer `DeliveryTarget`. Portanto o cancelamento
venceu de fato a corrida com o worker, não apenas a aparência da tela.

## Linguagem pt-BR observada na UI

Os exemplos reais “Este announcement já foi decidido”, “Receipt”, estado cru
“completed”, “flow”, “provider”, “sandbox” e “churn” foram corrigidos para
“anúncio”, “comprovante”, “concluído”, “fluxo”, “plataforma”, “ambiente de teste”
e “risco de não voltar”. Identificadores internos continuam em código, payload,
diagnóstico e no token de modelo editável quando tecnicamente necessário; não são
mais usados como instrução ou estado normal para o operador.

## Bloqueio técnico descoberto: disparo manual

A Action projetada pelo backend já declarava `command_not_available`, mas a tela
v1 ignorava `actions[]`, abria o painel e chamava um endpoint que sempre respondia
`fire_command_upgrade_required`. A tela agora consome a Action e não permite o
POST. Habilitar o disparo exige implementação própria e não pode ser inferido deste
ensaio: versão positiva da campanha, CAS, idempotência, snapshot de público,
confirmação vinculada, quota, comprovante e resultado rastreável precisam fechar
antes. Até lá, o estado honesto é indisponível.

## Repetição E2E após a rodada de linguagem e omotenashi

Às 21:47 BRT foi criado pelo serviço local um novo anúncio sintético da campanha
“E2E local — omotenashi revisada”. O console foi usado somente para acordar o gatilho,
pois a Action de disparo manual da UI permanece corretamente desabilitada; toda a decisão
e confirmação ocorreu na superfície do operador.

- A tela apresentou 12 clientes, Instagram + WhatsApp e o aviso explícito do bypass
  noturno hermético.
- “Publicar agora” abriu a consequência vinculada à versão 1: 12 destinos, duas
  plataformas e frase exata `PUBLICAR 12`; nada saiu antes da confirmação forte.
- Após frase e senha, o comprovante
  `c976843d-3e4a-494b-a55b-65e9fc8b002f` levou o anúncio à versão 2.
- O worker confirmou Instagram 1/1 e WhatsApp 12/12. O diagnóstico read-only desse
  comprovante registrou 2 outboxes `dispatched`, 13 tentativas e 13 destinos
  `confirmed`, `provider_calls=0`, `pii=false` e `result=OK`.
- Budget observado: 3 ações significativas desde a revisão até o comprovante, uma frase
  e uma senha exigidas pelo risco, zero redigitação editorial, zero IDs copiados, zero
  conferência externa. A atualização entre processos exigiu uma recarga após 2,5 s no
  stack local sem Redis; o ledger já estava concluído.

Ao abrir `/history`, o mesmo anúncio apareceu incorretamente como “Na fila”. A rota de
resultado usa o agregado v2 do ledger, mas o histórico v1 ainda deriva estado do JSON
legado `platform_results`. Corrigir cursor, filtros, estados e métricas do histórico é a
entrega MKT-045. O achado está registrado, mas não foi implementado antes do gate humano
de MKT-044.

## Repetição do histórico no MKT-045

Depois da aprovação do gate MKT-044, `/history` foi migrado para o contrato v2. O anúncio
9 passou a apresentar o mesmo fato do detalhe: execução encerrada com Instagram 1/1 e
WhatsApp 12/12 confirmados. Como não havia recuperação pendente, a chamada mudou de
“Abrir resultado e resolver” para “Ver resultado”.

O ensaio manual confirmou filtros na URL e no backend: 5 itens gerais, 3 contendo
WhatsApp, persistência após reload e vazio filtrado honesto para Facebook, recuperável em
um toque. Em seguida, 27 registros locais sintéticos e identificados provaram paginação:
25 apareceram inicialmente, “Carregar mais resultados” trouxe os dois restantes sem
duplicar linha e desapareceu ao fim. As fixtures foram removidas imediatamente e nenhum
provider ou pessoa real foi envolvido.

O painel também foi conferido no navegador: “Entregas confirmadas hoje” e “Aceitas,
ainda sem confirmação” são números separados; “Clientes alcançados” não é mais inferido
a partir de aceite. O custo comum do filtro é uma seleção, nenhuma digitação, nenhuma
mudança de tela e zero conferência externa.

## Provas finais desta rodada

- Frontend: **30 arquivos / 211 testes**, typecheck, lint e build de produção verdes.
- Projeção de modelos: **5 testes**, incluindo custo constante de **2 queries** para
  listar dependências sem N+1.
- Dependências de produção: `svgo` **4.1.0** e `npm audit --omit=dev` com **0**
  vulnerabilidades.
- Guard de linguagem cobre singular e plural de anúncio, fluxo, plataforma,
  comprovante, ambiente de teste e modelo nos textos literais da UI.
- O rerun noturno dos drills encontrou uma precedência errada: horário silencioso
  adiava um destino cujo consentimento já fora revogado. O worker agora resolve
  identidade/consentimento/assinatura antes da janela de entrega; revogação é terminal
  imediatamente e continua sem chamada à plataforma. Três testes temporais focados e o
  pacote canônico final (**19 backend + 4 BFF**) passaram.
