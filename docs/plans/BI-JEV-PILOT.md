# BI-JEV-PILOT: piloto do Jev no de-para de produto do B.I.

> **Status: 🧪 ferramenta de medição pronta; a medição roda no staging.** Aprovado pelo dono em
> 23/09/2026 ("vamos fazer esse piloto do De-Para do BI"). Nada aqui muda o fluxo do
> `suggest_aliases`: o piloto só mede. Irmão de [BI-DATA-FOUNDATION-PLAN](BI-DATA-FOUNDATION-PLAN.md) (P1).

## A pergunta

O `suggest_aliases` propõe o de-para produto Yooga → `offerman.Product` por nome parecido
(`rapidfuzz`), e **toda** proposta espera uma pessoa no Admin (229 no staging em 19/08). O Jev
(TypeSafe, lançado em 15/09/2026) é um modelo de decisão: recebe opções tipadas e devolve a
escolha com probabilidade, a US$ 0,042 por milhão de tokens de entrada, saída grátis.

A pergunta que o piloto responde é: **o Jev acerta o suficiente, com confiança calibrada, para
que a fila humana encolha sem que um erro passe despercebido? E a que custo e em quanto tempo,
comparado ao fuzzy de hoje, ao LLM que o projeto já usa (no modelo do dia e no Haiku) e a
embeddings locais, que custam zero?** Os dois últimos entraram a pedido do dono em 23/09 ("existiria
alguma alternativa similar, mais barata que LLMs?") e, ao contrário do Jev, não dependem de cadastro:
dá para medir já.

## Como mede

`manage.py benchmark_alias_matchers` (referência em
[commands.md](../reference/commands.md#benchmark_alias_matchers)):

- **Gabarito**: os `ProductAlias` **confirmados** da origem. Confirmado com produto = resposta
  certa; confirmado sem produto = "fora do catálogo" (o concorrente acerta dizendo "nenhum destes").
  Proposta não confirmada não entra: é palpite da máquina.
- **Mesma lista curta para Jev e LLM**: os K produtos de nome mais parecido (default 10). Os dois
  escolhem entre eles ou "nenhum destes". A cobertura da lista é o teto de acerto deles e sai no
  relatório. Os **embeddings** procuram no catálogo inteiro, por significado ("pão de chocolate" →
  "Pain au Chocolat"), e podem achar o que o fuzzy nem listou.
- **Concorrentes**: `fuzzy` · `jev` · `llm:<modelo>` (um por `--llm-model`; preço de `LLM_PRICES`,
  tabela pública de 24/06/2026) · `embed` (`fastembed`, modelo multilíngue aberto de ~0,2 GB, roda
  no servidor, nada sai da casa).
- **Só o nome**: SKU exato continua ganhando antes de qualquer concorrente; a dúvida mora no nome.
- **Placar por concorrente**: acerto; quantos aceitaria sozinho (confiança ≥ 0,9) e **quantos
  desses errados**, que são o erro que passaria sem ninguém ver; latência p50/p95; tokens; custo
  total e por 1.000 itens; falhas. `--csv` grava caso a caso para auditoria.
- **Dados**: só nome de produto (origem e catálogo). Nenhum dado de cliente sai do sistema.

## Como rodar (staging)

1. Confirmar de-paras no Admin → B.I. → De-paras. **O gabarito é o que a casa confirmou**, e sem
   gabarito o comando recusa. Umas 100 a 200 linhas variadas bastam.
2. **Já dá para rodar, sem o Jev** (cadastros da TypeSafe pausados desde 22/09; há uma rotina
   vigiando a reabertura). No console do staging:
   `pip install fastembed` (não está na imagem; some no próximo deploy) e
   `benchmark_alias_matchers --limit 200 --llm-model claude-haiku-4-5 --llm-model claude-opus-5 --csv /tmp/piloto.csv`.
   A primeira rodada do `embed` baixa o modelo (~0,2 GB).
3. Quando o cadastro reabrir: `JEV_API_KEY` no ambiente (decisão do dono), rodada de fumaça
   `benchmark_alias_matchers --matcher jev --limit 5` para validar o formato da resposta, e a rodada
   completa de novo com o Jev no placar.

## Critério de decisão (proposto)

Um concorrente entra no `suggest_aliases` (como opinião a mais na proposta, **nunca** confirmando)
se, no gabarito:

- aceitaria sozinho ≥ 50% dos casos com **zero** erros aceitos a 0,9, e
- acerta mais que o fuzzy com custo por 1.000 itens desprezível (centavos) e p95 < 1 s.

Empate técnico se decide pelo que não sai da casa e não pede cadastro: embeddings > Jev > LLM. Se
entrar, a integração segue a ADR-001: adapter só com duas implementações reais, e o fuzzy continua
sendo o caminho sem chave nem pacote. Embeddings no caminho de produção significam `fastembed`
(e `onnxruntime`) na imagem, e isso é decisão à parte.

## O que não se sabe ainda

- **Formato exato da resposta do Jev.** O pedido segue a descrição pública (`POST /v1/systemone`,
  `state` + `questions`, escolha = chave → descrição com `other`), mas a referência da API não
  estava acessível deste ambiente. `parse_jev_response` aceita os nomes de campo citados na
  documentação pública e, se não reconhecer a resposta, falha listando as chaves recebidas. A
  rodada de fumaça do passo 3 existe para isso.
- **Preço do LLM**: tabela pública de 24/06/2026 em `LLM_PRICES`; `--llm-price-*` sobrescreve.
  O de-para não é urgente: se um LLM vencer, a Batch API da Anthropic corta o custo à metade.
- **Calibração dos embeddings**: similaridade de cosseno não é probabilidade; o `--min-similarity`
  (default 0,8) e o `--accept-at` se escolhem olhando o CSV da primeira rodada.

## Próxima frente: intenções na mensageria

O dono quer o mesmo tipo de ferramenta para reconhecer **intenções** (no plural: uma mensagem pode
pedir, perguntar horário e reclamar ao mesmo tempo) nas mensagens de clientes. É frente própria,
com plano próprio: dado de cliente, LGPD e o desenho do concierge (ADR-026) mudam as regras.
