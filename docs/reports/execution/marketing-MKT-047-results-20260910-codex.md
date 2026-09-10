# MKT-047 — resultados das sessões de gestores

**Estado:** sessão P01 concluída; T1–T9 executadas; P02–P03 pendentes
**Commit sob avaliação:** `9fd2b6a5d` + correções `bcc00fc48`, `6fd632b1d`, `92b4de2ea`, `d9e54c5c5`, `42b2eb7ed`, `a88b550c8`, `057f307e8`, `d86e0dce8` e `6c4bbc3f2`
**Perfil:** `config.settings_marketing_demo`, adapter `SIMULATION_ONLY`  
**Política de dados:** somente códigos P01–P05 e métricas; sem nomes, conteúdo ou PII

## Preparação do ambiente

Em 2026-09-10, antes da sessão P01:

- o banco SQLite descartável recebeu backup local e as migrations correntes;
- a única directive vencida era um check sintético de produção e foi concluída pelo
  handler local, sem provider externo;
- Django `/health/live/` e `/health/ready/` retornaram 200;
- BFF `/health/live` e `/health/ready` retornaram 200;
- o adapter de Marketing permanece `SIMULATION_ONLY` e as flags externas permanecem
  desligadas.

## Participantes

| Código | Perfil operacional resumido, sem identificação | Data | Estado |
|---|---|---|---|
| P01 | proprietário/gestor | 2026-09-10 | concluída |
| P02 | gestor real | — | pendente |
| P03 | gestor real | — | pendente |
| P04 | participante cumulativo do piloto | — | futuro |
| P05 | participante cumulativo do piloto | — | futuro |

## Resultados por tarefa

O facilitador preenche esta tabela; o participante não precisa anotar cliques ou tempos.

| Participante | Tarefa | Sem ajuda | Ações | Digitação extra | Telas | Espera máx. | Consulta externa | Recuperação preservada | Certeza completa | Resultado/achado sem PII |
|---|---:|:---:|---:|:---:|---:|---:|---:|:---:|:---:|---|
| P01 | 1 | não | 3 inferidas | só senha/frase de segurança | 0 | 335 s totais, incluindo esclarecimento | 0 | N/A | não | Agendou; precisou perguntar entre “Publicar agora” e “Agendar”. Comprovante `899184a4-91a4-4a51-8836-f20a9fc181a3`. |
| P01 | 2 | sim | 3 inferidas + edição | somente texto e senha/frase de segurança | 0 | 84 s totais | 0 | N/A | não | Texto exato aprovado agora; comprovante `0655480d-6127-473d-8b38-d400c61db4f3`; sem dúvida relatada. |
| P01 | 3 | sim | 3 inferidas + data/hora | somente data/hora e senha/frase de segurança | 0 | 1.045 s de relógio; tempo ativo não observável | 0 | N/A | não | Persistiu 11/09/2026 09:15 BRT; comprovante `7d79ef88-beae-4bd2-8f3d-b919010febc5`; sem dúvida relatada. |
| P01 | 4 | não | não concluída | houve redigitação aparente | 1 | 207 s até a interrupção | 0 | não | não | Reautenticação fechou o editor. O rascunho existia, mas só reapareceu após abrir manualmente “Nova campanha”; tarefa invalidada. |
| P01 | 4R1 | sim | não instrumentadas | somente o nome solicitado | 0 trocas de rota | não instrumentada; sem espera relatada | 0 | N/A; sessão não expirou | sim, no escopo de T4 | Repetição concluída sem pedido de ajuda. Regra 6 voltou do servidor ativa, versão 1, com gatilho manual, modelo “Saiu do forno”, Instagram + WhatsApp e tag `qa-marketing-e2e`; lista mostrou público de 12 pessoas. Budgets de clique/latência não são reivindicados sem telemetria. |
| P01 | 5 | sim | 3 inferidas + senha/frase de segurança | nenhuma editorial | 0 | ≈13 min de relógio; tempo ativo não observável | 0 | N/A | sim, no escopo de T5 | Antes da confirmação viu 12 pessoas e que nasceria para revisão. Criou somente o anúncio 42 pendente, comprovante `c8a62cef-2e47-4b1d-88f1-196c060e33a8`; zero outbox e zero destino. |
| P01 | 6 | sim | 1 ação + senha/frase de segurança após preparação | nenhuma | 0 | ≈4 min de relógio; tempo ativo não observável | 0 | N/A | não | Repetiu somente 1 falha: 13/13 confirmados ao final, comprovante `d34a7a52-51ed-4fa0-9d0f-ff985c474daa`. A confirmação dizia “Instagram, WhatsApp” embora o alvo fosse só WhatsApp; P01 identificou a ambiguidade. |
| P01 | 6R1 | sim | inspeção visual; nenhum comando executado | nenhuma | 0 | sem espera relatada | 0 | N/A | sim, no escopo de T6 | P01 confirmou que “1 destino elegível” e o escopo exclusivo de WhatsApp estavam claros. Sugeriu retirar “realmente” da copy; ajuste incorporado como “Plataformas afetadas”. Cenário restaurado a 13/13 sem nova entrega. |
| P01 | 7 | não | 1 confirmação + TOTP; inscrição assistida | só TOTP, permitido pelo gate | 0 no app | não instrumentada | 1 autenticador, exigido pela segurança | N/A | não | A consulta funcionou, mas P01 precisou perguntar de qual autenticador viria o código: o device local não havia sido inscrito no aparelho. Comprovante `b5ecbefe-a1eb-40ff-876a-829118671d09`, versão 4, uma consulta e zero reenvios. |
| P01 | 7R1 | sim | 1 confirmação + TOTP | só TOTP, permitido pelo gate | 0 no app | não instrumentada | 1 autenticador, exigido pela segurança | N/A | sim, no escopo de T7 | Repetição após enrollment concluída sem pedido de ajuda. Comprovante `7cdb3a33-2ccb-4759-9949-cc6c4372b893`, versão 5, somente WhatsApp, uma consulta e zero reenvios; ledger final 13/13. P01 apontou desalinhamento visual das casas do código depois de concluir. |
| P01 | 8 | sim | 2 inferidas + TOTP | só TOTP, permitido pelo gate | 0 no app | não instrumentada; sem espera relatada | 1 autenticador, exigido pela segurança | rollback não acionado; gravação concluída | sim, no escopo da configuração | Substituiu a referência indisponível pelo fluxo local aprovado. Comprovante `1e81fb34-29f6-4f58-9d9b-b6773be51db2`, versão 3→4; teste externo permaneceu bloqueado por não existir aparelho verificado e nenhum envio foi criado. |
| P01 | 9 | sim | login + 1 retomada após a expiração | somente credenciais de login | 0 trocas de rota | não instrumentada; sem espera relatada | 0 | sim | sim, no escopo da retomada | Após a expiração controlada, voltou a `/announcements/42`, retomou e recebeu uma confirmação nova e vazia para a versão 1, público 12 e Instagram + WhatsApp. O anúncio permaneceu pendente, sem aprovação, outbox ou destinos. |

As linhas P02–P05 serão adicionadas no início de cada sessão, nunca antecipadas como
evidência. O resumo e a decisão G-H05 só serão escritos depois da coleta real.

## Achados vivos

### P01/T1 — default seguro e certeza do comprovante

- A instrução “opção padrão mais segura para a próxima janela” levou o participante a
  perguntar se deveria usar **Publicar agora**; a tela apresenta **Publicar agora** e
  **Agendar** como alternativas concorrentes sem declarar qual é o default seguro.
- Depois do esclarecimento, o participante agendou e reconheceu o resultado como
  “anúncio agendado”.
- O estado final mostrou versão e plataformas, mas não reapresentou o horário agendado
  nem a audiência de 12 clientes no comprovante. Assim, a certeza obrigatória não pode
  ser inferida da tela final.
- Classificação: concluiu com ajuda; tarefa fora do aceite. Corrigir e repetir T1 depois
  da rodada inicial, sem refazer tarefas que tenham passado.

### P01/T2 — decisão rápida, resultado assíncrono e contexto incompleto

- O participante alterou somente o texto solicitado e aprovou para agora sem pedir
  ajuda, em 84 segundos totais.
- O backend preservou exatamente o texto, a versão 2 e o modo `now`; o simulador local
  convergiu para 13/13 attempts confirmados, com zero provider externo.
- Ao parar no comprovante, a tela dizia corretamente “publicando” e “entrega ainda não
  começou”, sem fingir confirmação. Porém o comprovante não reapresentava a audiência de
  12 clientes; por isso “certeza completa” continua falsa sob o critério estrito.
- Classificação: fluxo funcional e sem ajuda; corrigir o resumo do comprovante e repetir
  somente a checagem de certeza depois da alteração.

### P01/T3 — instante correto, mas ausente no encerramento

- O participante agendou sem ajuda. O backend persistiu exatamente
  `2026-09-11T09:15:00-03:00`, com timezone `America/Sao_Paulo`, versão 2 e público de
  12 clientes.
- O intervalo de 1.045 segundos é relógio de conversa, não tempo ativo instrumentado;
  portanto não será usado como latência ou falha de budget de espera.
- O comprovante final novamente não exibiu 11/09 às 09:15 nem a audiência; dizia apenas
  que horário e versão estavam guardados. A persistência está correta, mas exige memória
  ou conferência externa para confirmar o instante.
- Classificação: execução funcional sem ajuda; certeza final fora do aceite. A correção
  do comprovante atende T1–T3 em uma única intervenção e requer só a checagem final.

### P01/T4 — reautenticação escondeu um rascunho preservado

- Durante a criação, a tela informou que o rascunho estava salvo no dispositivo e em
  seguida pediu autenticação novamente. Depois do login, voltou à lista de campanhas,
  aparentando perda integral do trabalho; o participante não conseguiu concluir T4.
- A inspeção no mesmo navegador comprovou que o registro local não havia sido apagado:
  ao abrir manualmente **Nova campanha**, reapareceram o nome `Pesquisa P01 — fornada`,
  o gatilho manual, o modelo **Saiu do forno** e Instagram.
- Causa confirmada na UI: o gate de autenticação desmontava a página e os `ref`s locais
  que lembravam o editor aberto. A promessa de preservação era tecnicamente verdadeira,
  mas a recuperação exigia memória e navegação não explicadas — falha de omotenashi.
- Risco adicional confirmado no código: um salvamento ainda dentro do debounce de 400
  ms consultava a identidade reativa depois da perda de sessão e podia ser descartado.
- Correção local: o editor aberto agora usa estado Nuxt preservado através do gate; cada
  gravação pendente captura operador, recurso, versão, base e conteúdo no instante da
  edição. Teste de regressão reproduz a identidade desaparecendo antes do debounce.
- Diagnóstico da recorrência: em um Chrome limpo, o cookie manteve validade de 14 dias e
  o poll de 60 segundos retornou 200. O perfil de ensaio compartilhava o nome genérico
  `sessionid` entre todos os backends locais em `127.0.0.1` (cookies ignoram porta). O
  perfil descartável passou a usar `marketing_demo_sessionid`; produção não muda.
- Evidência inicial: 25 testes focados e o typecheck passaram; no navegador real o
  rascunho P01 foi restaurado sem redigitação. T4 original permanece **falha** e será
  repetida integralmente depois da validação da suíte, sem reclassificar o incidente.

### P01/T4-R1 — repetição humana após a correção

- P01 repetiu a tarefa sem pedir ajuda e confirmou a conclusão; o navegador permaneceu
  em `/campaigns`, sem navegação para outra tela.
- A própria lista reapresentou **Pesquisa P01 — fornada — reteste** como disparo manual,
  Instagram + WhatsApp e público **QA Marketing E2E (12)**.
- Uma leitura do banco descartável confirmou a regra 6 ativa, versão 1, com modelo
  **Saiu do forno**, `platforms=[instagram, whatsapp]`,
  `audience_rules={tags: [qa-marketing-e2e]}` e agendamento vazio. Nenhum conteúdo ou
  dado pessoal foi coletado.
- Classificação: repetição funcional aprovada, sem ajuda, redigitação extra, troca de
  tela ou consulta externa. Como não havia telemetria de cliques/latência da interação
  humana, este registro não inventa esses números nem os usa para aprovar o budget
  agregado do gate.
- O incidente original continua na linha T4 como falha e permanece parte da evidência;
  esta linha registra somente o resultado posterior à correção.

### P01/T5 — disparo manual sem envio

- P01 concluiu sem pedir ajuda depois de receber o objetivo e os dados da ficha. A tela
  mostrou antes da confirmação o público salvo de 12 pessoas e explicou que a ação
  criaria um anúncio para revisão, sem publicar.
- O comprovante `c8a62cef-2e47-4b1d-88f1-196c060e33a8` registra `fire` concluído sobre
  a campanha 6, produto `MD`, público 12 e anúncio 42 em `pending_review`.
- O anúncio 42 voltou do servidor com Instagram + WhatsApp, versão 1,
  `delivery_state=not_started`, sem horário de publicação e sem publicação realizada.
  Havia zero `MarketingOutbox` e zero `DeliveryTarget`: nenhuma chamada ao simulador ou
  provider pôde começar.
- Classificação: estado de sucesso de T5 atendido e certeza da consequência confirmada.
  As três ações são inferidas do caminho preparado (produto, disparo e confirmação);
  os cerca de 13 minutos são relógio de conversa, não tempo ativo, logo não aprovam nem
  reprovam os budgets agregados de contagem/ack sem telemetria.

### P01/T6 — repetição seletiva correta e correção do escopo exibido

- O cenário começou com 1 publicação de Instagram confirmada e, no WhatsApp, 11
  mensagens confirmadas + 1 falha repetível. A tela explicou que aceitos, confirmados e
  incertos não seriam reenviados.
- P01 autorizou a recuperação sem pedir ajuda. O comprovante
  `d34a7a52-51ed-4fa0-9d0f-ff985c474daa` registrou uma única falha na fila e versão 3;
  depois do worker hermético, o ledger terminou com 1/1 Instagram e 12/12 WhatsApp
  confirmados. O histórico contém 13 confirmações finais e exatamente uma tentativa
  anterior `failed_retryable`.
- A confirmação anterior ao comando, porém, dizia **“Plataformas: Instagram,
  WhatsApp”** para **1 destino elegível**. P01 questionou corretamente a diferença entre
  postagem pública e mensagem direta; não havia certeza de qual efeito seria repetido.
- Causa confirmada: quando o request não restringia plataforma, o serviço selecionava
  corretamente apenas targets `failed_retryable`, mas passava todas as plataformas do
  anúncio para autorização, auditoria e comprovante.
- Correção `d9e54c5c5`: autorização, auditoria e receipt agora recebem somente as lanes
  dos targets efetivamente afetados. A UI diz **“Plataformas afetadas”**,
  corrige o singular e explica: Instagram/Facebook/Google são publicações públicas;
  WhatsApp é mensagem direta por pessoa com consentimento revalidado. O formulário
  também declara que DM do Instagram não faz parte deste app.
- O contrato ficou documentado no README da superfície: eventual DM do Instagram deve
  nascer como lane/capability separada, com identidade, consentimento, limite,
  readiness e comprovante próprios; nunca misturada ao `instagram` público.
- Validação: 186 testes focados de backend, 240 testes da interface, typecheck, lint
  focado, `ruff` e `git diff --check` passaram. Uma regressão no navegador real mostrou
  **“1 destino elegível”** e escopo exclusivo de WhatsApp; o cenário técnico foi
  restaurado para 13/13 depois da inspeção.
- Em T6-R1, P01 confirmou que a quantidade e o escopo exclusivo de WhatsApp estavam
  claros, sem executar a recuperação novamente. Também observou que **“realmente”** era
  dispensável; `42b2eb7ed` incorporou a melhoria de omotenashi para a copy final
  **“Plataformas afetadas”**, coberta por teste focado de componente e lint.
- Classificação: efeito seletivo e certeza aprovados após a repetição mínima. O cenário
  local foi restaurado a 13/13 confirmados, sem falhas repetíveis ou resultados incertos.

### P01/T7 — consulta segura, inscrição do autenticador e acabamento do modal

- O cenário começou com 12 destinos confirmados e 1 resultado incerto somente no
  WhatsApp. A tela dizia **“não reenvie”** e explicava que a ação apenas consultaria o
  provedor.
- Na primeira execução, P01 perguntou de qual autenticador viria o código. Havia um
  `TOTPDevice` criado no banco descartável, mas ele não havia sido inscrito em nenhum
  aparelho do participante. A segurança bloqueou corretamente; o preparo e a orientação
  humana falharam. T7 original permanece **sem ajuda: não**.
- Com autorização explícita, o device exclusivamente local foi substituído, P01
  cadastrou o QR no próprio autenticador e o arquivo temporário com o QR foi apagado logo
  depois. O segredo de provisionamento foi exibido somente no QR autorizado desta sessão;
  não foi commitado nem será reutilizado em produção.
- A execução original gerou o comprovante
  `b5ecbefe-a1eb-40ff-876a-829118671d09`, versão 4: `lookup_count=1`, plataforma
  `whatsapp`, zero chamada a `send`. O job terminou `completed/confirmed` por `lookup` do
  simulador e o ledger voltou a 13/13, sem criar nova tentativa de entrega.
- `a88b550c8` substituiu os três inputs TOTP genéricos pelo `PinInput` acessível já
  fornecido pelo Reka UI: quantidade parametrizável, casas numéricas, avanço automático,
  colagem, `one-time-code`, rótulos por dígito e instrução sobre a origem do código.
- Após feedback de P01, `057f307e8` reorganizou o modal: cabeçalho centralizado,
  consequência segura destacada, destinos e plataformas em um único resumo, botões
  responsivos de largura integral e linguagem operacional **“Consultar resultado”** /
  **“Consulta registrada”**.
- T7-R1 foi concluída sem novo pedido de ajuda. O comprovante
  `7cdb3a33-2ccb-4759-9949-cc6c4372b893`, versão 5, novamente registrou exatamente uma
  consulta só de WhatsApp e zero reenvios; o ledger terminou em 13/13.
- Depois de concluir, P01 detectou que a fileira de casas ainda estava deslocada dentro
  do contêiner central. `d86e0dce8` corrigiu a raiz com `justify-center`; o teste focado
  fixa a classe e a verificação visual no navegador confirmou o eixo do conjunto.
- Validação: 243 testes da interface, typecheck, lint focado e `git diff --check`
  passaram para o modal; a correção final de alinhamento repetiu o teste do componente.
  Classificação: T7 funcional e repetição humana aprovadas; o achado de preparo permanece
  preservado como falha da rodada original.

### P01/T8 — configuração recuperada com CAS e teste externo fechado por segurança

- O facilitador preparou no banco descartável uma referência conhecida, porém ausente
  do catálogo ativo (`retired_local_flow`, versão 3). A interface identificou a
  configuração como indisponível e ofereceu somente a alternativa aprovada
  **“Fluxo local — sem envio externo”**.
- P01 concluiu sem pedir ajuda. Antes da autorização, o modal mostrou configuração
  atual, configuração resultante, versão revisada e a consequência explícita
  **“Nenhuma mensagem será enviada agora”**; o código TOTP foi a única digitação além
  da seleção e confirmação.
- O comprovante `1e81fb34-29f6-4f58-9d9b-b6773be51db2` ficou `completed`, com CAS
  `base_version=3` e `resulting_version=4`. O evento imutável
  `00f04fec-1130-4592-a9e2-93d7799722f9` registra WhatsApp,
  `previous_flow_ref=retired_local_flow` e
  `resulting_flow_ref=local_marketing_e2e`; a leitura posterior confirmou o modelo
  ativo na versão 4.
- A área do canal reapresentou o fluxo local como seleção atual. O teste seguro ficou
  visivelmente **“bloqueado com segurança”**, pois o perfil não possui aparelho de teste
  verificado. Isso é o resultado fail-closed correto, não um teste externo bem-sucedido:
  foram criados zero `MarketingTestReceipt`, zero `MarketingOutbox` e zero efeitos
  externos desde o comando.
- O rollback não precisou ser acionado porque o CAS foi aceito; sua execução não é
  reivindicada como evidência humana. A certeza da configuração e do bloqueio seguro
  foi completa, mas cliques e latência não são aprovados sem telemetria.
- `6c4bbc3f2` também refinou o modal compartilhado deste fluxo: código centralizado,
  resumo compacto, botões de largura integral e todo o gate visível sem rolagem na
  viewport do ensaio. Validação: 243 testes da interface, typecheck, lint focado e
  `git diff --check` passaram.

### P01/T9 — sessão expirada sem perder nem executar a decisão

- O facilitador abriu a confirmação de publicação do anúncio local 42, preencheu a
  frase e a credencial de ensaio sem confirmar, identificou exatamente a sessão ativa
  do perfil descartável e a expirou no servidor. Nenhuma sessão de outro app foi
  alterada.
- Ao tentar confirmar, P01 recebeu o login de sessão encerrada. Depois de entrar, o app
  voltou à mesma URL `/announcements/42`, declarou que a decisão não havia sido enviada
  e ofereceu **“Retomar e reconfirmar”**. Não houve troca de rota ou busca manual do
  anúncio.
- P01 acionou a retomada sem pedir ajuda adicional e recebeu uma confirmação nova, com
  os campos sensíveis novamente vazios. O servidor reapresentou versão 1, público de 12
  pessoas, Instagram e WhatsApp, além das diferenças entre publicação pública e
  mensagem direta. A segunda confirmação não foi autorizada, conforme o roteiro.
- A leitura posterior comprovou `pending_review`, versão 1,
  `delivery_state=not_started` e `published_at=null`. Não existe receipt de aprovação:
  o único receipt ligado ao anúncio é o `fire` que o criou em T5. Também permanecem
  zero `MarketingOutbox` e zero `DeliveryTarget`.
- Classificação: retomada funcional aprovada, com intenção preservada, challenge antigo
  descartado, contexto revalidado e efeito externo inexistente. O retorno visual foi
  percebido como imediato, mas o limite de 1 segundo não é reivindicado sem telemetria.

### Regressão técnica facilitada — não conta como participante MKT047

- O facilitador retomou o rascunho preservado, concluiu a campanha e percorreu o fluxo
  real do app local: disparo manual → contagem de 12 pessoas → confirmação → revisão →
  publicação pelo simulador → resultado assentado.
- A execução criou 1 destino de Instagram e 12 de WhatsApp; os 13 attempts terminaram
  `confirmed` com receipts `sim_…` e `external_effect=false`. Nenhum provider externo foi
  chamado.
- O ensaio encontrou três lacunas adicionais antes do novo gate humano: o modelo exigia
  produto sem oferecer um seletor; a prévia de revisão voltava ao produto de amostra; e
  uma contagem anterior podia habilitar o botão durante o debounce da nova escolha.
- A correção `92b4de2ea` oferece produtos como **Nome (SKU)** antes da senha, sela o SKU e
  o hash factual na confirmação, reaproveita exatamente o conteúdo autorizado na criação,
  invalida contagens antigas e usa o SKU da ocorrência na prévia fiel.
- O comprovante de aprovação passou a sobreviver à recarga pelo contrato persistente do
  servidor. Duas recargas manuais do anúncio 41 mantiveram visíveis público de 12 pessoas,
  Instagram + WhatsApp, modo imediato, instante, versão e receipt
  `5c668017-35f9-48d2-bb4c-3791c4e3af0d`.
- Validação do diff final: 172 testes de backend e 239 de interface passaram, junto de
  typecheck, lint, `ruff`, contrato gerado e `git diff --check`.
- Esta evidência aprova a regressão técnica, mas **não** transforma o facilitador em P01
  nem reclassifica o incidente original. A repetição humana posterior está registrada
  separadamente em P01/T4-R1.
