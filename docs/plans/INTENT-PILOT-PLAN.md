# INTENT-PILOT-PLAN: piloto de intenções nas mensagens de clientes

> **Status: 🧪 ferramenta pronta; falta gabarito e três decisões do dono (§5).** Pedido do dono
> em 23/09/2026: "tenho interesse [...] sobretudo em reconhecer intenções dos clientes na
> mensageria (no plural mesmo)". Irmão do [BI-JEV-PILOT](BI-JEV-PILOT.md), que mede o mesmo tipo
> de ferramenta no de-para de produto. Nada aqui muda o concierge: o piloto só mede.

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
  inicial (`setup_intent_categories`) é **proposta**, não decisão:

  | ref | nome | sensível |
  |---|---|---|
  | `order` | Pedido | |
  | `product_question` | Dúvida de produto | |
  | `hours_delivery` | Horário, retirada ou entrega | |
  | `order_status` | Status do pedido | |
  | `complaint` | Reclamação | ✔ |
  | `allergy` | Alergia ou restrição | ✔ |
  | `special_order` | Encomenda especial | |
  | `human` | Falar com uma pessoa | ✔ |

  "Sensível" = deixar passar custa caro; o placar mede essas à parte.
- **Gabarito = a casa rotula.** `sample_intent_messages` sorteia mensagens de cliente;
  Admin → Clientes → **Mensagens para rotular** mostra uma por vez, com caixinhas: marca **todas**
  as intenções (ou nenhuma) e salva, e a tela já abre a próxima. Salvar assina quem e quando.
  Ininteligível → ação "Pular".
- **Concorrentes** (`benchmark_intent_classifiers`):
  - `regex`: a regra de hoje. Linha de base.
  - `embed`: embeddings locais (`fastembed`), sem treino: a mensagem comparada com a descrição
    de cada intenção. Custo zero, nada sai da casa.
  - `llm:<modelo>`: um por `--llm-model` (ex.: Haiku 4.5 e o modelo do dia), lista em JSON.
  - `jev`: TypeSafe Jev, uma pergunta sim/não por intenção numa chamada só.
- **Placar:** conjunto exato (acertou todas e nenhuma a mais) · **exato nas mensagens com 2+
  intenções** · precisão · cobertura · F1 · **cobertura das sensíveis** · cobertura por
  intenção · latência p50/p95 · custo por 1.000 mensagens · falhas. `--csv` caso a caso, **sem
  texto de cliente** (só o número da amostra; o texto se lê no Admin).

## 4. Privacidade (LGPD), por construção

- **Nenhuma cópia de texto.** A amostra aponta para a `ConversationMessage` (CASCADE): apagar a
  mensagem, por retenção ou pedido do titular, apaga a amostra junto.
- **Sempre redigido.** Quem rotula e quem classifica vê o texto passado por
  `redact_observation_text` (CPF, cartão, contato, endereço, detalhe de alergia e de saúde
  omitidos). A intenção sobrevive: "[alergia: detalhe omitido]" ainda diz alergia.
- **Provedor externo só com decisão escrita.** `llm` e `jev` mandam o texto redigido para fora;
  ficam fora do placar até `SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED=true`. É a regra do Marketing
  (`SHOPMAN_MARKETING_AI_PROVIDER_POLICY_APPROVED`): credencial sozinha nunca liga provedor.
  `regex` e `embed` rodam sem isso.

## 5. O que precisa do dono, em ordem

1. **Revisar a lista de intenções** (Admin → Clientes → Intenções), depois do
   `setup_intent_categories`. Renomear, reescrever descrição (os classificadores leem a
   descrição), marcar sensível, desativar, criar. É a decisão de produto do piloto.
2. **Decidir se texto de cliente redigido pode ir a provedor externo no piloto**, e para quem:
   - Anthropic (`llm`): já recebe o texto **cru** quando o concierge está em modo assistente.
   - TypeSafe (`jev`): fornecedor novo, sem termos avaliados (retenção, treino, transferência
     internacional). Cadastros pausados desde 22/09 de qualquer forma.
   Se sim: `SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED=true` no ambiente. Se não: o piloto mede
   `regex` × `embed`, que já responde se dá para fazer em casa.
3. **Rotular ~200 mensagens** (ou delegar a alguém da equipe com acesso ao Admin). Leva perto de
   uma hora: a tela anda sozinha para a próxima.

## 6. Como rodar (staging)

```bash
python manage.py migrate storefront
python manage.py setup_intent_categories
python manage.py sample_intent_messages --limit 200
# ... rotulagem no Admin ...
pip install fastembed   # não está na imagem; some no próximo deploy
python manage.py benchmark_intent_classifiers --csv /tmp/intencoes.csv
# com a decisão do §5.2:
python manage.py benchmark_intent_classifiers --llm-model claude-haiku-4-5 --llm-model claude-sonnet-5 --csv /tmp/intencoes.csv
```

Se `sample_intent_messages` não achar mensagem, o concierge ainda não recebeu texto de cliente
naquele ambiente, e o piloto espera o canal ter volume.

## 7. Critério de decisão (proposto)

- **Sensíveis primeiro:** nenhum uso automático com cobertura das sensíveis abaixo de 95%.
- Para o B.I. da mensageria (uso 2): F1 ≥ 0,85 basta, porque o erro se dilui no agregado.
- Para a transferência (uso 1): conjunto exato ≥ 80% **e** sensíveis ≥ 95%; e mesmo assim
  somando à regex, nunca substituindo de cara.
- Para economizar o agente (uso 3): só com precisão ≥ 95% na intenção desviada. Responder
  errado custa mais que o agente.
- Empate: o que não sai da casa (`embed`) > o que já sai (`llm`) > fornecedor novo (`jev`).

## 8. O que não se sabe ainda

- **Volume real de mensagens** no staging e em produção: depende de o concierge estar ligado.
- **Formato da resposta do Jev** para perguntas sim/não: `parse_jev_boolean` foi escrito pela
  descrição pública e falha dizendo as chaves que recebeu.
- **Calibração do `embed`:** similaridade não é probabilidade; o corte (`--min-similarity`,
  default 0,45) se escolhe pelo CSV da primeira rodada.
- **A redação tira sinal?** "pago no pix amanhã" vira "pago no [dado financeiro ou segredo
  omitido]". Nenhuma intenção da lista depende disso, mas se "pagamento" entrar na lista, rever.
