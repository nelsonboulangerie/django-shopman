# MKT-047 — resultados das sessões de gestores

**Estado:** coleta P01 em andamento; T4 original preservado como falha e repetição humana concluída funcionalmente
**Commit sob avaliação:** `9fd2b6a5d` + correções `bcc00fc48`, `6fd632b1d` e `92b4de2ea`
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
| P01 | proprietário/gestor | 2026-09-10 | em andamento |
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
| P01 | 5 | — | — | — | — | — | — | — | — | pendente |
| P01 | 6 | — | — | — | — | — | — | — | — | pendente |
| P01 | 7 | — | — | — | — | — | — | — | — | pendente |
| P01 | 8 | — | — | — | — | — | — | — | — | pendente |
| P01 | 9 | — | — | — | — | — | — | — | — | pendente |

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
