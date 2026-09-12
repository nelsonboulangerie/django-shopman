# Impressos operacionais e DANFE NFC-e — 12/09/2026

## Entrega e isolamento

Branch `codex/print-layouts-20260912`, worktree `django-shopman-print-layouts-20260912`.
Base: `eaba3d45af9e9a201ff38ca6fb03899c4a78111a`, head do PR #619 quando inspecionado (aberto, não integrado).
Coordenação direta com as sessões “Corrigir fluxos críticos do PDV” e “Conversacional - Execução do plano de excelência”. Nenhuma alteração no checkout compartilhado, nenhum merge, deploy ou emissão real.

O trabalho do #619 foi mantido: endereço antes dos itens, cobrança por método, troco para, valor a levar e proteção contra cobrar novamente pedidos pagos. O novo contrato em elaboração na sessão PDV é `Order.data.pos.sales_mode=counter|order`; o compositor apenas o lê. Não altera o funil, o helper de handoff ou o payload de emissão fiscal.

## Caminhos reais encontrados

- Ficha do pedido: `receipt_escpos.order_ticket`, endpoints individual/lote, bytes base64 para o agente do balcão. O lote continua usando os mesmos critérios e carimbos.
- DANFE da bobina: `POSDanfeEscposView` → `build_danfe` → `danfe_nfce` → agente; consulta HTML em `/fiscal/danfe/<ref>/`.
- Hardware documentado: Epson TM-T20 USB, fila do sistema; agente envia RAW via `lp -o raw` (Linux/macOS) ou winspool (Windows). Contrato medido no repositório em 15/08/2026: CP860, 48 colunas, QR nativo. Bobina de 80 mm, área nominal de 576 dots/72 mm a aproximadamente 203 dpi.
- Há geometria declarativa de 58 mm no PDV, mas o compositor ESC/POS destes documentos continua sendo de 48 colunas/80 mm. Esta entrega não promete suporte a 58 mm.
- Recibo de venda, comprovante de caixa e etiquetas de produção têm outras finalidades; não foram redesenhados. Helpers comuns ganharam quebra sem truncamento e remoção de controles injetados em texto.

## Decisões de layout

“Ficha do pedido” é a proposta de nome, sem renomeação global de APIs/modelos. “Comanda” já identifica outra entidade; “romaneio” descreve melhor lote/rota; “ordem de preparo” não cobre cobrança e retirada.

No modo residente, número do pedido em corpo duplo; modalidade/dia/janela compartilham linha; nome e telefone compartilham linha quando cabem. Nome extenso permanece completo. Endereço, cobrança e observações aparecem antes dos itens. Valores recebidos não entram novamente na cobrança. Somente a parcela pendente em dinheiro determina o troco a levar. Método externo, isoladamente, não prova pagamento. Estado desconhecido não manda cobrar.

Marca de impressão derivada do SVG existente, em preto sobre branco: `media/branding/nelson-print.svg` e `.png`. No modo residente o PNG é limitado a 24 × 8 mm nominais; no raster a ficha usa marca de até 20 × 7,5 mm ao lado do pedido e o fiscal até 28 × 10 mm. Configuração do deployment: `SHOPMAN_PRINT_LOGO_PATH` com caminho local para esse PNG. Default vazio conserva o nome em texto; arquivo indisponível usa texto na ficha; o modo residente registra aviso. Nenhuma configuração de produção foi alterada.

## Fonte fiscal e regras verificadas

O gerador anterior usava `Order.items`, `Order.total_q`, cadastro atual de `Shop` e ambiente atual das settings. Isso diverge quando a emissão remove a taxa de entrega, rateia desconto ou quando o cadastro muda depois da autorização.

Agora os campos fiscais vêm do XML apontado por `nfce_xml_url`: emissor/destinatário, itens/unidades/valores, descontos/acréscimos, pagamentos/troco, ambiente, horários locais, chave/protocolo, consulta e QR. Mantém `infAdFisco`, `infCpl`, `xMsg` e tributos informados. O código não altera a regra de emissão nem inventa dados omitidos do XML.

Fontes oficiais consultadas em 12/09/2026:

- [SEFAZ-PR — QR Code](https://sped.fazenda.pr.gov.br/NFCe/Pagina/QR-Code): referencia o manual 6.0 e descreve a URL 3.0 e o ambiente. A URL do QR é preservada do XML, sem regenerar assinatura/CSC.
- [Portal Nacional — manuais vigentes](https://www.nfe.fazenda.gov.br/pOrtaL/listaConteudo.aspx?AspxAutoDetectCookieSupport=1&tipoConteudo=ndIjl+iEFdE%3D): manual DANFE NFC-e 6.0, março/2025. O endpoint de download retornou loop de redirects nesta consulta; não se afirma leitura integral do PDF 6.0.
- [CONFAZ — manual 5.0, seções 2 e 3](https://www.confaz.fazenda.gov.br/legislacao/arquivo-manuais/manual_de_especificacoes_tecnicas_do_danfe_nfc-e_qr_code-versao-5-0.pdf): base oficial acessível para fonte XML, identificação, detalhes, totais, pagamentos, consulta, consumidor, protocolo, mensagens, margens e QR. O papel pode ser A4; a antiga afirmação do código de que “A4 não é DANFE” foi removida. Mantidos todos os itens, margens laterais de 4 mm e QR acima de 25 mm; não foi adotado modelo resumido.
- [Portal Nacional — notas técnicas](https://www.nfe.fazenda.gov.br/pOrtaL/listaConteudo.aspx?AspxAutoDetectCookieSupport=1&tipoConteudo=04BIflQt1aY%3D): há evolução RTC e CNPJ alfanumérico; não confundir NFC-e modelo 65 com DANFE Simplificado Tipo 2 da NF-e modelo 55.
- [Focus — consulta NFC-e](https://doc.focusnfe.com.br/reference/consultar_nfce): contrato de status e caminhos de XML/DANFE.

## Recusas e recuperação

Leitura por HTTPS dos hosts Focus ou do host configurado, sem redirects/credenciais na URL, timeout de conexão/leitura, limite de 2 MB e cache de 24 horas. Confere chave, modelo 65, protocolo autorizado, ambiente, campos indispensáveis e correspondência do QR. XML externo com entidades é recusado.

Sem fonte validada, cancelamento conhecido, campos incompletos, caracteres fiscais fora da CP860 ou QR fora da largura: não compõe um documento substituto a partir do pedido. Resposta 409, sem marcar primeira impressão, com motivo e URL do provedor quando existente. O PDV oferece “Abrir DANFE autorizada” e não afirma sucesso de impressão. Uma falha de fonte conhecida não é tratada como simples espera de autorização.

Totais RTC (`IBSCBSTot`, `ISTot`, `vNFTot`) ainda não foram homologados neste compositor: são explicitamente recusados, com acesso à via do Focus, em vez de descartados. A classificação de entrega gratuita no adapter existente continua sendo investigada pela sessão PDV; não foi alterada nesta entrega.

## Prévia reproduzível

Na raiz desta worktree, usando o Python canônico do repositório:

```bash
/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python scripts/print_preview/render.py
/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python -m http.server 13627 --bind 127.0.0.1 --directory output/print-layouts
```

`output/print-layouts/index.html` compara bytes do commit base aos bytes do código atual. Inclui curto, longo/endereço/observações, retirada hoje, entrega paga, dinheiro com troco para R$ 100,00, pagamento misto, balcão imediato e XML fiscal fictício. Há SVGs de 80 mm e `.bin` ESC/POS, além da consulta fiscal HTML. O banco da prévia é SQLite em memória; não usa dados de operação nem chama o provedor.

Imprimir a galeria em A4 a 100%, sem ajustar e sem cabeçalho/rodapé. Régua de 80 mm para conferência. A escala na tela depende do monitor. O antes aproxima a fonte residente por monospace; o depois mostra os pixels exatos enviados no raster. O interpretador respeita comandos de dimensão, negrito, raster, QR e avanço, e recusa linhas que excedam a área.

| Cenário | Antes (mm) | Depois (mm) |
|---|---:|---:|
| Retirada curta | 127,5 | 84,8 |
| Longo com endereço/observações | 225,0 | 197,9 |
| Entrega paga | 142,5 | 124,2 |
| Entrega com troco | 165,0 | 134,6 |
| Entrega com pagamento misto | 168,8 | 151,8 |
| Balcão imediato | 114,0 | 81,6 |

São medidas nominais da simulação, incluindo avanço de corte. O DANFE de demonstração cresce porque passa a imprimir dados fiscais que faltavam (endereço do destinatário, pagamentos parciais, desconto/frete, horários e mensagens); não é lícito omiti-los para ganhar espaço.

## Validação e limites

Resultado final: 129 testes backend e 11 subtests passaram; 20 testes frontend de recuperação/geometria passaram; typecheck Nuxt (Node 22), Ruff dos módulos alterados e `git diff --check` aprovados. Dependências instaladas somente nesta worktree. Logs locais em `output/print-layouts/`. Após ajustar a recuperação de notas canceladas, 22 testes fiscais passaram novamente, incluindo uma nova regressão que impede oferecer nota cancelada como autorizada.

Testes cobrem contratos críticos, comandos e limite de largura; os testes fiscais usam XML fictício sem assinatura e modificam os dados comerciais para provar que não substituem a fonte fiscal. Cobrem também fetch/cache/timeout configurado, redirects, tamanho, entidade XML, chave/ambiente/QR divergentes, cancelamento, recusa sem carimbo e recuperação.

Não houve impressora conectada, emissão de homologação real, validação criptográfica de assinatura XML ou conferência por contador. O protocolo é lido da fonte entregue por HTTPS pelo provedor e vinculado à chave registrada; não se faz nova consulta de autorização à SEFAZ. O cache não é arquivo fiscal permanente. Documentos antigos sem XML acessível exigem a via do provedor.

Ensaio físico pendente: densidade e resolução da marca raster, fonte A real, acentos, alinhamento, margens, avanço até a guilhotina, segunda via, bobina longa, leitura óptica do QR com celular e durabilidade do papel. Homologação fiscal, RTC e formatos diferentes de 80 mm permanecem limites explícitos; testes de software não substituem esse ensaio.

Rollback futuro: reverter apenas os commits desta branch e a configuração opcional da marca. Não há migrações, reseed ou mudança de pagamento/emissão.

## Iteração proporcional inicial — feedback do usuário

O usuário autorizou priorizar acabamento mesmo com pequena perda de velocidade.
Foi implementado backend raster selecionável por `SHOPMAN_PRINT_RENDERER=raster`;
o default de operação permanece `native` até o ensaio. A prévia usa raster.
Os dois modos recebem os mesmos campos pelos compositores existentes: não há
segunda regra de pagamento, coleta, troco ou fonte fiscal. O backend gráfico mede
texto em pixels, quebra nomes/identificadores sem truncar e alinha valores à direita.

Noto Sans de peso 500/700 é distribuída com licença OFL, obtida do
[repositório oficial Google Fonts](https://github.com/google/fonts/tree/main/ofl/notosans).
A composição usa Pillow já instalado por `qrcode[pil]`. A fonte está incluída no
package-data. O corpo operacional é 24 dots (~8,5 pt), fiscal 22 dots (~7,8 pt),
rodapé operacional 20 dots; destaques têm 28–42 dots. Não usa dithering: o arquivo
final tem somente preto/branco e QR com módulos inteiros e zona livre preservada.

Marca e referência compartilham o cabeçalho operacional. Dinheiro destaca
**TROCO PARA**, seguido de **Levar de troco** e **Valor a cobrar**. Cartão destaca
**A COBRAR**; no misto a parcela específica do cartão também é destacada, para
não confundi-la com o total. Pedido pago continua indicando **PAGO — NÃO COBRAR**.
O fiscal tem divisões visuais entre itens, valores, consulta e destinatário.

Saída `GS v 0`, 576 dots, em faixas de até 128 linhas, sem avanço entre faixas.
Foi mantida a família de comandos já usada para o logo. A
[referência oficial Epson](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lv_0.html)
documenta o formato e observa que é um comando legado, com alternativas mais
recentes. O suporte e a fluidez das faixas precisam do ensaio na TM-T20 da loja;
não alteramos densidade, velocidade ou configuração persistente do equipamento.

Após a iteração: **136 testes e 11 subtests passaram**. Novas regressões cobrem
dinheiro, entrega paga, misto, conteúdo fiscal, identificador longo e reconstrução
pixel a pixel das faixas (incluindo o QR dentro do raster fiscal). Ruff aprovado. Build do wheel também aprovado, com fonte e licença conferidas dentro do pacote.

Benchmark local de 20 composições após aquecimento: mediana de **25 ms** no pedido
curto, **63 ms** no longo e **118 ms** no DANFE. Arquivos desses cenários de benchmark:
32.083, 62.419 e 127.563 bytes. Valores não incluem fetch do XML, banco, transmissão,
fila nem impressão. Não equivalem a promessa de latência no balcão. Resultados em
`output/print-layouts/benchmark.json`; exemplos RAW em `*-depois.bin`.

Ensaio a realizar: usar os RAW de exemplo pelo mesmo agente/fila da loja, cronometrar
curto/longo/fiscal até o corte, conferir acentos/números em tamanho real e ler o QR
com celular. Só então decidir a configuração operacional. Não houve impressão
física nesta conversa, e não se afirma garantia física ou homologação fiscal.

## Direção de sinalização, monograma e blocos — revisão atual

A proposta aplicada passa a usar **Barlow Semi Condensed Medium/Bold**, do
[projeto oficial de Jeremy Tribby](https://github.com/jpt/barlow), inspirada na
sinalização e infraestrutura pública californiana, sob SIL OFL 1.1. Arquivos
obtidos do repositório Google Fonts; licença em `Barlow-OFL.txt`. A Noto Sans
permanece somente para o estudo comparativo da prévia. A Parisine Narrow é uma
candidata mencionada pelo usuário, não uma fonte incorporada sem arquivo/licença.

`typography.html` compara Barlow Semi Condensed, Noto Sans e o eixo condensado da
Noto Sans com o mesmo texto/tamanho. A galeria principal mostra o raster real.

Monograma extraído de `nelson_monograma_flat_2023.svg`, fornecido pelo usuário.
O SVG original contém material de trabalho adicional e referência a JPEG externo.
Foi selecionado somente o grupo vetorial principal do monograma circular,
preservando suas curvas; fundos amarelos e elementos externos não foram copiados.
Saída `media/branding/nelson-monogram-print.svg`, traços `#000000`, sem fundo,
sem imagens externas; PNG RGBA correspondente com transparência, também preto.
O original no diretório Design não foi modificado. A prévia oferece ambos para baixar.

Cabeçalho com monograma de até 96 dots à esquerda e nome/dados à direita.
No DANFE, os dados do emissor continuam exclusivamente do XML; a ficha usa o
nome comercial já recebido pelo serviço. Cartão do pedido em duas colunas,
com identificação à esquerda e modalidade/dia/janela à direita. Caixas de borda
2 dots e raio 12 dots agrupam pagamento e observações; endereços/itens permanecem
livres. No dinheiro, duas células separam valor do troco a levar e valor a cobrar.
Os campos crescem por conteúdo, sem altura fixa que corte endereços ou notas.

A tabela acima corresponde a esta revisão. O exemplo fiscal completo fica em
221,6 mm, preservando os mesmos dados da revisão anterior (242,4 mm). Espaço e
hierarquia foram equilibrados; a ficha com troco usa 111,9 mm para separar blocos
que antes ocupavam 102,4 mm na versão proporcional inicial.

Validação desta revisão: **78 testes passaram**, cobrindo compositor operacional,
fiscal e raster. Inclui caixa extensa, reconstrução dos pixels, valores de troco
nas duas células e PNG estritamente preto com transparência. Ruff e diff check
aprovados. Continuam pendentes impressora física, leitura óptica e validação fiscal
já descritas. Configuração raster segue opt-in; sem merge ou deploy.

## Correção da comparação no painel estreito

O corte reportado à direita foi reproduzido na aba do usuário: viewport de 620 px,
comparação com 557 px disponíveis e conteúdo de 629 px. Era overflow horizontal
da galeria, ocultando parte do segundo impresso. A comparação agora quebra em
coluna e mostra o depois primeiro em telas estreitas; SVG limita-se ao contêiner.
Verificado na mesma aba: as sete comparações têm scrollWidth = clientWidth = 557 px,
e a ficha aparece inteira. A impressão mantém 80 mm e a composição RAW não mudou.


## Endereço para leitura imediata

A ficha raster separa rua/número (30 dots, bold), complemento (27 dots),
bairro/cidade (24 dots) e instruções sob “NA CHEGADA” (26 dots, uma frase por
linha), com maior entrelinha. A finalidade é encontrar o destino sem ler um
parágrafo compacto; o exemplo com troco passa de 111,9 para 134,6 mm.

Conserva o endereço cadastrado: só separa a primeira linha por vírgulas quando
há número reconhecível na segunda parte; formatos incomuns permanecem completos.
Complemento já presente não se duplica. Sem texto formatado, utiliza os campos
estruturados existentes, inclusive CEP. Instruções mantêm texto e pontuação.
O DANFE não mudou nesta revisão. Verificação visual na aba do usuário; testes
cobrem partes do endereço, dados estruturados, complemento e formato incomum.
