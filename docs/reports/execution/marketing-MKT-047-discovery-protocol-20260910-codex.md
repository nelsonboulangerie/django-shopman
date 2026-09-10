# MKT-047 — protocolo de discovery e budgets do operador

**Estado:** encerrado por dispensa explícita do Product owner; não aprovado por amostra
**Ambiente permitido:** local ou staging seeded, sem destinatário/provider real
**Participantes:** 3 gestores reais no pré-piloto; 5 cumulativos antes do rollout de 25%; usar apenas códigos `P01`…`P05`, sem nome ou PII
**Duração prevista:** três blocos de 10–15 minutos por participante
**Owner da decisão:** Product owner

## Decisão de Produto que encerra este protocolo

Em 2026-09-10, depois de ser informado de que MKT-047 vinha do plano original como
“Discovery de 5–8 gestores e budgets”, o Product owner determinou explicitamente:
“desinventa. dá seus pulos.” A decisão cancela a coleta obrigatória com P02–P05 e retira
MKT-047 da cadeia bloqueante para MKT-048. O protocolo fica preservado como histórico e
como opção de discovery futuro, mas não será imposto ao operador nem apresentado como
trabalho pendente.

Esta é uma **dispensa de Produto**, não uma aprovação fictícia: não se declara que a
amostra de gestores ou os budgets foram satisfeitos. As evidências humanas já coletadas
continuam íntegras; os cenários mecânicos restantes passam a regressão técnica local e
não são atribuídos a participantes. A dispensa não reduz consentimento, autorização,
step-up, fail-closed, idempotência, reconciliação ou qualquer outra proteção técnica.
Também não autoriza push, PR, deploy, produção, credencial/provider externo ou envio
real; G-H09 e G-H10 continuam exigindo autorização contextual própria.

Este protocolo transforma G-H05/MKT-047 em uma sessão repetível. Ele não autoriza
deploy, produção, sandbox externo, credencial externa ou envio real. O facilitador
configura e reinicia o cenário; o participante só opera o cockpit.

Em 2026-09-10, o proprietário aprovou explicitamente a alteração da amostra: três
gestores no pré-piloto e cinco participantes cumulativos antes do rollout de 25%. A
mudança reduz somente a amostra inicial de discovery. Contratos, critérios por tarefa,
gates de segurança, release, produção e envio permanecem inalterados. Com três pessoas,
o limiar inteiro equivalente a 80% é **3/3** em cada caso comum.

## Decisões provisórias submetidas à validação

- o caso comum revisa e agenda na próxima janela permitida; **Publicar agora** é
  sempre uma ação separada;
- conteúdo pode ser editado até a aprovação; depois dela, correção cria nova versão;
- cancelamento alcança só trabalho reversível e informa o que foi evitado e o que já
  não pode ser desfeito;
- o sino prioriza privacidade, duplicidade, resultado incerto/parcial, trabalho preso,
  canal indisponível e aprovação pendente; informativos ficam no próprio objeto;
- a ação principal abre o problema exato já contextualizado;
- senha, frase de consequência e TOTP podem exceder o budget apenas quando o gate de
  segurança exigir; conteúdo, público, horário e IDs não podem ser redigitados.

## Preparação pelo facilitador

1. Usar exclusivamente a worktree/branch isolada aprovada.
2. Criar uma base descartável com `config.settings_marketing_demo` conforme
   `docs/operations/marketing-local-simulator.md`; nunca apontar para um banco existente.
3. Manter todas as flags de efeito externo fechadas e o adapter
   `SIMULATION_ONLY`; confirmar `external_effect=false` antes da primeira sessão.
4. Iniciar Django em `127.0.0.1:8008`, Marketing Nuxt em `127.0.0.1:3008` e
   `make marketing-simulator`.
5. Antes de cada participante, restaurar a fixture canônica e verificar live/ready.
6. Gravar somente métricas de tarefa e observações sem conteúdo, credencial ou PII.

## Roteiro único — nove tarefas

O facilitador lê apenas o objetivo. Não ensina o caminho, salvo se o participante
pedir ajuda; toda ajuda é registrada e torna aquele caso “com ajuda”.

Para reduzir fadiga, executar tarefas 1–3, 4–6 e 7–9 em três blocos independentes. O
participante pode interromper entre blocos sem perder a validade das tarefas concluídas.

| # | Objetivo dado ao participante | Estado de sucesso | Budget do caso comum |
|---:|---|---|---|
| 1 | Aprovar um anúncio pronto para a próxima janela segura. | Comprovante no mesmo contexto, com versão, público, horário, plataformas e estado por canal. | ≤3 ações; 0 digitação; 0 telas; preview/ack ≤1 s |
| 2 | Ajustar somente o texto e aprovar. | Texto preservado, diff/prévia final visível e aprovação da versão correta. | ≤5 ações + edição; 0 telas; autosave ≤1 s |
| 3 | Agendar para o horário solicitado. | Data, timezone, expiração e efeito das quiet hours inequívocos. | ≤4 ações; no máximo data/hora; 0 telas |
| 4 | Criar uma regra comum com o público indicado na ficha. | Gatilho, exclusões, dedupe e próximas ocorrências visíveis; round-trip sem perda. | ≤7 ações; só nome digitado; ≤1 tela; count ≤2 s |
| 5 | Disparar manualmente a regra escolhida. | Contagem e consequência antes da confirmação; cria anúncio pendente e comprovante, sem enviar. | ≤4 ações; 0 digitação editorial; 0 telas; count ≤2 s/ack ≤1 s |
| 6 | Resolver uma entrega parcial repetível. | Só alvos falhos são repetidos; antes/depois e incertezas restantes ficam claros. | ≤3 ações; 0 digitação; 0 telas; ack ≤1 s |
| 7 | Tratar um resultado incerto sem reenviar às cegas. | Reconciliação/escalonamento com owner; linguagem não sugere entrega nem reenvio. | ≤3 ações; 0 digitação; ≤1 tela; feedback ≤1 s |
| 8 | Corrigir um canal com configuração conhecida indisponível. | Configuração selecionada, CAS/rollback e resultado do teste seguro visíveis. | ≤4 ações; ref selecionada; ≤1 tela; check ≤3 s |
| 9 | Retomar a decisão depois que a sessão expirar. | Login volta ao mesmo ponto, revalida versão/readiness e pede nova confirmação. | login + 1 ação; password manager; 0 telas; retorno ≤1 s |

## Registro por tarefa

Duplicar uma linha para cada participante e tarefa:

| Participante | Tarefa | Concluiu sem ajuda | Ações | Digitação além do permitido | Mudanças de tela | Espera máxima | Consulta externa | Trabalho preservado na recuperação | Certeza final completa | Observação sem PII |
|---|---:|:---:|---:|:---:|---:|---:|---:|:---:|:---:|---|
| P__ | __ | sim/não | __ | sim/não | __ | __ ms | __ | sim/não/N/A | sim/não | __ |

“Certeza final completa” exige que o participante localize sem ajuda versão, público,
horário, plataformas e próxima ação, e diferencie aceito, confirmado, parcial e incerto.

## Regra de decisão, sem interpretação oportunista

MKT-047 pré-piloto só passa quando:

- 3 gestores reais concluíram as nove tarefas;
- os 3 concluíram **cada** caso comum sem ajuda;
- a mediana de cada métrica está dentro do budget correspondente;
- houve zero perda de rascunho, zero ação perigosa acidental e zero leitura de
  aceito/parcial/incerto como entrega total;
- 100% localizaram versão, público, horário, plataformas e próxima ação ao concluir;
- toda exceção de budget tem motivo de segurança e aprovação explícita de Produto.

Além disso, o rollout de 25% permanece bloqueado até que pelo menos cinco gestores
distintos tenham participado cumulativamente sob os mesmos critérios. As duas pessoas
adicionais podem participar durante o piloto limitado, mas não substituem nenhum gate de
segurança, SLO, release ou produção.

Qualquer falha produz achado e nova rodada somente das tarefas afetadas depois da
correção. Não se reduz confirmação, consentimento, autorização ou fail-closed para
atingir um número.

## Declaração de fechamento

Após anexar a tabela preenchida e o resumo agregado, o Product owner decide:

```text
APROVO G-H05 / MKT-047
participantes: <3 códigos no pré-piloto, sem nomes>
execução: <data/ambiente/commit>
resultado: <taxa por tarefa + medianas>
exceções de segurança: <nenhuma ou lista aprovada>
achados remanescentes: <nenhum bloqueante ou lista>
```

Esta declaração deixou de ser exigida pela dispensa explícita acima. MKT-048 pode
começar apoiado na decisão G-H07 já aprovada e nas regressões técnicas; nenhum estágio
externo ou rollout é autorizado por isso.
