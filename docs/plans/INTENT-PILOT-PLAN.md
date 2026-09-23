# INTENT-PILOT-PLAN: piloto de intenções nas mensagens de clientes

> **Status: 🧪 roda sozinho; a casa só confere.** Pedido do dono em 23/09/2026: "tenho interesse
> [...] sobretudo em reconhecer intenções dos clientes na mensageria (no plural mesmo)", e, sobre
> o trabalho: "você faz, a gente só confere". Irmão do [BI-JEV-PILOT](BI-JEV-PILOT.md), que mede o
> mesmo tipo de ferramenta no de-para de produto. Nada aqui muda o concierge: o piloto só mede.

## 1. A pergunta

Uma mensagem de cliente pode querer várias coisas ao mesmo tempo: "quero 2 croissants para
amanhã, vocês entregam no Centro? sou celíaca". **Qual classificador reconhece TODAS as
intenções de uma mensagem, sem deixar passar as sensíveis, a que custo e em quanto tempo?**

A resposta decide três usos possíveis, que dependem do placar:

1. **Transferência para a equipe mais fina.** Hoje o `classify_handoff_request`
   (`storefront/concierge/handoff.py`) é uma regex que devolve **uma** causa, a primeira que
   casa, e pula o agente. "Quero falar com alguém sobre a encomenda do casamento, sou alérgica
   a nozes" vira só `customer_request`: a alergia some do motivo.
2. **B.I. da mensageria.** Quantas reclamações, dúvidas e pedidos chegam, por dia e por hora.
   Hoje não existe: não há rótulo de intenção em lugar nenhum.
3. **Custo do concierge.** Uma pergunta simples ("abre domingo?") não precisa do agente com
   Sonnet 5 e 11 ferramentas. Um classificador barato na porta pode separar o que é resposta de
   uma linha.

## 2. O que existe hoje (levantado em 23/09)

- **Um canal de entrada de verdade:** WhatsApp via ManyChat → concierge
  (`POST /api/webhooks/concierge/<connection_key>/events/`). Instagram, iFood, SMS e e-mail não
  recebem conversa de cliente.
- **Sem classificador de intenção.** O desenho "um fluxo por intenção" (`#menu`, `#pedir`) foi
  abandonado de propósito na [ADR-026](../decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md):
  "o cliente não fala em intenções". O agente escolhe ferramentas e já responde a vários pedidos
  num turno. **O piloto não reabre essa decisão:** ele mede, e o uso que vier respeita a ADR (o
  agente continua dono da conversa).
- **A única classificação:** a regex de transferência, com quatro causas.
- **Histórico:** `ConversationMessage` (`kind=inbound`) guarda o texto. Não há rótulo humano:
  por isso o piloto começa pelo gabarito.

## 3. Como mede

- **Vocabulário = dado.** `IntentCategory`, editável no Admin (Clientes → Intenções). A lista
  inicial foi fechada com o dono em 23/09 (ele pediu os temas de fora da venda):

  | ref | nome | sensível |
  |---|---|---|
  | `order` | Pedido | |
  | `product_question` | Dúvida de produto | |
  | `hours_delivery` | Horário, endereço, retirada ou entrega | |
  | `order_status` | Status do pedido | |
  | `special_order` | Encomenda especial | |
  | `house_info` | Como funciona a casa (pet, mesa, wi-fi, estacionamento…) | |
  | `complaint` | Reclamação | ✔ |
  | `allergy` | Alergia ou restrição | ✔ |
  | `human` | Falar com uma pessoa | ✔ |
  | `job` | Vaga de emprego | |
  | `partnership` | Parceria ou divulgação (influenciador, sessão de fotos no local) | |
  | `supplier_offer` | Proposta de fornecedor | |

  "Sensível" = deixar passar custa caro; o placar mede essas à parte. As três últimas nem são de
  cliente: são mensagens que vão para outra mesa da casa, e o reconhecimento delas é o que tira
  esse ruído da fila do atendimento.
- **Corpus = a observação que já roda.** O concierge em modo `observe` grava as perguntas que
  chegam enquanto a equipe responde (já redigidas, `automation_eligible=false`, com prazo de
  retenção de 1 a 30 dias, default 7). É desse corpus que o piloto sorteia.
- **A máquina sugere, a casa confere.** O ciclo automático (`run_intent_pilot`, no
  `maintenance_worker`) sorteia até 40 mensagens recentes por dia (fila aberta de no máximo 200),
  e um modelo forte da Anthropic (`AI_ASSIST_MODEL`) pré-marca as intenções: estado **sugerida**.
  Em Admin → Clientes → **Mensagens para rotular** a pessoa confere uma por vez (corrige as
  caixinhas e salva; a tela abre a próxima) ou várias de uma vez ("Confirmar sugestões
  selecionadas como estão"). Só o **conferido** é gabarito. Ininteligível → "Pular".
- **Viés declarado:** gabarito que nasce de sugestão ancora na sugestão. Por isso o modelo que
  sugere não entra no placar automático, que mede outros (Haiku 4.5 e Sonnet 5), a regex e os
  embeddings.
- **Concorrentes** (`benchmark_intent_classifiers`):
  - `regex`: a regra de hoje. Linha de base.
  - `embed`: embeddings locais (`fastembed`), sem treino: a mensagem comparada com a descrição
    de cada intenção. Custo zero, nada sai da casa.
  - `llm:<modelo>`: um por `--llm-model` (ex.: Haiku 4.5 e o modelo do dia), lista em JSON.
  - `jev`: TypeSafe Jev, uma pergunta sim/não por intenção numa chamada só.
- **Placar:** conjunto exato (acertou todas e nenhuma a mais) · **exato nas mensagens com 2+
  intenções** · precisão · cobertura · F1 · **cobertura das sensíveis** · o que cada um deixou
  passar · latência · custo por 1.000 mensagens · falhas. Com 30 mensagens conferidas, o ciclo
  mede sozinho, no máximo uma vez por semana, e guarda o placar em Admin → Clientes → **Placar
  das intenções** (só números, sem texto de cliente; fica depois que as mensagens vencem).

## 4. Privacidade (LGPD), por construção

- **Nenhuma cópia de texto.** A amostra aponta para a `ConversationMessage` (CASCADE): apagar a
  mensagem, por retenção ou pedido do titular, apaga a amostra junto.
- **Sempre redigido.** Quem rotula e quem classifica vê o texto passado por
  `redact_observation_text` (CPF, cartão, contato, endereço, detalhe de alergia e de saúde
  omitidos). A intenção sobrevive: "[alergia: detalhe omitido]" ainda diz alergia.
- **Provedor externo só com decisão do dono.** `llm` e `jev` mandam o texto redigido para fora
  e só entram se o provedor estiver em `SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED`. Decisão de
  23/09: **`anthropic` aprovado** (já recebe o texto cru quando o concierge atende; é o default)
  e **`typesafe` (Jev) fora** até o dono decidir (fornecedor novo, termos não avaliados, cadastro
  pausado). `regex` e `embed` rodam sem isso.
- **A pressa é a certa.** A mensagem observada vence em dias e leva a amostra junto; o ciclo
  sorteia só dentro da janela de retenção e pré-marca na hora, para a conferência caber nela.

## 5. O que precisa da casa

Só conferir. Decisões já tomadas pelo dono em 23/09: o vocabulário (§3), a Anthropic aprovada e
o Jev fora (§4), e o corpus é a observação que já roda. Nenhum comando de console:

- a migração sobe no release; o vocabulário, o sorteio, a pré-marcação e o placar rodam no
  `maintenance_worker`;
- **a equipe confere** em Admin → Clientes → Mensagens para rotular (filtro "sugerida"): leva
  segundos por mensagem, e a ação em lote confirma as que estão certas de uma vez;
- **o placar aparece sozinho** em Admin → Clientes → Placar das intenções quando houver 30
  conferidas.

Opcional, se o ritmo de conferência não couber em 7 dias: subir
`CONCIERGE_OBSERVATION_RETENTION_DAYS` (até 30). E os embeddings só entram no placar com
`fastembed` na imagem, que é decisão à parte.

## 6. Rodar à mão (opcional)

```bash
python manage.py run_intent_pilot                 # um ciclo, igual ao do worker
python manage.py run_intent_pilot --measure-now   # placar já, sem esperar a semana
python manage.py sample_intent_messages --limit 200 --days 7
python manage.py benchmark_intent_classifiers --llm-model claude-haiku-4-5 --csv /tmp/intencoes.csv
```

## 7. Critério de decisão (proposto)

- **Sensíveis primeiro:** nenhum uso automático com cobertura das sensíveis abaixo de 95%.
- Para o B.I. da mensageria (uso 2): F1 ≥ 0,85 basta, porque o erro se dilui no agregado.
- Para a transferência (uso 1): conjunto exato ≥ 80% **e** sensíveis ≥ 95%; e mesmo assim
  somando à regex, nunca substituindo de cara.
- Para economizar o agente (uso 3): só com precisão ≥ 95% na intenção desviada. Responder
  errado custa mais que o agente.
- Empate: o que não sai da casa (`embed`) > o que já sai (`llm`) > fornecedor novo (`jev`).

## 8. O que não se sabe ainda

- **Volume real de mensagens:** depende de quantas perguntas a observação captura por dia; o
  teto de 40 sorteios/dia se ajusta em `intent_pilot.DAILY_SAMPLE_CAP`.
- **Formato da resposta do Jev** para perguntas sim/não: `parse_jev_boolean` foi escrito pela
  descrição pública e falha dizendo as chaves que recebeu.
- **Calibração do `embed`:** similaridade não é probabilidade; o corte (`--min-similarity`,
  default 0,45) se escolhe pelo CSV da primeira rodada.
- **A redação tira sinal?** "pago no pix amanhã" vira "pago no [dado financeiro ou segredo
  omitido]". Nenhuma intenção da lista depende disso, mas se "pagamento" entrar na lista, rever.
