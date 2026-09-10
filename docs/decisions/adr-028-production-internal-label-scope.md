# ADR-028 — Pesagem e identificação interna não são rótulo de venda

**Data:** 2026-09-10  
**Status:** aceito para o fluxo interno; enquadramento local pendente de validação pela VISA/RT  
**Escopo:** Preparação, documentos congelados de impressão e revisão de parâmetros legais

## Contexto

A tela de Preparação nasce do planejamento. Ela produz dois artefatos diferentes:

1. uma instrução de pesagem por ingrediente;
2. uma identificação do preparo prevista para o dia selecionado.

Nenhum deles mede conteúdo líquido real nem contém todos os campos de um rótulo
comercial. Chamá-los simplesmente de “etiqueta do produto” permitiria que um
papel interno fosse aplicado à venda, dando aparência de conformidade a um
documento incompleto.

## Decisão

- Todo documento deste fluxo declara `legal_scope=internal_only_not_for_sale`.
- O papel mostra de forma visível **USO INTERNO — NÃO É RÓTULO DE VENDA**.
- A pesagem mantém o alvo operacional em gramas como informação dominante.
  Quando há `MaterialConversion` canônica, ativa e sem fornecedor, a contagem
  aproximada aparece apenas como referência (`102 g`; abaixo, `≈ 2 ovos`). O
  cliente não calcula nem persiste essa equivalência.
- `target_g` e `total_weight_display` são alvos de produção. Nunca recebem o
  nome “peso líquido”; conteúdo líquido comercial exige medição real com tara
  descontada.
- A identificação interna traz designação humana, SKU, data de preparo prevista
  e validade. A validade tem precedência ficha técnica → cadastro canônico do
  SKU. Se nenhuma regra responsável existir, a impressão explícita falha
  fechada; o antigo fallback D+1 foi removido. `0` é valor válido e significa o
  mesmo dia.
- O documento e seu hash congelam a equivalência e a regra de validade usadas.
  Alteração posterior no cadastro não reescreve uma via já emitida.
- Rótulo de venda é outro contrato e outro renderer. Ele deverá receber peso
  líquido aferido, origem, lote, ingredientes e demais campos aplicáveis; não
  será uma evolução silenciosa deste documento interno.

## Base normativa conferida

- [RDC 216/2004](https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2004/res0216_15_09_2004.html),
  especialmente itens 4.8.17, 4.8.18 e 4.9.1: para alimento preparado
  armazenado/aguardando transporte, identificação mínima por designação, data
  de preparo e prazo de validade; sob refrigeração a 4 °C ou menos, prazo
  máximo de cinco dias.
- [RDC 727/2022 consolidada](https://anvisalegis.datalegis.net/action/ActionDatalegis.php?acao=abrirTextoAto&cod_menu=8542&cod_modulo=310&link=S&numeroAto=00000727&orgao=RDC/DC/ANVISA/MS&seqAto=002&tipo=RDC&valorAno=2022),
  arts. 2º, 7º–8º e 28–32: requisitos gerais do alimento embalado na ausência
  do consumidor.
- [RDC 429/2020 consolidada](https://anvisalegis.datalegis.net/action/ActionDatalegis.php?acao=abrirTextoAto&cod_menu=9434&cod_modulo=310&numeroAto=00000429&orgao=RDC/DC/ANVISA/MS&seqAto=000&tipo=RDC&valorAno=2020)
  e IN 75/2020: enquadramento da informação nutricional e suas exceções
  específicas.
- [Portaria Inmetro 249/2021](https://anmlegis.datalegis.net/action/ActionDatalegis.php?acao=abrirTextoAto&cod_menu=6783&cod_modulo=405&link=S&numeroAto=00000249&orgao=INMETRO/ME&seqAto=000&tipo=POR&valorAno=2021):
  conteúdo nominal de produto pré-medido não se confunde com alvo de receita.

O levantamento não substitui orientação jurídica. A RDC 216 permite
complementação estadual/municipal. Transferência para outra loja/filial e a
fronteira da Lei 10.674/2003 para produção artesanal devem ser confirmadas por
responsável técnico ou pela vigilância sanitária local antes de qualquer
dispensa.

## Consequências e próximos limites

- O operador não informa equivalência nem validade durante a pesagem.
- O gestor mantém validade na ficha técnica; a rotina já existente cobra
  revisão periódica dos parâmetros normativos.
- A data da identificação atual ainda é a data selecionada no planejamento.
  Se o preparo mudar de dia, a etiqueta deve ser descartada e reemitida. Um
  futuro fluxo de recipiente/lote factual deverá nascer do gesto “preparo
  pronto”, usar horário real do servidor e emitir uma etiqueta por recipiente;
  ele não pode ser inferido apenas de uma ordem planejada.

