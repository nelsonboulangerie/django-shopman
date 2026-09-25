# Inventário local dos impressos — 15/09/2026

Solicitado pela Coord Repo (tarefa 01a09be0-05f0-7562-a480-2c1c257d23cd), com autorização de Pablo para inventariar e registrar. Não autoriza publicação, CI, merge ou deploy.

## Estado verificado

- Worktree: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-print-layouts-20260912`.
- Branch: `codex/print-layouts-20260912`; HEAD `3ade610524e560106d18761551aa54127fdaa2ea`.
- Base da implementação: `eaba3d45af9e9a201ff38ca6fb03899c4a78111a`, head intermediário do PR #619.
- Nove commits não contidos nos refs remotos locais; todos aparecem com `+` em `git cherry origin/main HEAD` (sem patch equivalente em main).
- origin/main local = main consultada pela API GitHub: `ae52f96b72cbbffbc5541b61f4c560e880474586`. Não foi feito fetch nem alterado ref remoto.
- Antes deste registro: arquivos versionados limpos; apenas `output/` não rastreado. Este relatório é arquivo local adicional, sem commit.
- PR #619 está MERGED desde 12/09/2026 14:42:46 UTC, merge `4883e6015047554839045e38821780652e59f75c`, head final `9b922942b69cd0dde6cf41f3978c674897871c2c`.
- Consulta por head exato não encontrou PR desta branch. Busca de PRs relacionados e inspeção de #642, #647 e #676 não identificaram entrega equivalente. Isso não constitui auditoria exaustiva de cada patch remoto.

## Delta real preservado

35 arquivos, 2.490 inserções e 564 remoções contra a base eaba3d45a. Não contar como nossa entrega o trabalho anterior do #619.

1. Compositor operacional com modalidade, horário, endereço, observações e regras de pagamento/troco; backend raster opt-in com Barlow Semi Condensed e três estilos (34/500, 26/400, 20/400 dots/peso). Dinheiro integral com troco conhecido enfatiza TROCO PARA + Levar de troco; cartão mantém cobrança. Estado pago não manda cobrar.
2. Fonte fiscal passa a ser o XML fornecido pelo provedor, com validação estrutural, chave/ambiente/protocolo/QR e recusas; DANFE HTML e ESC/POS usam os dados autorizados, com recuperação no PDV para via do provedor. Não há validação criptográfica da assinatura nem consulta nova à SEFAZ.
3. Monograma SVG/PNG preto com transparência, fontes e licenças, configurações opcionais e documentação; nenhuma configuração de produção alterada. Renderer default continua native.
4. Gerador offline, testes e prévias antes/depois para curto, longo, pago, troco, misto, balcão e fiscal.

Arquivos novos centrais `shopman/backstage/services/print_layout.py`, `shopman/shop/services/danfe_xml.py` e `media/branding/nelson-monogram-print.svg` não existem em origin/main observado.

Commits locais, do mais antigo ao mais recente:
- df661b62e — fonte fiscal XML e redesenho inicial
- 4d833a668 — renderer raster proporcional
- 4f2b51f05 — Barlow, monograma e blocos
- 0a66c9aef — galeria sem corte em painel estreito
- 6aaed94ac — endereço e instruções de chegada separados
- d81c3dd7e — simplificação de troco na entrega em dinheiro
- c96520216 — três estilos mais leves
- 1d54c5bb4 — registro da pausa visual
- 3ade61052 — fichas seguindo composição do DANFE

## Evidências existentes (históricas, não reexecutadas agora)

`docs/reports/PRINT-LAYOUTS-2026-09-12.md` descreve implementação, fontes e limitações.
`output/print-layouts/` contém aproximadamente 15 MB não rastreados: index.html, typography.html, danfe-screen.html, SVGs antes/depois, bytes .bin, PNGs e logs. Preservar esse diretório ao arquivar a worktree; ele não está protegido pelos commits.

- `danfe-style-tests.txt`: 82 testes passaram em 13,91 s na última revisão.
- `test-result.txt`: etapa anterior com 129 testes + 11 subtests.
- `frontend-tests.txt`: 20 testes em 2 arquivos passaram; typecheck e Ruff históricos também registrados.
- Evidência de software não equivale a aprovação estética, fiscal ou física.
- A prévia HTTP antiga em 127.0.0.1:13627 não estava acessível nesta auditoria (conexão recusada). HTML e imagens permanecem no disco. Não foi iniciado servidor.
- Para reabrir somente a galeria preservada: `python3 -m http.server 13627 --bind 127.0.0.1 --directory output/print-layouts` a partir desta worktree.
- Monograma para uso/download: `media/branding/nelson-monogram-print.svg` (e PNG adjacente); cópia na galeria `monogram.svg`.

## Decisões e validações pendentes

Pablo pediu manter como está por enquanto. A referência DANFE foi escolhida para a ficha, mas não houve aprovação visual final nem autorização de integração/publicação. Nome proposto: Ficha do pedido, ainda sem renomeação global.

A pergunta posterior confirmou a existência oficial do DANFE NFC-e Resumido (Ajuste SINIEF 19/16, cláusula décima, §3º II), condicionado à concordância do consumidor; manual também remete às regras da UF. Essa modalidade NÃO foi implementada. Falta verificar a legislação vigente do Paraná e concluir consulta ao manual atual 6.0 antes de eventual adoção. O relatório anterior usa o manual oficial 5.0 acessível e registra a falha de acesso integral ao 6.0. Não tratar afirmações históricas sobre impressão de todos os itens como proibição absoluta do resumido.

Faltam ensaio na Epson TM-T20, qualidade/velocidade real, largura útil, acentos, corte, QR lido por celular, papel e emissão real de homologação. RTC e bobina 58 mm seguem fora da cobertura declarada. Raster trabalha nominalmente em 576 dots/72 mm úteis na bobina de 80 mm.

## Relação com main e próximo passo

Main mudou os seguintes arquivos também alterados pela branch: `config/settings.py`, `docs/reference/data-schemas.md`, `shopman/backstage/api/operations.py`, `surfaces/pos-nuxt/app/pages/index.vue`. Isso é sobreposição de arquivos, não prova de conflito textual. Há alterações posteriores do próprio #619 e do #647 (estação e recibo atômico); preservar essas correções ao retomar. #642 trata captura/dados fiscais na criação do pedido e #676 trata prova de impressão da Produção, sem substituir nosso compositor.

Próximo passo: manter como proposta local aguardando direção/aprovação visual de Pablo. Quando retomada, decidir se a correção fiscal de fonte XML será revisada separadamente do design; reconciliar com main em isolamento, revalidar contratos de PDV/estação e rodar testes pertinentes após essa reconciliação. Antes de habilitar raster, fazer ensaio físico. Nenhum PR, push, merge, deploy ou CI deve ser inferido deste inventário.

Nesta auditoria foram feitos somente leituras locais/consultas GitHub e a gravação deste arquivo. Nenhum teste ou workflow foi disparado; nenhum código foi alterado.
