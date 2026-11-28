# Merchant: preservar configuração existente do alpha

O artefato `watchman-infrastructure-40909702803`, execução de 29/10/2026,
identificou duas variáveis no vivo que sumiriam num update do spec:
`GOOGLE_MERCHANT_PROJECTION` e `GOOGLE_MERCHANT_SERVICE_ACCOUNT_B64`.

A configuração versionada do alpha passa a declarar a projeção com valor `1`,
conforme o passo 6 do plano `CATALOG-PUSH-GOOGLE-META-PLAN.md`, e a conta de
serviço como `SECRET`, sem valor. Nenhuma credencial foi lida ou gravada e
nenhum update foi executado no ambiente online.

O Watchman deve ser reexecutado após o merge para confirmar o contrato completo
contra o vivo. Esta correção não afirma que o sync comercial foi ensaiado nem
altera o opt-in de publicação do Marketing.
