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
comparado ao fuzzy de hoje e ao LLM que o projeto já usa?**

## Como mede

`manage.py benchmark_alias_matchers` (referência em
[commands.md](../reference/commands.md#benchmark_alias_matchers)):

- **Gabarito**: os `ProductAlias` **confirmados** da origem. Confirmado com produto = resposta
  certa; confirmado sem produto = "fora do catálogo" (o concorrente acerta dizendo "nenhum destes").
  Proposta não confirmada não entra: é palpite da máquina.
- **Mesma lista curta para todos**: os K produtos de nome mais parecido (default 10). Jev e LLM
  escolhem entre eles ou "nenhum destes". A cobertura da lista é o teto de acerto dos dois e sai no
  relatório.
- **Só o nome**: SKU exato continua ganhando antes de qualquer concorrente; a dúvida mora no nome.
- **Placar por concorrente**: acerto; quantos aceitaria sozinho (confiança ≥ 0,9) e **quantos
  desses errados**, que são o erro que passaria sem ninguém ver; latência p50/p95; tokens; custo
  total e por 1.000 itens; falhas. `--csv` grava caso a caso para auditoria.
- **Dados**: só nome de produto (origem e catálogo). Nenhum dado de cliente sai do sistema.

## Como rodar (staging)

1. Confirmar de-paras no Admin → B.I. → De-paras. **O gabarito é o que a casa confirmou**, e sem
   gabarito o comando recusa. Umas 100 a 200 linhas variadas bastam.
2. Credenciais no ambiente (decisão do dono): `JEV_API_KEY` (conta TypeSafe);
   `AI_ASSIST_API_KEY` já existe para o LLM.
3. Primeiro uma rodada de fumaça com o Jev, para validar o formato da resposta:
   `benchmark_alias_matchers --matcher jev --limit 5`.
4. Rodada completa:
   `benchmark_alias_matchers --limit 200 --llm-price-in <US$/M> --llm-price-out <US$/M> --csv /tmp/piloto.csv`.

## Critério de decisão (proposto)

O Jev entra no `suggest_aliases` (como opinião a mais na proposta, **nunca** confirmando) se, no
gabarito:

- aceitaria sozinho ≥ 50% dos casos com **zero** erros aceitos a 0,9, e
- acerta mais que o fuzzy com custo por 1.000 itens desprezível (centavos) e p95 < 1 s.

Se entrar, a integração segue a ADR-001: adapter só com duas implementações reais (fuzzy e Jev),
credencial opcional, e o fuzzy continua sendo o caminho sem chave.

## O que não se sabe ainda

- **Formato exato da resposta do Jev.** O pedido segue a descrição pública (`POST /v1/systemone`,
  `state` + `questions`, escolha = chave → descrição com `other`), mas a referência da API não
  estava acessível deste ambiente. `parse_jev_response` aceita os nomes de campo citados na
  documentação pública e, se não reconhecer a resposta, falha listando as chaves recebidas. A
  rodada de fumaça do passo 3 existe para isso.
- **Preço do LLM**: entra por argumento, porque depende do modelo em `AI_ASSIST_MODEL`.
