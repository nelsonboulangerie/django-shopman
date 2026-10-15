# Laudo de fechamento — superfícies no mesmo trilho

Data da autópsia e implementação: 14/10/2026.

## Causa do Marketing “sair da linha”

Não havia uma causa única dentro do domínio de Marketing. O app tinha virado uma
fábrica paralela: três configurações Playwright, servidor de desenvolvimento no
gate, mock Python particular, job monolítico em outro sistema operacional e 82
goldens misturando comportamento, geometria e rasterização.

O incidente da nova oferta revelou duas falhas distintas:

1. o teste aceitava a primeira aparição do diálogo como prontidão definitiva; uma
   remontagem tardia podia removê-lo antes da captura, sem uma asserção funcional
   depois da estabilização;
2. mesmo com a cena correta e estável, trocar `nuxt dev` pelo artefato de produção
   produziu 6.001 pixels de diferença apenas na rasterização do texto, repetidos de
   forma idêntica em 20 de 20 execuções. O golden estava classificando ruído visual
   como falha de produto.

## Experimentos

| Experimento | Resultado | Conclusão |
|---|---:|---|
| Nova oferta, servidor dev, mesmo commit | 20/20 com o diálogo presente | O flake não é reproduzível por repetição simples; não autoriza baseline nova. |
| Nova oferta, build de produção, golden antigo | 20/20 com diálogo presente; 20/20 com os mesmos 6.001 pixels de texto | Build e golden mediam coisas diferentes de forma determinística. |
| Nova oferta, build de produção, barreira funcional e evidência | 100/100, retry zero | Critério de aceite do incidente satisfeito. |
| Mutação remove o sujeito durante a estabilização | teste reprova | A corrida deixa de aparecer apenas como diff de pixels. |

Hipóteses do WP: prontidão insuficiente, excesso de goldens, harness particular e
ausência de contrato foram confirmados. O modo dev era uma divergência real e
desnecessária, mas não foi isolado como causa única do flake em 20 repetições; foi
eliminado porque não representa o artefato publicado.

## Trilho implantado

- `surfaces/contracts.json` é o manifesto versionado das 11 entradas (dez apps e
  o `operator-kit`), com comandos, capabilities, runner, browser, assinaturas e
  exceções com responsável e vencimento.
- `scripts/surface_contract.mjs` valida o contrato, gera as matrizes da CI e executa
  fases locais pelo mesmo nome que a CI usa.
- A CI deixou de decidir por `matrix.app == <nome>`; instalação da layer, browser,
  visual, geometria, SSR, PWA, a11y, segurança e audit são capabilities.
- Todo gate visual declarado constrói e serve o artefato de produção. B.I., POS,
  Kitchen Sink, Marketing e catálogo do kit deixaram de usar `nuxt dev`.
- Ao passar o POS pelo artefato real, o gate deixou de medir botões responsivos
  ocultos, passou a reconhecer os modos `dia`/`semana` e encontrou ações visíveis
  de 32 px no detalhe; as ações foram elevadas ao alvo canônico de 44 px.
- O Marketing passou de três configs para um harness, compartilhando políticas do
  runner visual do kit.
- O contrato limita cada app a oito assinaturas. Marketing caiu de 82 para seis;
  POS declara as quatro que já possuía. As demais cenas continuam com asserções de
  comportamento, acessibilidade, rótulos, overflow e evidência diagnóstica.
- A cena de ofertas publica `data-surface-ready="offers:ready"`; o helper verifica
  marcador e diálogo antes e depois de fontes e dois frames de layout.

## Exceções temporárias

Hub, KDS e Compras ainda não separam um fluxo funcional próprio da matriz visual.
Isso agora é explícito no manifesto, com responsável `engineering` e vencimento em
14/11/2026. Uma exceção vencida reprova o contrato; ela não pode desaparecer num
comentário ou num `if` do workflow.

## Resultado

“Mesmo trilho” passou a significar a mesma fábrica e o mesmo vocabulário de fases,
não telas iguais. Diferenças de domínio continuam nos testes de cada app; diferenças
de boot, retry, build, evidência e seleção da CI precisam estar no contrato.
