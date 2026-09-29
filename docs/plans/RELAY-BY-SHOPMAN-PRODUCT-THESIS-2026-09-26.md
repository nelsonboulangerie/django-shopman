# Relay by Shopman — tese de produto e fronteira técnica

Status: hipótese de produto; arquitetura preparada, spin-off ainda não autorizado

Data: 2026-09-26

## 1. Veredito franco

Há potencial real de produto, mas ainda não há validação suficiente para tratá-lo como uma empresa ou plataforma autônoma.

A dor existe: produtos verticais precisam publicar em várias redes, acompanhar resultados, sobreviver a OAuth, permissões, formatos, quotas e mudanças de API. Concorrentes como Ayrshare, Publer, Buffer e Post Bridge mostram demanda e disposição de pagamento. Eles também provam que o mercado já é disputado e que “uma API para redes sociais” isoladamente não é diferenciação defensável.

O Relay pode vencer se for a camada de **publicação confiável e UX hospedada para softwares verticais**, não um proxy genérico de endpoints. O valor deve estar em:

- capabilities observadas por conta, em vez de documentação estática;
- composer hospedado que nunca oferece uma opção inválida;
- validação e transformação de mídia;
- idempotência, reconciliação e status uniforme;
- trilha de aprovação/auditoria;
- integração progressiva, começando por destinos totalmente operacionais;
- experiência explícita para diferenças de cada plataforma.

Shopman será o primeiro e principal cliente de design. Não pode ser o único cliente disfarçado: isso enfraquece a tese comercial e, no caso do TikTok, não atende ao perfil de produto amplo esperado para aprovação de Direct Post.

## 2. Fronteira de responsabilidade

### Shopman continua dono de

- campanhas e objetivos comerciais;
- promoções, cupons, preço, estoque e regras da loja;
- segmentos de clientes, consentimento comercial e audiência;
- aprovação interna da campanha;
- linguagem e fluxos específicos do varejo/alimentação;
- decisão de quando criar, pausar ou repetir uma campanha.

### Relay passa a ser dono de

- OAuth e renovação de tokens;
- descoberta de contas, Pages, locations e perfis;
- capabilities teóricas, implementadas e observadas;
- formatos, campos, CTA e restrições por destino;
- ingestão, inspeção e derivados de mídia;
- composer/preview hospedado quando necessário para compliance;
- publicação, idempotência, retry seguro e reconciliação;
- status uniforme, recibos externos e webhooks;
- auditoria técnica do consentimento de publicação.

Relay não conhece regras de promoção, disponibilidade de produto, margem, CRM ou significado comercial do cupom. Ele recebe uma composição aprovada e executa uma veiculação.

```text
Shopman CampaignPlan
       │ cria destinos e composições aprovadas
       ▼
Relay PublicationSet
       ├── Destination: Instagram / @nelson / Feed
       ├── Destination: Facebook / Página Centro / Feed
       ├── Destination: Google / Loja Jardins / Offer
       └── Destination: WhatsApp / Conta Principal / Template
                   │
                   ▼
          Delivery + Receipt + Webhook
```

## 3. Contrato mínimo Relay-ready

O Marketing V2 não precisa chamar um serviço externo agora. Precisa evitar dependências que tornem a extração futura cara.

### Recursos

- `Connection`: vínculo OAuth e contas descobertas.
- `CapabilitySnapshot`: possibilidades observadas e versão usada na composição.
- `PublicationSet`: conjunto aceito atomicamente pelo Relay.
- `Destination`: conta + plataforma + formato.
- `Composition`: conteúdo e mídia específicos do destino.
- `Delivery`: tentativa externa independente.
- `Receipt`: identificador/status devolvido pela plataforma.

### Envelope conceitual

```json
{
  "client_reference": "shopman:campaign:cmp_123",
  "destinations": [
    {
      "client_reference": "shopman:destination:dst_456",
      "connection_id": "conn_google_jardins",
      "format": "offer",
      "capability_snapshot_version": "2026-09-26T12:00:00Z",
      "composition": {
        "summary": "A primavera chegou à Nelson.",
        "media": [{"asset_id": "asset_hibisco_4x3"}],
        "offer": {
          "title": "15% OFF no Hibisco",
          "coupon_code": "PRIMAVERA15",
          "redeem_url": "https://example.invalid/resgatar/primavera15",
          "terms": "Válido enquanto durarem os estoques."
        }
      },
      "publish_at": "2026-09-28T11:00:00Z",
      "idempotency_key": "shopman:cmp_123:dst_456:v3"
    }
  ]
}
```

Esse exemplo é um contrato de fronteira, não uma API pública congelada. Segredos, URLs reais e identificadores pessoais não pertencem a fixtures ou documentação.

### Invariantes

1. O catálogo de capabilities informa a UI, mas não autoriza efeitos.
2. Apenas formatos na allow-list executável do adapter podem ser selados.
3. A aceitação do conjunto é transacional; cada veiculação externa é independente.
4. Sucesso parcial não provoca rollback de publicações bem-sucedidas.
5. Resultado desconhecido é reconciliado antes de retry.
6. Cada destino guarda a versão de capabilities usada na aprovação.
7. O preview usa o mesmo derivado de mídia que será selado.
8. Webhooks são autenticados, deduplicados e reprocessáveis.

## 4. TikTok: caminho permitido, sem promessa prematura

### Primeira integração candidata

Quando Relay já for um produto público e multi-tenant, a primeira proposta ao TikTok deve ser o fluxo de upload/rascunho:

- escopo `video.upload`;
- envio de vídeo ou fotos para a caixa de entrada do creator;
- conclusão de edição, música, privacidade e publicação no TikTok;
- estado no Relay: `awaiting_creator_completion`, nunca `published` por inferência.

Para `PULL_FROM_URL`, o Relay precisa hospedar a mídia em domínio/prefixo verificado; não deve repassar URLs arbitrárias de clientes.

### Direct Post

Direct Post só entra depois de:

- produto público com usuários externos reais;
- Login Kit e consentimento explícito;
- composer que consulta `creator_info` antes de cada publicação;
- opções de privacidade devolvidas dinamicamente pela API;
- disclosures e controles obrigatórios;
- auditoria aprovada para `video.publish`.

Clientes não auditados ficam sujeitos às restrições de teste/visibilidade da plataforma. Um utilitário privado para publicar apenas em contas administradas pelo próprio time não deve ser apresentado como caso elegível.

## 5. Sequência de produto

### Fase A — Shopman funcional sem TikTok

- concluir Marketing V2 para Instagram, Facebook, Google e WhatsApp;
- adotar `CampaignDestination`, composição por destino e veiculação independente;
- manter adapters dentro do monólito, atrás de uma porta Relay-ready;
- medir taxa de sucesso, tempo de composição, retries e suporte.

### Fase B — Relay interno multi-tenant

- extrair autenticação, capabilities, mídia e delivery para um serviço isolado;
- usar Shopman como primeiro tenant real;
- preservar a mesma semântica e idempotency keys;
- oferecer hosted composer como componente incorporável.

### Fase C — validação externa

- recrutar 3–5 parceiros de design que operem software vertical;
- cobrar desde o piloto ou obter carta de intenção com preço e volume;
- validar onboarding sem intervenção do time;
- validar se o comprador prefere API, componente hospedado ou ambos.

### Fase D — TikTok e escala

- submeter produto público ao review;
- começar por upload/rascunho;
- pedir Direct Post apenas após uso externo e UX compatível;
- adicionar plataforma somente com sandbox proof, contract test e observabilidade.

## 6. Gates para continuar ou parar

Não separar Relay como produto autônomo antes de atingir pelo menos um dos sinais abaixo:

- três clientes externos pagantes; ou
- cinco cartas de intenção concretas, com volume e faixa de preço; ou
- um parceiro de distribuição capaz de trazer dez integrações qualificadas.

Além disso, o piloto precisa demonstrar:

- publicação bem-sucedida acima de 99% excluindo rejeições corretas de conteúdo;
- zero duplicação externa em retry;
- diagnóstico acionável para falhas conhecidas;
- integração inicial em dias, não semanas;
- margem que comporte suporte e mudanças contínuas das plataformas.

Se os parceiros pedirem apenas agendamento básico e não pagarem pela confiabilidade/API, o Relay deve permanecer infraestrutura interna do Shopman.

## 7. Nome

`Relay by Shopman` é um bom codinome: comunica encaminhamento sem usar a marca de uma rede. Antes de exposição pública, exige busca de marca e domínio.

Nomes com `Tok` — `ApiTok`, `BridgeTok`, `LinkTok` — devem ser descartados: restringem o produto a uma plataforma, podem conflitar com marcas existentes e contrariam a orientação de review de não apoiar o nome do app na marca da rede.

## 8. Fontes primárias e sinais de mercado

- TikTok — Content Posting API: <https://developers.tiktok.com/docs/en/content-posting-api-get-started>
- TikTok — Upload Content: <https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content>
- TikTok — Content Sharing Guidelines: <https://developers.tiktok.com/doc/content-sharing-guidelines>
- TikTok — App Review Guidelines: <https://developers.tiktok.com/docs/en/app-review-guidelines>
- Buffer — publicação TikTok automática e por notificação: <https://support.buffer.com/en-us/articles/using-tiktok-with-buffer-oGEroY9Of2>
- Ayrshare — produto e posicionamento: <https://www.ayrshare.com/>
- Publer — API pública: <https://publer.com/help/en/article/does-publer-have-a-public-api-194nknf/>
- Post Bridge — API social para agentes/produtos: <https://www.post-bridge.com/agents>
