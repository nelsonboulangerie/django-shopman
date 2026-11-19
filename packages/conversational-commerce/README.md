# conversational-commerce

Núcleo genérico de comércio conversacional: contratos, máquina de estados,
portas, política, contrato de efeito, resposta com prova, adaptadores falsos
e a suíte de conformidade. Qualquer canal, qualquer modelo, qualquer sistema
de comércio por trás.

**Estado:** D1 fechado (F0 a F11 do plano do framework,
`docs/plans/COMERCIO-CONVERSACIONAL-FRAMEWORK-PLANO.md`). Os 17 contratos, o
catálogo de 16 movimentos e o perfil, as portas com os falsos, o episódio, a
política, a resposta com prova, o turno, o contrato de efeito, os compromissos, a
recomendação, os resultados e a memória declarada existem, com as seis jornadas de
referência (J1 a J6) e os 40 testes de conformidade (K01 a K40) marcados. A
especificação inteira está `vigente` (`spec/`). O que falta é o lado de cada
adaptador: os K de escopo `adapter` e `real_mechanism` só valem para uma
implementação rodados no mecanismo dela (`spec/11-conformance.md`, seção 6).

## O que o pacote é

- **Python puro**, `requires-python >= 3.12`, **zero dependências**. Não
  importa Django, SDK de modelo, SDK de canal nem o sistema de quem o usa.
- **Import:** `conversational_commerce`. **Distribuição:** `conversational-commerce`.
- **Extra `[testing]`:** `pytest`, para quem roda a suíte de conformidade
  contra o próprio adaptador.
- Quem fala com o mundo (canal, modelo, pedidos, estoque, pagamento) é o
  **adaptador**, que implementa as portas do pacote e prova que as implementa
  rodando a suíte de conformidade.

A regra de corte: o que não puder ser dito sem nomear uma empresa, um canal,
um framework web ou um ramo de negócio pertence ao adaptador ou ao perfil, não
a este pacote.

## Guardas

| Prova | Onde |
|---|---|
| Nenhum import fora da biblioteca padrão (K38) | `conversational_commerce/tests/test_k38_no_infrastructure.py` |
| A suíte roda sem rede | fixture `autouse` em `conversational_commerce/tests/conftest.py` |
| Instala e passa a própria suíte num venv sem Django | `python scripts/wheel_suite.py conversational-commerce` (na raiz do monorepo) |
| O critério de saída do D1: a matriz fecha, as seis jornadas juntas, a especificação vigente | `conversational_commerce/tests/test_d1_exit.py` |
| A matriz teste × invariante | `python -m conversational_commerce.testing.matrix --check` |

## Rodar

Na raiz do monorepo:

```bash
make test-conversational-commerce
```

O alvo roda dentro deste diretório com `PYTHONPATH` apontando para cá, para
nunca pegar uma instalação editável de outro checkout, e com `-p no:django`.

## Especificação e decisões

- Especificação: [`spec/00-index.md`](spec/00-index.md).
- Decisão de arquitetura: [ADR-049](../../docs/decisions/adr-049-comercio-conversacional-pacote-puro.md).
- Referência: `docs/research/INTELIGENCIA-COMERCIO-CONVERSACIONAL-v2.md`.

## Licença

FSL-1.1-ALv2, a mesma dos pacotes irmãos. Ver [LICENSE.md](LICENSE.md).
