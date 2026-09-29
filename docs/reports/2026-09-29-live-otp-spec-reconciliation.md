# OTP de debug e reconciliação segura do spec vivo

- `executado_em`: `2026-09-29T09:10Z`–`2026-09-29T09:19Z`
- `app`: `shopman-nelson`
- `deployment_ativo`: `074e8964-1050-49e0-98a1-215ae2bf2178`
- `deployment_anterior`: `02527053-d135-4bd3-9d32-d09dd367be19`
- `escopo`: desligar OTP de debug e impedir a perda de variáveis somente no vivo

## Resultado

O spec foi composto a partir do app vivo. Nenhum valor secreto foi lido ou
registrado. A comparação estrutural antes/depois confirmou que as únicas mudanças
de comportamento foram:

1. `SHOPMAN_EXPOSE_DEBUG_OTP`: `true` para `false`;
2. o job `release` passou a executar `migration_safety` entre `check --deploy` e
   `migrate`.

As nove variáveis de app que existiam somente no vivo foram declaradas no
blueprint versionado. As três variáveis de recibo de privacidade do serviço
`web` também foram declaradas com tipo e escopo corretos; as duas chaves HMAC
continuam sem valor no Git.

O drift destrutivo foi eliminado: a conferência já não encontra variáveis que
**sumiriam** num `apps update --spec`. Diferenças deliberadas entre o blueprint
seguro e flags operacionais vivas continuam visíveis e ainda exigem composição a
partir do vivo; este trabalho não ligou ou desligou Marketing, Concierge,
pagamentos, fiscal, 2FA, DNS ou canais.

## Incidente contido durante a aplicação

A credencial de leitura da DigitalOcean omite os vínculos dos componentes
`postgres` e `cache`. As duas primeiras tentativas receberam `InternalError` em
`build.components.postgres`, antes do PRE_DEPLOY; o deployment anterior permaneceu
ativo e saudável. Não houve migration nem troca de instância nessas tentativas.

O spec foi recomposto com os vínculos canônicos dos clusters já versionados e
validado por `doctl apps propose`, sem warnings. O deployment seguinte concluiu
build e deploy com sucesso. Esse achado reforça a regra: um spec retornado por uma
credencial sem `database:read` não pode ser reaplicado sem recompor os bindings.

## Evidências sanitizadas

- spec vivo: OTP de debug `false`, 130 envs de app, quatro serviços e um job;
- preservação: nove envs live-only de app e três envs de recibo no `web` presentes;
- release: `migration-safety: clear`, nenhuma migration a aplicar e grupos OK;
- readiness: HTTP 200;
- menu: HTTP 200 e contrato de produto/disponibilidade válido;
- checkout BFF não mutante: HTTP 403 com `authentication_required`;
- SSR: HTTP 200, conteúdo Nelson e 141.511 bytes.

Não foram criados pedido, pagamento, estorno, emissão fiscal, mensagem, campanha,
promoção ou alteração de credencial.

## Rollback

O deployment anterior permanece identificado acima na plataforma. O snapshot
sanitizado do antes e o spec candidato foram comparados por hash durante a janela;
arquivos temporários com valores cifrados não pertencem ao repositório e devem ser
descartados ao encerrar a operação. Um rollback não deve reativar OTP de debug:
em incidente, restaure o deployment anterior somente para recuperar serviço e
reaplique imediatamente `SHOPMAN_EXPOSE_DEBUG_OTP=false` no spec vivo.
