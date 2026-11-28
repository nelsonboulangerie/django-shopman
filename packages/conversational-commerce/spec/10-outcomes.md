# Recomendação, exposição, resultado e memória declarada

> **Estado:** vigente
> **Dono:** F10

Responde: quando a casa pode recomendar; o que conta como exposição; como o resultado é medido
sem transformar o que falta em número; como uma correção substitui o anterior; o que se guarda
do cliente e como a correção alcança os derivados. A fonte é o código:
`conversational_commerce/engine/moves/recommend.py`, `conversational_commerce/ledger/exposures.py`,
`conversational_commerce/ledger/outcomes.py`, `conversational_commerce/memory/`,
`conversational_commerce/evaluation/` e o contexto comercial de `engine/turn.py`. A forma de
`ExposureEvent`, `OutcomeEvent` e `MemoryItem` é do `01-contracts.md`.

Derivado de: v2 4.3, 5.5, 6.1, 6.2 e 8.5 e o plano do framework, seção 3.9 (F10).

## 1. A recomendação (`recommend`, família `commerce`, A0)

Só quando o cliente pede (ato `ask_recommendation`) e diz o que precisa (`need` nos campos do
ato). As precondições do catálogo, todas lidas da situação que o turno monta:

| Precondição | O turno preenche com |
|---|---|
| `explicit_need` | a necessidade declarada não é vazia |
| `advisor_constraint` | há item no catálogo que atende **cada** exigência declarada (`policy.advisor`); exigência desconhecida no item é não atendida |
| `unsolicited_within_limit` | zero: no D1 toda recomendação é pedida |
| `commercial_context_clear` | sem caso aberto no episódio nem reclamação nesta mensagem; sem atrito alto (`signals.friction`); sem compromisso aberto com prazo vencido |
| `refusal_respected` | a memória declarada não guarda a recusa do cliente |

O nome e o preço saem do fato lido do item (`read_item`), nunca do modelo: a resposta é o molde
`recommend.item` com os espaços travados no fato. A família `commerce` cede a todas as outras, e
o caso aberto suspende toda oferta (`suspended_by_open_problem`, F5), no turno e enquanto o caso
estiver aberto no episódio.

**A recusa segura nova oferta até o cliente mudar de ideia.** "Sem sugestões" (`decline_offers`)
vira memória declarada (`offers.declined = true`, fonte o evento); enquanto vale, a
recomendação fica inelegível com `customer_declined_offers`, e a limitação diz isso ao cliente.
"Pode sugerir" (`accept_offers`) é outro registro, que substitui o primeiro.

[DECIDIDO] Pedir uma recomendação depois de recusar não desfaz a recusa: só o ato de mudar de
ideia desfaz. A resposta diz como, em vez de adivinhar se o pedido novo foi a mudança.

## 2. Exposição (`ExposureLedger`)

Atribuição ao tratamento (a decisão, com a seleção), exposição efetiva (este livro) e execução
(os recibos do `08-effect.md`) são três registros separados. O turno e as retomadas gravam a
exposição devolvida pelo canal, e `Engine.observe_delivery` grava cada estado novo como registro
novo. Só `delivered` e `read` são exposição efetiva (`exposed`): o provedor aceitar a mensagem
não é o cliente tê-la recebido, e "lida" só existe quando o canal a observa (K18).

## 3. Resultado (`OutcomeLedger`)

| Regra | Como |
|---|---|
| Fonte independente (N20) | o livro recusa resultado cuja fonte é o próprio agente (`self_reported_outcome`) |
| Janela aberta é censura (K33, N21) | a porta devolve `censored`; o livro recusa `observed` com janela aberta; censurado não entra na média |
| Desconhecido não vira zero (N21) | `unknown` é contado à parte; `summarize` devolve `mean = None` sem nada observado |
| Correção substitui (K35, N14) | o registro que `supersedes` passa a valer (`current`); o anterior fica no histórico (`chain`); cada registro só é substituído uma vez |

## 4. Custo e comparação econômica (`evaluation`)

Modelo sem preço cadastrado tem custo desconhecido (`Unavailable`), nunca zero. `compare_costs`
veta a comparação (`cost_unknown:<braço>`) quando algum consumo de algum braço não tem custo,
e também quando as moedas diferem. Comparar o que custa com o que não se sabe daria vantagem a
quem não declarou preço (K34).

## 4.1 Placar de conversa (`evaluation.conversation`)

A régua de mensagem mede se a casa entendeu; esta mede se o cliente saiu atendido. O adaptador
traduz cada turno do cliente em `TurnEvidence` (respondeu, silêncio legítimo, lastro, próximo
passo, frase repetida, se pedia dado vivo ou ação) e `score` conta. Desfecho por turno, nesta
ordem: `silent` (falou e ninguém respondeu, sem equipe com a conversa), `unbacked` (afirmou sem
lastro), `dead_end` (respondeu com lastro e deixou o cliente sem próximo passo), `useful`.
Silêncio legítimo fica fora da conta. Lastro desconhecido (`backed=None`) conta à parte e
impede o "pronto"; taxa sem turno é `None`, nunca zero.

`Scorecard.meets(useful_at_least=0.9)` é o alvo de pronto: nenhum sem lastro, nenhum silêncio,
nenhum lastro desconhecido e útil na fração pedida.

A alternativa de mercado entra como `IncumbentProfile` (lê dado vivo?, age no comércio?,
responde texto livre neste canal?), e `incumbent_reach` diz, por turno, se ela alcançaria um
atendimento útil ou o primeiro motivo por que não. É comparação por capacidade declarada, não
por execução: prova onde a alternativa nem chega, nunca que ela erraria onde chega. O leitor
de língua (o que é "próximo passo" em português) é do adaptador.

## 5. Memória declarada (`memory.MemoryStore`)

Na primeira versão só existem a memória de trabalho (o estado de diálogo, `04-episode.md`) e a
declarada: o que o cliente afirmou, com fonte, finalidade e validade. Nada inferido entra
(`not_declared`).

- **Corrigir é registro novo que substitui**; o corrigido fica no histórico e nunca reaparece
  em recuperação (`recall`) nem em resumo (K28).
- **Vencido não se lembra**: `valid_until` passado sai da recuperação e dos resumos.
- **Derivado segue a origem**: o resumo guarda os itens de que nasceu e é refeito quando um
  deles foi corrigido ou venceu, nunca servido velho.
- **Categoria sensível nunca é lembrada em silêncio**: só com a confirmação do cliente.
- **Texto de memória é dado** (N23): entra em situação ou em espaço travado, nunca em pedido a
  modelo.
- Em `shadow`, nada se guarda.

Preferência inferida é corte do plano (fora do F10).

## 6. Prova

`make test-conversational-commerce`, em `conversational_commerce/tests/outcomes/`:

| Prova | Escopo |
|---|---|
| J6 de ponta a ponta: recomendação, recusa, oferta segurada, mudança de ideia, recomendação | núcleo |
| K28 memória corrigida ou vencida não reaparece em recuperação nem em resumo | `core` |
| K33 janela aberta: censurado, não zero | `adapter` |
| K34 modelo sem preço: custo desconhecido, comparação vetada | `core` |
| K35 fonte externa corrige: registro novo que substitui, histórico preservado | `adapter` |
| Placar de conversa: ordem dos desfechos, lastro desconhecido à parte, alcance da alternativa | núcleo |
| Restrição de conselheiro: sem item que atenda, sem necessidade declarada, caso aberto no episódio | núcleo |
| Exposição: aceito não é exposto; entregue é; cada estado é registro | núcleo |
| Fonte do próprio agente recusada; desconhecido contado à parte; sombra não guarda memória | núcleo |

K33 e K35 são `adapter`: o adaptador real repete com a fonte de resultados dele.
