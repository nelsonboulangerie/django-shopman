# Integração do Shopman com TikTok e TikTok Shop

## Sumário executivo

Há um caminho técnico para o app Marketing do Shopman enviar vídeos e fotos ao TikTok, mas **o caminho regulatório e de produto é o fator decisivo**. A publicação pública automática usa o **Content Posting API — Direct Post**, não a Marketing API de anúncios. Ela exige app aprovado, escopo `video.publish` aprovado e autorizado pela conta, além de uma auditoria específica para remover a restrição de visibilidade privada. Sem essa auditoria, o cliente fica limitado a `SELF_ONLY`, a no máximo cinco usuários publicadores em 24 horas, e somente contas privadas podem iniciar o post.[^1]

O maior obstáculo para a Nelson Boulangerie não é autenticação nem implementação. O guideline oficial diz que clientes Direct Post devem servir criadores autênticos e público amplo; cita como uso **não aceitável** uma ferramenta de upload para contas administradas pela própria equipe.[^1] Portanto, um conector exclusivo da Nelson, embutido em um backoffice privado, tem risco material de reprovação na auditoria necessária à publicação pública. Não se deve prometer “disparo automático público” antes de obter orientação escrita ou aprovação do TikTok.

O caminho imediato de menor risco é o **Upload API** (`video.upload`): o Shopman envia o conteúdo como rascunho, o operador recebe uma notificação no inbox do TikTok, abre o app, edita se desejar e conclui a publicação. Essa alternativa ainda requer app e escopo aprovados e autorização OAuth, mas preserva uma confirmação humana no TikTok e não depende da promessa de Direct Post público. Há um teto de cinco compartilhamentos pendentes por usuário em qualquer janela de 24 horas.[^2]

O TikTok Shop opera no Brasil desde 8 de maio de 2025.[^3] Entretanto, sua política brasileira vigente impede o caso central da Nelson: **alimentos perecíveis, que exigem temperatura específica e todos os alimentos caseiros são proibidos**. Alimentos embalados ou pré-embalados e bebidas não alcoólicas podem ser aceitos somente para vendedores qualificados/aprovados numa categoria restrita, tratada como “somente por convite”.[^4] Assim, croissants, pães frescos, confeitaria fresca e itens de produção diária não devem ser cadastrados. Um piloto de Shop só é defensável com uma linha realmente pré-embalada, não perecível, de validade e rotulagem adequadas — por exemplo, biscoitos, granola ou kits shelf-stable — e após aprovação explícita da categoria.

### Veredito recomendado

| Frente | Veredito | Motivo |
|---|---|---|
| Upload de rascunho ao TikTok | **Implementar primeiro** | Compatível com confirmação humana; resolve grande parte do retrabalho operacional; risco de plataforma menor |
| Direct Post público | **Condicional / não prometer agora** | Auditoria obrigatória e guideline contrário a ferramenta interna para contas próprias |
| Direct Post privado | **Usar somente para teste controlado** | Restrito a `SELF_ONLY`; não atende o objetivo comercial final |
| TikTok Shop para produtos frescos | **Não implementar** | Categoria explicitamente proibida no Brasil |
| TikTok Shop para linha pré-embalada não perecível | **Piloto após qualificação** | Categoria restrita/somente por convite; custo e logística precisam fechar |
| Shopman como conector TikTok Shop de mercado | **Visão futura** | Public app exige revisão, compliance/legal, listagem em português e, se Connector, beta test |

## Escopo, data de corte e nível de certeza

Este relatório considera regras disponíveis em **12 de setembro de 2026**, com prioridade para TikTok for Developers, TikTok Shop Partner Center, TikTok Shop Academy Brasil, TikTok Newsroom e TikTok Support. Políticas, tarifas e disponibilidade de endpoints mudam com frequência; itens marcados como “confirmar no portal” não têm evidência pública suficiente para serem tratados como compromisso contratual.

Há dois ambientes e dois processos de credenciamento separados:

1. **TikTok for Developers** — Login Kit e Content Posting API para autorizar um perfil e enviar conteúdo.
2. **TikTok Shop Partner Center / Seller Center** — APIs de catálogo, pedidos, estoque, logística, devoluções, finanças e webhooks de uma loja.

Uma aprovação não concede automaticamente a outra. Da mesma forma, o termo interno “app Marketing” do Shopman não significa TikTok Marketing API: a documentação oficial separa APIs orgânicas do TikTok for Developers das APIs de anúncios/campanhas do TikTok for Business.[^5]

## 1. Publicação orgânica no TikTok

### 1.1 Direct Post versus Upload

| Aspecto | Direct Post | Upload |
|---|---|---|
| Objetivo | Publicar diretamente no perfil autorizado | Enviar rascunho para conclusão no TikTok |
| Escopo | `video.publish` | `video.upload` |
| Vídeo | `/v2/post/publish/video/init/` | `/v2/post/publish/inbox/video/init/` |
| Foto | `/v2/post/publish/content/init/`, `post_mode=DIRECT_POST` | Mesmo endpoint, `post_mode=MEDIA_UPLOAD` |
| Interação humana | Consentimento expresso e UX completa no app integrador | Usuário abre notificação, revisa/edita e publica no TikTok |
| Público sem auditoria | Não; `SELF_ONLY` | A publicação final é concluída pelo usuário no fluxo do TikTok |
| Melhor uso para Nelson | Somente se houver aprovação/auditoria e produto elegível | Primeira entrega recomendada |

O Direct Post inicializa o envio, devolve `publish_id` e, para `FILE_UPLOAD`, uma `upload_url` válida por uma hora. O Upload API segue o mesmo padrão de transferência, mas termina inicialmente em `SEND_TO_USER_INBOX`, até que a pessoa conclua o post no TikTok.[^2][^6]

O Content Posting API suporta vídeos e fotos. Fotos usam somente `PULL_FROM_URL`, aceitam até 35 imagens, título de até 90 e descrição de até 4.000 unidades UTF-16. Para vídeo, a legenda aceita até 2.200 unidades UTF-16.[^6][^7]

### 1.2 Elegibilidade, aprovação e auditoria

São necessárias duas camadas de aprovação:

1. **Revisão do app e do escopo.** O app deve estar cadastrado no TikTok for Developers, adicionar Content Posting API e solicitar somente os produtos/escopos necessários. Para Direct Post, o app e o usuário precisam conceder `video.publish`; para Upload, `video.upload`.[^6][^8]
2. **Auditoria do cliente Direct Post.** Mesmo um cliente capaz de testar o endpoint continua privado enquanto “unaudited”. Só a auditoria remove a limitação de visibilidade.[^1][^6]

A revisão geral pede nome e ícone próprios, descrição correta, site institucional completo — não apenas landing ou login —, links visíveis de Política de Privacidade e Termos de Serviço, redirect URI válido e explicação detalhada de cada produto e escopo. É obrigatório fornecer pelo menos um vídeo demonstrando o fluxo completo e atualizado; são aceitos até cinco vídeos de 50 MB. Para a primeira revisão, a demonstração deve usar sandbox e mostrar a interface e as interações reais no mesmo domínio informado.[^8]

A FAQ estima “vários dias a duas semanas” para app review, mas as diretrizes gerais registram que o processo é manual e sem prazo ou garantia oficial. Apps incompletos, beta ou de teste em geral não são aprovados; um app ainda não publicado pode pedir avaliação, acompanhada de justificativa e mockups, sob decisão discricionária.[^5][^9]

#### Restrição crítica de finalidade

O guideline do Direct Post exige que o cliente:

- facilite a publicação de conteúdo original por criadores autênticos;
- seja destinado a audiência ampla, não a grupo interno/privado;
- não seja uma ferramenta para subir conteúdo somente às contas que o desenvolvedor ou sua equipe administra;
- não copie conteúdo arbitrário de outras plataformas.[^1]

**Análise para o Shopman:** a instância atual é um backoffice de uma única padaria. Mesmo com uma implementação tecnicamente perfeita, a descrição honesta “operadores da Nelson publicam na conta TikTok da Nelson” coincide com o exemplo oficial de uso não aceitável para Direct Post auditado. Há três saídas legítimas:

1. lançar primeiro o Upload API e manter conclusão no app TikTok;
2. obter confirmação escrita do suporte/parcerias de que o caso é aceitável antes de investir na auditoria;
3. transformar a capacidade numa função real e acessível a múltiplos lojistas/criadores do framework Shopman, com onboarding, UX e políticas públicas — não apenas uma narrativa criada para revisão.

Não é recomendável mascarar o uso interno como SaaS público. Informação incompleta ou falsa pode atrasar ou impedir aprovação, e violações posteriores podem revogar a integração.[^9]

### 1.3 Sandbox e produção

O sandbox permite até cinco configurações e até dez contas-alvo. Ele não exige revisão para experimentação, mas **não oferece publicação de vídeos públicos pelo Content Posting API**.[^10] A configuração pode ser importada para um Draft de produção; a importação sobrescreve a configuração existente do Draft.

Isso produz um plano de testes claro:

- sandbox/cliente não auditado valida OAuth, transferência, estados, erros e UX;
- todos os Direct Posts de teste permanecem privados;
- publicação pública só entra no aceite após app live, `video.publish` autorizado e auditoria Direct Post concluída;
- nenhuma evidência de sandbox deve ser interpretada como homologação de publicação pública.

### 1.4 Autenticação e ciclo de tokens

O Login Kit usa OAuth 2.0 Authorization Code. Para web, o backend redireciona a pessoa para `https://www.tiktok.com/v2/auth/authorize/` com `client_key`, `scope`, `redirect_uri`, `state` e `response_type=code`. O `state` deve ser imprevisível e validado no callback contra CSRF. A redirect URI precisa ser absoluta, HTTPS, estática, sem query string ou fragmento; podem ser cadastradas até dez, cada uma com menos de 512 caracteres.[^11]

O backend troca o `code` em `POST https://open.tiktokapis.com/v2/oauth/token/`, mantendo `client_secret` e tokens somente no servidor. O access token comum vale 24 horas; o refresh token, 365 dias. O refresh não requer nova interação, mas a resposta pode rotacionar o refresh token e o valor novo deve substituir o anterior de forma atômica. A desconexão usa `POST /v2/oauth/revoke/`.[^12]

Para a Nelson, a ação do titular pelo celular será necessária em três situações previsíveis:

- login/consentimento inicial aos escopos;
- eventual reautorização após revogação ou expiração do refresh token;
- conclusão de cada rascunho no app TikTok quando usado Upload API.

Não é necessário solicitar senha, cookie ou token ao operador. O sistema deve entregar redirect/QR oficial do TikTok e receber apenas o callback OAuth. Credenciais nunca devem ser coladas em chamado, log ou banco sem criptografia.

### 1.5 UX obrigatória para Direct Post

O TikTok não autoriza uma chamada invisível de servidor disparada apenas porque uma campanha foi aprovada no backoffice. Na tela “Publicar no TikTok”, o cliente deve consultar `creator_info/query` no momento de renderizar e usar os dados mais recentes.[^1][^13]

A tela deve:

- mostrar nickname/conta de destino;
- interromper o envio se o criador não puder publicar naquele momento;
- conferir a duração contra `max_video_post_duration_sec`;
- mostrar preview do conteúdo;
- deixar título/legenda e hashtags pré-preenchidos, porém editáveis;
- oferecer exatamente as opções de privacidade retornadas pelo creator info;
- não selecionar privacidade por padrão: o usuário escolhe manualmente;
- oferecer comentário, duet e stitch conforme permitido pela conta, desabilitando visualmente os indisponíveis;
- deixar esses controles desligados por padrão e exigir decisão do usuário;
- não mostrar duet/stitch para foto;
- obter consentimento expresso antes de começar a transferência;
- informar que processamento/visibilidade pode levar minutos;
- apresentar o texto/link de confirmação de uso de música exigido;
- manter status visível por polling ou webhook.[^1]

Para conteúdo comercial, a tela também precisa trazer uma chave, desligada por padrão, indicando promoção de marca/produto/serviço. Ao ligá-la, o usuário deve marcar ao menos “sua marca” (`brand_organic_toggle`) ou “conteúdo de marca/parceria paga” (`brand_content_toggle`). Sem uma opção marcada, publicar fica desabilitado. Conteúdo de terceiros/pago não pode ser privado; a UX deve bloquear a combinação ou mudar a privacidade com aviso. Os rótulos esperados são “Promotional content” para marca própria e “Paid partnership” para branded content.[^1]

Como a Nelson promove os próprios produtos, o normal é **conteúdo comercial + sua marca** (`brand_organic_toggle=true`, `brand_content_toggle=false`). Isso não elimina a escolha explícita do operador nem permite hardcode invisível. Se houver colaboração remunerada, produto recebido, afiliado ou outra contrapartida a terceiro, passa a branded content e a política correspondente deve ser respeitada.[^14]

### 1.6 Música, direitos e conteúdo comercial

Para conteúdo que promove marca, produto ou serviço, o TikTok recomenda somente músicas da **Commercial Music Library (CML)**, pois as licenças comuns fora dela não cobrem uso comercial. Se o post usar som original ou música fora da CML, a confirmação declara que não há música protegida ou que todas as licenças necessárias foram obtidas e pagas.[^15]

Consequências práticas:

- não reaproveitar automaticamente trilha de Instagram/Reels;
- armazenar a origem/licença da trilha no registro da campanha;
- preferir vídeo sem trilha, som original próprio ou música comprovadamente liberada para uso comercial;
- não inserir watermark/logo promocional do Shopman nem marca de outra plataforma;
- a marca da própria padaria aparecer naturalmente no cenário/produto é conteúdo comercial a divulgar, mas o integrador não deve sobrepor sua própria publicidade ao arquivo.[^1]

Alimentos comuns não constam como categoria proibida de branded content no Brasil na regra específica consultada; as restrições de HFSS publicadas nesse documento atingem Irlanda, Noruega, Portugal e Reino Unido, não Brasil. Ainda assim, conteúdo de alimentos precisa respeitar normas gerais, alegações e publicidade aplicáveis, e essa constatação não autoriza a venda do item no TikTok Shop.[^16]

### 1.7 Transferência e validação de mídia

Para mídia já armazenada pelo Shopman, o método esperado é `PULL_FROM_URL`. O guideline orienta não usar `FILE_UPLOAD` para arquivo já residente no servidor. O domínio ou prefixo precisa ser verificado no Developer Portal; a URL deve ser HTTPS, não redirecionar e permanecer acessível até o término do download, que expira após uma hora.[^1][^17]

`FILE_UPLOAD` deve ser reservado para arquivo vindo do dispositivo do usuário. Para vídeo, chunks precisam ser sequenciais, em geral de 5 a 64 MB, último chunk até 128 MB, máximo de 1.000 chunks. Arquivos com menos de 5 MB sobem inteiros; acima de 64 MB, em múltiplos chunks.[^17]

Restrições de vídeo publicadas:

- contêiner: MP4 recomendado, WebM ou MOV;
- codec: H.264 recomendado, H.265, VP8 ou VP9;
- frame rate: 23–60 fps;
- altura e largura: 360–4.096 px;
- tamanho: até 4 GB;
- duração: até 10 minutos no upload, mas o limite real do criador precisa ser lido em `creator_info` e pode ser 3, 5 ou 10 minutos.[^17]

Fotos aceitam WebP ou JPEG, até 1080p e 20 MB por imagem.[^17] A recomendação operacional é normalizar vídeo para MP4/H.264, áudio AAC, dimensões verticais compatíveis e tamanho muito inferior ao teto antes de iniciar o job; validar localmente evita gastar cota com falha previsível.

### 1.8 Limites e antispam

Os limites oficiais relevantes são:

- Direct Post e inicialização de foto: 6 requisições/minuto por access token;
- Query Creator Info: 20/minuto por access token;
- Fetch Status: 30/minuto por access token;
- cliente Direct Post não auditado: até 5 usuários publicadores/24h;
- Direct Post auditado ou não: cap de criadores ativos em 24h definido com base na estimativa declarada na auditoria;
- cap de posts por criador em 24h, compartilhado entre todos os clientes Direct Post, tipicamente em torno de 15, podendo variar;
- Upload: no máximo 5 shares pendentes por usuário em qualquer janela de 24h.[^1][^2][^7][^13]

Não se deve retentar cegamente `spam_risk_*`. `auth_removed`, usuário banido, texto classificado como spam e risco genérico são terminais; falha interna e download temporário podem ser retentáveis com backoff. O código deve preservar `publish_id`, `log_id`, contagem de bytes, razão de falha e decisão de retry.

### 1.9 Estados, moderação e webhooks

O status é consultado em `POST /v2/post/publish/status/fetch/`. Estados documentados:

- `PROCESSING_UPLOAD`;
- `PROCESSING_DOWNLOAD`;
- `SEND_TO_USER_INBOX`;
- `PUBLISH_COMPLETE`;
- `FAILED`.[^18]

Para posts públicos, o `post_id` só é entregue depois da moderação. Ela normalmente termina em cerca de um minuto, mas pode levar horas; não há SLA garantido. `PUBLISH_COMPLETE` e “publicamente disponível” são fatos distintos que o Shopman deve representar separadamente.[^18]

Eventos Content Posting disponíveis:

- `post.publish.failed`;
- `post.publish.complete`;
- `post.publish.inbox_delivered`;
- `post.publish.publicly_available`;
- `post.publish.no_longer_publicaly_available` (grafia oficial da API).[^18]

O webhook geral deve usar HTTPS, responder `200` imediatamente e processar assincronamente. A entrega é “at least once”; duplicatas são esperadas e exigem idempotência. Sem `200`, há retentativas com backoff por até 72 horas.[^19]

Arquitetura recomendada: webhook como fonte rápida de atualização e polling de reconciliação lento como rede de segurança. Nunca marcar “publicado publicamente” apenas por `PUBLISH_COMPLETE`; aguardar `publicly_available` ou `post_id` no status.

## 2. TikTok Shop Open Platform no Brasil

### 2.1 Disponibilidade e cadastro do vendedor

O TikTok Shop foi lançado no Brasil em 8 de maio de 2025.[^3] O cadastro brasileiro atual aceita apenas pessoa jurídica com CNPJ, incluindo MEI, EI, SLU, EIRELI, LTDA, S/A e ONG. O representante deve ter 18 anos, documento brasileiro válido, CPF, selfies de verificação, comprovantes societários, endereço, dados fiscais e conta bancária em nome da empresa. A conta precisa ser aprovada antes de publicar produtos; a orientação oficial informa análise normalmente em dois a seis dias.[^20]

Novas lojas entram em período probatório. Em 2 de abril de 2026, os níveis publicados eram: Iniciante, até 50 pedidos/dia e 1.000 anúncios ativos; Padrão, 100/2.000; Premium, 200/3.000; Profissional, sem o limite probatório de pedidos/ativos e com cota de 1.000 novos anúncios/dia. A progressão depende de tempo, treinamento, pedidos entregues, compradores, violações e score da loja; não há duração garantida.[^21]

### 2.2 Elegibilidade de produtos da Nelson

A regra brasileira de 17 de agosto de 2026 proíbe:

- alimentos perecíveis;
- alimentos que exijam temperatura específica;
- alimentos pré-embalados para menores de três anos e fórmula infantil;
- aditivos alimentares;
- todos os alimentos caseiros;
- bebidas alcoólicas.[^4]

Existe exceção para alimentos embalados/pré-embalados e bebidas não alcoólicas, mas somente em conformidade com a política de produtos restritos. A Academy classifica Food & Beverages — incluindo snacks, laticínios, alimentos instantâneos, frescos/congelados, bebidas não alcoólicas e insumos de confeitaria — como categoria “invite-only”, aberta somente a vendedores aprovados no processo de qualificação.[^22]

**Implicação:** mesmo que “artesanal” seja comercialmente desejável, a expressão “todos os alimentos caseiros” e a proibição de perecíveis tornam inadequado tentar listar os pães e doces frescos da operação diária. A API não contorna a política e não deve criar anúncio antes de o Seller Center mostrar categoria e qualificação aprovadas.

Um eventual piloto deve conter apenas SKUs simultaneamente:

1. industrializados/produzidos por empresa habilitada, não “caseiros” no sentido da política;
2. embalados ou pré-embalados para varejo;
3. não perecíveis e sem cadeia fria;
4. rotulados e regularizados conforme as regras brasileiras aplicáveis;
5. aprovados pelo Centro de Qualificação do TikTok Shop;
6. economicamente viáveis para envio e devolução nacionais.

### 2.3 Tipos de desenvolvedor e app

O Partner Center define três perfis:[^23]

| Perfil | Caso | Tipo de app |
|---|---|---|
| Seller Developer | Integra a própria loja ao próprio sistema; relação 1:1 | Custom App |
| System Integrator | Integra lojas específicas como prestador | Custom ou Public App |
| App Developer | Produto de software para operações de sellers | Custom ou Public App |

Seller Developer exige loja TikTok Shop já ativada e somente essa loja pode autorizar seus apps. Para o piloto Nelson-only, este é o enquadramento natural, sem a objeção de “uso interno” que existe no guideline do Content Posting Direct Post.

Um **Custom App** não aparece na App Store e é distribuído por link de autorização. Em geral precisa de registration review; compliance/legal pode ser exigido conforme mercado, categoria e escopos. Se for classificado como Connector ou chegar a 25 autorizações, exige app review; Connector também exige beta testing. Um **Public App** sempre exige registration review, formulário/listing por mercado, app review, compliance/legal e português para sellers brasileiros; Connector público também exige beta test.[^24][^25]

Para o Shopman como framework multiempresa, a evolução correta seria começar como Custom App da Nelson e só migrar a Public App quando houver produto real, suporte, políticas e onboarding para terceiros.

A disponibilidade técnica no país é corroborada também pela matriz oficial de regiões/idiomas, que inclui Brasil/pt-BR, por Development Shop local completo para BR e por um fluxo Open API fiscal específico do Brasil.[^38] Isso não significa que todo endpoint ou scope esteja automaticamente liberado: a lista efetiva é contextual ao app, mercado, categoria e revisão no Partner Center.

### 2.4 OAuth/autorização e assinatura

O fluxo Shop é independente do Login Kit. Pré-requisitos: cadastro de developer no Partner Center, app criado e APIs habilitadas. O seller abre o link de autorização, concede escopos e volta à redirect URL com `auth_code`. O backend troca o código em `GET https://auth.tiktok-shops.com/api/v2/token/get` usando `app_key`, `app_secret` e `grant_type=authorized_code`.[^26]

O access token de Shop vale por padrão sete dias e deve ser renovado em `/api/v2/token/refresh` antes de expirar. A duração do refresh acompanha a autorização concedida. O token segue no header `x-tts-access-token`; APIs de loja exigem também `shop_cipher`, obtido em `GET /authorization/202309/shops`.[^26][^27]

Além do token, cada chamada Open API inclui `app_key`, timestamp e assinatura criptográfica calculada sobre caminho/parâmetros e, conforme o método, body. A versão faz parte do path nas APIs modernas. A documentação alerta a não fixar “202309” como se fosse sempre a versão mais nova; cada endpoint e changelog são a fonte de verdade.[^28]

Controles mínimos:

- segredo e tokens criptografados no servidor;
- rotação atômica de token;
- vínculo inequívoco entre shop, `open_id`, `shop_cipher` e autorização;
- assinatura produzida por módulo único e testado;
- relógio UTC sincronizado;
- IP allowlist quando configurada;
- tratamento de desautorização e autorização prestes a expirar;
- menor conjunto de scopes possível.

### 2.5 APIs úteis ao Shopman

O portfólio oficial cobre produto, pedido, fulfillment, retorno/reembolso, logística, promoção, finanças e seller. Para a arquitetura Shopman, a ordem de valor é:[^29]

| Prioridade | Capacidade | Uso no Shopman |
|---|---|---|
| 1 | Authorization / Shop | Persistir autorização e `shop_cipher`; bloquear loja desconectada |
| 2 | Product + Inventory | Publicar somente SKUs qualificados; mapear IDs/SKUs; preço e estoque |
| 3 | Orders + webhook | Importar pedido, reservar estoque e evitar venda dupla |
| 4 | Fulfillment + Logistics | Etiqueta/coleta ou tracking do seller; estados de pacote |
| 5 | Returns/Refunds | Sincronizar cancelamento, devolução, reembolso e decisão |
| 6 | Finance | Conciliação de tarifas, transações e pagamentos |
| 7 | Promotion | Descontos e campanhas compatíveis com margem e estoque |

Product API cria, edita, exclui e consulta produtos, preço e estoque. Produtos criados/editados entram em revisão; preço e estoque podem ter tratamento diferente de campos editoriais, e webhooks fornecem resultado da auditoria.[^30] A API de inventário aceita busca em lote por até 100 product IDs ou 600 SKU IDs.[^31]

Orders API lista/detalha pedidos e oferece webhook de status. Um pedido nasce `UNPAID`; a orientação é reservar estoque desde a criação e liberar/confirmar conforme transição, evitando oversell entre PDV, storefront e Shop.[^32]

Fulfillment distingue TikTok Shipping de Seller Shipping e suporta pacotes divididos/agrupados. No Brasil, a política publicada recomenda Ready to Ship em um dia útil, despacho/em trânsito em dois dias úteis e autocancelamento quando ainda não enviado após seis dias úteis.[^33][^34]

O fluxo brasileiro tem uma obrigação fiscal adicional: Order List/Detail pode sinalizar `need_upload_invoice` e fornecer os dados fiscais necessários; a nota fiscal precisa ser enviada pelo endpoint BR e processada antes do despacho. A integração deve aguardar o webhook de status da invoice, em vez de considerar que o upload HTTP equivale a aprovação.[^39] A referência atual de `Mark Package As Shipped` lista US, UK, Espanha, Irlanda, Itália, Alemanha, França e Japão — não Brasil —, portanto o Shopman deve seguir o fluxo `Ship Package`/logística efetivamente habilitado no app BR e nunca inferir disponibilidade por nome de endpoint.[^40]

Webhooks Shop cobrem mudança de pedido, destinatário, pacote, produto/auditoria, desautorização, expiração próxima, cancelamento, retorno, invoice e outros. A URL deve ser HTTPS/TLS 1.2+, sem IP nem porta; o receptor valida assinatura e responde em até três segundos. Após falha, ocorrem até quatro retentativas (2 min, 30 min, 3 h e 12 h).[^35]

Os limites de Open API são dinâmicos por app, loja, endpoint e carga. Não existe uma cota fixa global consultável. O cliente deve limitar por app-shop-endpoint, preferir batch/cache e tratar HTTP 429 ou código `36009002` com backoff exponencial e jitter. Sandbox tem limite unificado de 1.000 requisições/hora por usuário de sandbox desde 2026.[^36]

#### TikTok Shop não é atalho para broadcast comum

A Open Platform possui APIs separadas de conteúdo comprável, incluindo upload de arquivo de “shoppable video”, mas elas pertencem ao domínio Affiliate Creator, usam autorização/token de creator e scope `creator.video.write`.[^41] O guia de integração Affiliate informa que as APIs ficam inativas por padrão e dependem de aprovação do Account/Partner Manager, app Affiliate separado e allowlist do `app_key`. O onboarding público de creator consultado não documenta o Brasil na lista de países e restringe contas de teste de creator a beta/allowlist.[^42]

Portanto, essa superfície não deve ser usada como plano B garantido para o broadcast. Mesmo se liberada no futuro, ela serviria a conteúdo comprável de um creator autorizado, não a posts orgânicos genéricos. A publicação comum continua pertencendo ao Content Posting API.

### 2.6 Homologação e testes

O Partner Center oferece Development Shops/test accounts com funcionalidade de Seller Center e autorização, apropriados para testar token, catálogo, pedido e webhook sem operar uma loja real.[^26] Para Connector/ERP/OMS, o App Requirement Document pode exigir fluxos completos e cenários de borda, não apenas uma chamada bem-sucedida.

Critérios de aceite recomendados antes de produção:

- produto rejeitado/aprovado atualizado por webhook;
- idempotência na criação e atualização de SKU;
- preço e estoque reconciliados;
- reserva em `UNPAID`, pagamento, cancelamento e expiração;
- on-hold, split/combine, tracking e falha de transportadora;
- devolução/reembolso e conciliação financeira;
- desautorização e refresh expirado;
- throttling, timeout e retentativa sem duplicar escrita;
- webhook duplicado, atrasado e fora de ordem;
- trilha de auditoria por `request_id`.

### 2.7 Custos e economia unitária

Não foi localizada, na documentação pública consultada, uma tabela de cobrança do TikTok pelo **uso das APIs**. Isso não prova gratuidade contratual; eventuais termos, mínimos ou acordos devem ser confirmados no Partner Center antes de compromisso comercial.

Os custos do seller são explícitos e relevantes. Desde 15 de julho de 2026, cada item vendido no Brasil tem:[^37]

| Preço após desconto do seller | Comissão | Tarifa por item |
|---|---:|---:|
| abaixo de R$ 50 | 10% | R$ 4 |
| R$ 50 ou mais | 6% | R$ 6 |

Exemplos antes de frete, promoção, tributos, embalagem, perdas e afiliados:

- item de R$ 20: R$ 6 de tarifa, **30%**;
- item de R$ 49: R$ 8,90, **18,2%**;
- item de R$ 50: R$ 9, **18%**;
- kit de R$ 100: R$ 12, **12%**.

Isso torna item avulso barato especialmente desfavorável. A tese econômica, se a categoria for aprovada, deveria concentrar ticket em kits presenteáveis, shelf-stable e acima de R$ 50, com margem calculada depois de toda a logística. Promoções temporárias e incentivos exibidos no Seller Center não devem entrar como margem estrutural.

## 3. Recomendação para a Nelson Boulangerie

### 3.1 Roadmap em quatro gates

#### Gate 0 — decisão externa antes de código adicional

1. Confirmar quem é o titular da conta TikTok da Nelson e se a conta está em situação normal.
2. Criar organização/app no TikTok for Developers com propriedade empresarial.
3. Abrir consulta ao suporte descrevendo honestamente o caso Nelson-only e perguntar se Direct Post auditado é elegível.
4. Cadastrar seller no TikTok Shop apenas se a empresa quiser avaliar uma linha embalada; conferir CNPJ, conta bancária e documentos.
5. Pedir qualificação Food & Beverages no Centro de Qualificação e submeter lista/rotulagem dos SKUs candidatos.

A solicitação de categoria é feita no Seller Center desktop em **Minha conta → Configurações da conta → Centro de qualificação → Qualificação da categoria → Adicionar autorização**; o fluxo de qualificação é documentado como exclusivo de desktop.[^43]

**Saída:** resposta oficial sobre Direct Post e status de qualificação Shop. Sem isso, não assumir publicação pública nem elegibilidade de produto.

#### Gate 1 — Upload API funcional

Implementar no app Marketing:

- conexão OAuth TikTok com `video.upload` e `user.info.basic` somente se realmente necessário;
- armazenamento e refresh seguro;
- “Enviar rascunho ao TikTok” a partir do preview já aprovado;
- `PULL_FROM_URL` em domínio de mídia verificado;
- status `PROCESSING_*`, `SEND_TO_USER_INBOX`, `PUBLISH_COMPLETE`, `FAILED`;
- notificação clara “abra o TikTok no celular para revisar e publicar”;
- webhook idempotente + reconciliação por polling;
- validação MP4/H.264 e política de música comercial.

**Saída:** menos download/reupload manual, mas publicação continua intencional e finalizada no celular.

#### Gate 2 — Direct Post somente se pré-condições forem atendidas

Somente iniciar se o TikTok aceitar o posicionamento do produto e houver plano real de auditoria. Construir a UX obrigatória completa, sem reutilizar o botão de “disparar” como consentimento implícito. O operador deve chegar a uma etapa TikTok específica, ver a conta, preview, privacidade, interações, disclosure, música e confirmar.

**Saída:** teste privado primeiro; público somente após evidência no portal de cliente auditado e validação real de `PUBLIC_TO_EVERYONE`.

#### Gate 3 — TikTok Shop piloto opcional

Se e somente se existirem SKUs aprovados:

- começar por Seller Developer + Custom App 1:1;
- integrar Authorization, Product/Inventory e Orders/webhooks;
- operar fulfillment inicialmente no Seller Center se isso reduzir escopo;
- só automatizar fulfillment/finance depois de pedidos reais controlados;
- medir margem líquida, atrasos, avarias e devoluções por 30–60 dias;
- interromper se a categoria, prazo de validade ou embalagem gerar violações.

### 3.2 Matriz de risco

| Risco | Probabilidade | Impacto | Controle |
|---|---|---|---|
| Direct Post reprovado por uso interno | Alta | Alto | Consulta prévia; Upload API; produto multi-tenant real |
| Post comercial sem disclosure | Média | Alto | UI obrigatória; `brand_organic_toggle`; testes de contrato |
| Música sem direito comercial | Média | Alto | CML/som próprio; registro de licença; bloqueio por política |
| Disparo sem consentimento por automação | Média | Alto | confirmação por post; não transformar regra de campanha em chamada direta |
| Conteúdo fica privado | Alta antes da auditoria | Médio | estado explícito “privado/teste”; gate de produção |
| Duplicidade por webhook/retry | Média | Médio | idempotência por evento/publish_id/request_id |
| Venda de alimento proibido | Alta se catálogo fresco for sincronizado | Muito alto | allowlist de SKU/categoria; aprovação externa antes de sync |
| Margem negativa em item barato | Alta | Alto | kits > R$ 50; cálculo de contribuição; piloto limitado |
| Oversell multicanal | Média | Alto | reserva em pedido criado; inventário central; reconciliação |
| Token expirado/revogado | Média | Médio | refresh antecipado, rotação atômica, alertas, reautorização |
| Política/API muda | Alta | Médio | changelog, versionamento por endpoint, revisão trimestral |

### 3.3 Decisão final

Para a Nelson Boulangerie, **TikTok deve entrar primeiro como canal editorial, não como marketplace de produtos frescos**. O objetivo de curto prazo é permitir que o operador aprove uma campanha no Marketing, faça a última conferência TikTok e envie um rascunho que conclui no celular. Essa entrega é tecnicamente útil e compatível com as limitações públicas conhecidas.

Direct Post público deve permanecer atrás de feature flag e gate de elegibilidade. Se o TikTok negar a auditoria ao uso interno, a integração continua válida no modo Upload; não se deve procurar automação por navegador ou credenciais compartilhadas, pois isso adicionaria risco de conta e contrariaria o modelo oficial de autorização.

TikTok Shop deve ser tratado como experimento separado. O catálogo fresco é inelegível; só uma linha pré-embalada, não perecível e aprovada justifica o piloto. Mesmo então, a tarifa efetiva de itens baratos recomenda kits de ticket maior e uma prova econômica antes de integração ampla.

## 4. Checklist de evidências para go-live

### Content Posting

- [ ] Organização e app empresarial no TikTok for Developers
- [ ] Site institucional completo, Política de Privacidade e Termos visíveis
- [ ] Redirect URI HTTPS verificada
- [ ] Domínio/prefixo de mídia verificado
- [ ] Content Posting API adicionado
- [ ] `video.upload` aprovado e autorizado
- [ ] Demo E2E conforme app review
- [ ] OAuth/refresh/revoke testados
- [ ] Upload de vídeo e foto testado em conta-alvo
- [ ] Webhook autenticado, rápido e idempotente
- [ ] Música comercial e disclosure cobertos
- [ ] Se Direct Post: `video.publish` aprovado
- [ ] Se público: auditoria Direct Post aprovada no portal
- [ ] Se público: teste real de `publicly_available`, não só `PUBLISH_COMPLETE`

### TikTok Shop

- [ ] Seller BR aprovado com CNPJ e dados bancários
- [ ] Lista de SKU exclui perecíveis, cadeia fria e “caseiros” proibidos
- [ ] Qualificação Food & Beverages aprovada
- [ ] Rotulagem, validade e documentação validadas
- [ ] Developer onboarding e Custom App criados
- [ ] Registration/compliance/app review exigidos concluídos
- [ ] Development Shop usado nos testes
- [ ] Scopes mínimos aprovados
- [ ] Produto, estoque, pedido e webhook homologados
- [ ] SLA de expedição operacionalmente possível
- [ ] Margem líquida positiva após tarifas, frete, embalagem, imposto e afiliado

## Fontes

[^1]: TikTok for Developers. “[Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines).” Acesso em 12 set. 2026.
[^2]: TikTok for Developers. “[Upload](https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video).” Atualizado em 4 ago. 2026.
[^3]: TikTok Newsroom Brasil. “[TikTok Shop chega ao Brasil e inaugura a era da Compra por Descoberta](https://newsroom.tiktok.com/tiktok-shop-chega-ao-brasil?lang=pt-BR).” 8 maio 2025.
[^4]: TikTok Shop Academy Brasil. “[Política de Produtos Proibidos do TikTok Shop](https://seller-br.tiktok.com/university/essay?knowledge_id=6483182812481296).” 17 ago. 2026.
[^5]: TikTok for Developers. “[App Review FAQ](https://developers.tiktok.com/docs/en/getting-started-faq).” Atualizado em 4 ago. 2026.
[^6]: TikTok for Developers. “[Get Started — Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-get-started).” Atualizado em 4 ago. 2026.
[^7]: TikTok for Developers. “[Photo](https://developers.tiktok.com/docs/en/content-posting-api-reference-photo-post).” Atualizado em 24 ago. 2026.
[^8]: TikTok for Developers. “[App Review Guidelines](https://developers.tiktok.com/docs/en/app-review-guidelines).” Atualizado em 4 ago. 2026.
[^9]: TikTok for Developers. “[Developer Guidelines](https://developers.tiktok.com/docs/en/our-guidelines-developer-guidelines).” Acesso em 12 set. 2026.
[^10]: TikTok for Developers. “[Add a Sandbox](https://developers.tiktok.com/docs/en/add-a-sandbox).” Atualizado em 4 ago. 2026.
[^11]: TikTok for Developers. “[Login Kit for Web](https://developers.tiktok.com/docs/en/login-kit-web).” Acesso em 12 set. 2026.
[^12]: TikTok for Developers. “[User Access Token Management](https://developers.tiktok.com/docs/en/oauth-user-access-token-management).” Atualizado em 4 ago. 2026.
[^13]: TikTok for Developers. “[Query Creator Info](https://developers.tiktok.com/docs/en/content-posting-api-reference-query-creator-info).” Atualizado em 4 ago. 2026.
[^14]: TikTok Support. “[Promover uma marca, um produto ou um serviço](https://support.tiktok.com/pt_BR/business-and-creator/creator-and-business-accounts/promoting-a-brand-product-or-service?lang=pt_BR).” Acesso em 12 set. 2026.
[^15]: TikTok Support. “[Commercial use of music on TikTok](https://support.tiktok.com/en/business-and-creator/creator-and-business-accounts/commercial-use-of-music-on-tiktok?lang=en).” Acesso em 12 set. 2026.
[^16]: TikTok Business Help Center. “[Política de conteúdo de marca: requisitos específicos por mercado](https://ads.tiktok.com/resources/help/article/branded-content-policy-country-specific-requirements?lang=pt).” Atualizado em nov. 2025.
[^17]: TikTok for Developers. “[Media Transfer Guide](https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide).” Atualizado em 4 ago. 2026.
[^18]: TikTok for Developers. “[Get Post Status](https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status).” Atualizado em 4 ago. 2026.
[^19]: TikTok for Developers. “[Webhooks Overview](https://developers.tiktok.com/docs/en/webhooks-overview).” Acesso em 12 set. 2026.
[^20]: TikTok Shop Academy Brasil. “[Registro de Vendedores](https://seller-br.tiktok.com/university/essay?knowledge_id=3995530205677329&lang=pt-BR).” 18 dez. 2025.
[^21]: TikTok Shop Academy Brasil. “[Diretrizes para o período de experiência de loja nova](https://seller-br.tiktok.com/university/essay?from=ttsportal&identity=1&knowledge_id=1444948507379472&role=1).” 2 abr. 2026.
[^22]: TikTok Shop Academy Brasil. “[What are Invite Only Products?](https://seller-br.tiktok.com/university/essay?knowledge_id=6907568440706832&lang=en).” 3 dez. 2025.
[^23]: TikTok Shop Partner Center. “[Developer](https://partner.tiktokshop.com/docv2/page/developer).” Acesso em 12 set. 2026.
[^24]: TikTok Shop Partner Center. “[App launch overview](https://partner.tiktokshop.com/docv2/page/app-launch-overview).” Acesso em 12 set. 2026.
[^25]: TikTok Shop Partner Center. “[Publish and list a public App](https://partner.tiktokshop.com/docv2/page/publish-and-list-public-app).” Acesso em 12 set. 2026.
[^26]: TikTok Shop Partner Center. “[Authorization guide (202309)](https://partner.tiktokshop.com/docv2/page/authorization-guide-202309).” Acesso em 12 set. 2026.
[^27]: TikTok Shop Partner Center. “[Get Authorized Shops](https://partner.tiktokshop.com/docv2/page/get-authorized-shops).” Acesso em 12 set. 2026.
[^28]: TikTok Shop Partner Center. “[API versioning](https://partner.tiktokshop.com/docv2/page/api-versioning).” Acesso em 12 set. 2026.
[^29]: TikTok Shop Partner Center. “[TikTok Shop API concepts overview](https://partner.tiktokshop.com/docv2/page/tts-api-concepts-overview).” Acesso em 12 set. 2026.
[^30]: TikTok Shop Partner Center. “[Products API overview](https://partner.tiktokshop.com/docv2/page/products-api-overview).” Acesso em 12 set. 2026.
[^31]: TikTok Shop Partner Center. “[Inventory Search](https://partner.tiktokshop.com/docv2/page/inventory-search-202309).” Acesso em 12 set. 2026.
[^32]: TikTok Shop Partner Center. “[Order API overview](https://partner.tiktokshop.com/docv2/page/650b1b4bbace3e02b76d1011).” Acesso em 12 set. 2026.
[^33]: TikTok Shop Partner Center. “[Fulfillment API overview](https://partner.tiktokshop.com/docv2/page/650b2044f1fd3102b93c9178).” Acesso em 12 set. 2026.
[^34]: TikTok Shop Academy Brasil. “[Política de Logística](https://seller-br.tiktok.com/university/essay?default_language=en&knowledge_id=1444948508280592).” Acesso em 12 set. 2026.
[^35]: TikTok Shop Partner Center. “[Webhook configuration guide](https://partner.tiktokshop.com/docv2/page/configuration-guide).” Acesso em 12 set. 2026.
[^36]: TikTok Shop Partner Center. “[Rate limits](https://partner.tiktokshop.com/docv2/page/rate-limits).” Acesso em 12 set. 2026; TikTok Shop Partner Center. “[Sandbox Shops Rate Limiting & Inactive Seller Access Control](https://partner.tiktokshop.com/docv2/page/p9x5je85).” 15 jun. 2026.
[^37]: TikTok Shop Academy Brasil. “[Tarifa de Comissão da Plataforma](https://seller-br.tiktok.com/university/essay?knowledge_id=24428156307201).” 12 jun. 2026; vigente desde 15 jul. 2026.
[^38]: TikTok Shop Partner Center. “[Regions and languages](https://partner.tiktokshop.com/docv2/page/regions-and-languages).” Acesso em 12 set. 2026; “[Development Shops](https://partner.tiktokshop.com/docv2/page/ar5ppjvv).” Acesso em 12 set. 2026.
[^39]: TikTok Shop Partner Center. “[BR market — updated API workflow to support order invoice and warehouse](https://partner.tiktokshop.com/docv2/page/br-market-updated-api-workflow-to-support-order-invoice-and-warehouse).” 7 mar. 2025.
[^40]: TikTok Shop Partner Center. “[Mark Package As Shipped](https://partner.tiktokshop.com/docv2/page/mark-package-as-shipped-202309).” Acesso em 12 set. 2026; “[Ship Package](https://partner.tiktokshop.com/docv2/page/ship-package-202309).” Acesso em 12 set. 2026.
[^41]: TikTok Shop Partner Center. “[Upload Shoppable Video File](https://partner.tiktokshop.com/docv2/page/upload-shoppable-video-file-202505).” Acesso em 12 set. 2026.
[^42]: TikTok Shop Partner Center. “[Affiliate integration](https://partner.tiktokshop.com/docv2/page/affiliate-integration).” Acesso em 12 set. 2026; “[Creator authorization guide](https://partner.tiktokshop.com/docv2/page/creator-authorization-guide).” Acesso em 12 set. 2026.
[^43]: TikTok Shop Academy Brasil. “[Como solicitar acesso a categorias restritas](https://seller-br.tiktok.com/university/essay?default_language=pt-BR&knowledge_id=6911810440005392).” 17 jul. 2026.
