# Especificação do conversational-commerce: índice

> **Estado:** vigente
> **Dono:** F0

Este índice diz **em que ordem ler** e **que pergunta cada arquivo responde**. Ele não
guarda estado: o estado (`rascunho`, `em revisão` ou `vigente`) e o WP dono moram no
cabeçalho de cada arquivo, para que nenhuma onda precise editar este índice para avançar
o próprio arquivo.

Arquivo listado e ainda ausente é um WP que ainda não chegou. Enquanto um arquivo não
estiver `vigente`, vale a seção correspondente do plano
(`docs/plans/COMERCIO-CONVERSACIONAL-FRAMEWORK-PLANO.md`, seção 3); quando estiver, ele
é a verdade e o plano vira ponteiro. Divergência com a pesquisa de referência
(`docs/research/INTELIGENCIA-COMERCIO-CONVERSACIONAL-v2.md`) se anota no arquivo como
`[DIVERGE]`, nunca se esconde.

## Ordem de leitura

| # | Arquivo | Responde | WP dono |
|---|---|---|---|
| 0 | `00-index.md` | Em que ordem ler, e onde mora cada resposta | F0 |
| 1 | `01-contracts.md` | Quais são os contratos, como se versionam, qual é a forma canônica e o hash, onde estão os vetores | F1 |
| 2 | `02-catalog-profile.md` | Que movimentos existem, com que precondições; níveis de autonomia; escada de identidade; o perfil; códigos de inelegibilidade e erros estáveis | F2 |
| 3 | `03-ports.md` | Quais portas o núcleo pede, com que operações e garantias; `capabilities()`; os adaptadores falsos e as falhas injetáveis | F3 |
| 4 | `04-episode.md` | O que é um episódio e uma necessidade; posse e época; correlação; a máquina de estados e as esperas | F4 |
| 5 | `05-policy.md` | O que é admissível, prioritário e melhor; quando perguntar; limites de contexto; seleção e registro da decisão | F5 |
| 6 | `06-reply.md` | Como a resposta é planejada em partes, com que lastro, em que moldes, e como a saída é verificada | F6 |
| 7 | `07-turn.md` | Os passos do turno, os tetos, a queda sem modelo, os ambientes `test`, `shadow` e `live` | F7 |
| 8 | `08-effect.md` | A cadeia do efeito, suas propriedades, as combinações de recibo, a reconciliação e a guarda do ponto de efeito | F8 |
| 9 | `09-commitments.md` | Promessa e caso: estados, prazos, escalonamento, contingência | F9 |
| 10 | `10-outcomes.md` | Exposição, resultado, censura, supersessão e memória declarada | F10 |
| 11 | `11-conformance.md` | Como um adaptador roda a suíte; o escopo de cada teste K; a matriz gerada | F3 cria, F11 fecha |

## Fora da especificação, e onde mora

- **Decisão de arquitetura:** `docs/decisions/adr-049-comercio-conversacional-pacote-puro.md`.
- **Vetores de teste:** com o código, em `conversational_commerce/vectors/` (F1).
- **Matriz teste × invariante:** gerada a partir dos testes (F3, F11), nunca escrita à mão.
- **Decisão do dono:** linha do perfil, com dono e data (F2), nunca neste diretório.
