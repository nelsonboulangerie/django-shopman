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

Número do pedido em corpo duplo; modalidade/dia/janela compartilham linha; nome e telefone compartilham linha quando cabem. Nome extenso permanece completo. Endereço, cobrança e observações aparecem antes dos itens. Valores recebidos não entram novamente na cobrança. Somente a parcela pendente em dinheiro determina o troco a levar. Método externo, isoladamente, não prova pagamento. Estado desconhecido não manda cobrar.

Marca de impressão derivada do SVG existente, em preto sobre branco: `media/branding/nelson-print.svg` e `.png`. O PNG é limitado a 24 × 8 mm nominais. Configuração do deployment: `SHOPMAN_PRINT_LOGO_PATH` com caminho local para esse PNG. Default vazio conserva o nome em texto; arquivo indisponível também usa texto e registra aviso. Nenhuma configuração de produção foi alterada.

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

Imprimir a galeria em A4 a 100%, sem ajustar e sem cabeçalho/rodapé. Régua de 80 mm para conferência. A escala na tela depende do monitor. A fonte residente é aproximada por monospace; o interpretador respeita comandos de dimensão, negrito, raster, QR e avanço, e recusa linhas que excedam a área.

| Cenário | Antes (mm) | Depois (mm) |
|---|---:|---:|
| Retirada curta | 127,5 | 74,0 |
| Longo com endereço/observações | 225,0 | 171,5 |
| Entrega paga | 142,5 | 96,5 |
| Entrega com troco | 165,0 | 110,0 |
| Entrega com pagamento misto | 168,8 | 117,5 |
| Balcão imediato | 114,0 | 74,0 |

São medidas nominais da simulação, incluindo avanço de corte. O DANFE de demonstração cresce porque passa a imprimir dados fiscais que faltavam (endereço do destinatário, pagamentos parciais, desconto/frete, horários e mensagens); não é lícito omiti-los para ganhar espaço.

## Validação e limites

Resultado final: 129 testes backend e 11 subtests passaram; 20 testes frontend de recuperação/geometria passaram; typecheck Nuxt (Node 22), Ruff dos módulos alterados e `git diff --check` aprovados. Dependências instaladas somente nesta worktree. Logs locais em `output/print-layouts/`. Após ajustar a recuperação de notas canceladas, 22 testes fiscais passaram novamente, incluindo uma nova regressão que impede oferecer nota cancelada como autorizada.

Testes cobrem contratos críticos, comandos e limite de largura; os testes fiscais usam XML fictício sem assinatura e modificam os dados comerciais para provar que não substituem a fonte fiscal. Cobrem também fetch/cache/timeout configurado, redirects, tamanho, entidade XML, chave/ambiente/QR divergentes, cancelamento, recusa sem carimbo e recuperação.

Não houve impressora conectada, emissão de homologação real, validação criptográfica de assinatura XML ou conferência por contador. O protocolo é lido da fonte entregue por HTTPS pelo provedor e vinculado à chave registrada; não se faz nova consulta de autorização à SEFAZ. O cache não é arquivo fiscal permanente. Documentos antigos sem XML acessível exigem a via do provedor.

Ensaio físico pendente: densidade e resolução da marca raster, fonte A real, acentos, alinhamento, margens, avanço até a guilhotina, segunda via, bobina longa, leitura óptica do QR com celular e durabilidade do papel. Homologação fiscal, RTC e formatos diferentes de 80 mm permanecem limites explícitos; testes de software não substituem esse ensaio.

Rollback futuro: reverter apenas os commits desta branch e a configuração opcional da marca. Não há migrações, reseed ou mudança de pagamento/emissão.
