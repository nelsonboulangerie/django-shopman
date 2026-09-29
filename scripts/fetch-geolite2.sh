#!/bin/sh
# Baixa a base GeoLite2-City para dentro da imagem, no BUILD.
#
# Esta é a base que escreve "Próximo a Londrina, PR · Brasil" ao lado do aparelho
# confiável na tela "Segurança e dados" da loja. Ela é lida do DISCO, em tempo de
# exibição: o IP do titular nunca sai da casa. Ver shopman/shop/services/ip_location.py.
#
# ⚠️ FALHA SUAVE DE PROPÓSITO. Sem chave, o script sai com 0 e a imagem sobe sem a base.
# A tela então degrada para "navegador e data", que é exatamente o estado em que a PR #991
# a deixou — nada quebra. O contrário (build vermelho por falta de um rótulo de cidade)
# transformaria um enfeite em bloqueio de deploy, e ninguém quer descobrir isso às 3h.
#
# ⚠️ O download é VERIFICADO por sha256 publicado pela própria MaxMind. Um binário de
# 60 MB que entra na imagem e é lido por código de produção não entra sem conferência.
#
# Uso:
#   scripts/fetch-geolite2.sh /app/data/GeoLite2-City.mmdb
#
# A chave vem de uma destas, nesta ordem:
#   1. /run/secrets/maxmind_license_key   (BuildKit: --secret id=maxmind_license_key,...)
#   2. $MAXMIND_LICENSE_KEY               (build arg — ver a ressalva no Dockerfile)

set -eu

DESTINO="${1:?uso: fetch-geolite2.sh <caminho/do/GeoLite2-City.mmdb>}"

CHAVE=""
if [ -r /run/secrets/maxmind_license_key ]; then
    CHAVE="$(cat /run/secrets/maxmind_license_key)"
fi
if [ -z "$CHAVE" ]; then
    CHAVE="${MAXMIND_LICENSE_KEY:-}"
fi

if [ -z "$CHAVE" ]; then
    echo "geolite2: sem MAXMIND_LICENSE_KEY — a imagem sobe SEM a base de cidade."
    echo "geolite2: a tela de aparelhos fica só com navegador e data (degradação prevista)."
    echo "geolite2: para ligar, ver docs/guides/geolite2-city.md."
    exit 0
fi

BASE_URL="https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=${CHAVE}"
TMP="$(mktemp -d)"
# shellcheck disable=SC2064
trap "rm -rf '$TMP'" EXIT

echo "geolite2: baixando GeoLite2-City…"
# ⚠️ `--fail` não é zelo: sem ele o curl grava a PÁGINA DE ERRO da MaxMind (chave
# inválida, cota estourada) como se fosse o tarball, e a falha só apareceria quando o
# `maxminddb` tentasse abrir o arquivo — em produção, meses depois.
curl -fsSL "${BASE_URL}&suffix=tar.gz"        -o "$TMP/base.tar.gz"
curl -fsSL "${BASE_URL}&suffix=tar.gz.sha256" -o "$TMP/base.sha256"

# O arquivo de checksum da MaxMind vem como "<sha256>  <nome-do-tarball-com-data>".
# O nome de lá não é o nome daqui, então comparamos só o dígito.
ESPERADO="$(cut -d' ' -f1 < "$TMP/base.sha256")"
# `sha256sum` no Debian da imagem; `shasum -a 256` no macOS de quem roda isto à mão para
# conferir a receita antes de mexer no Dockerfile.
if command -v sha256sum >/dev/null 2>&1; then
    OBTIDO="$(sha256sum "$TMP/base.tar.gz" | cut -d' ' -f1)"
else
    OBTIDO="$(shasum -a 256 "$TMP/base.tar.gz" | cut -d' ' -f1)"
fi
if [ "$ESPERADO" != "$OBTIDO" ]; then
    echo "geolite2: ✖ sha256 NÃO confere (esperado $ESPERADO, obtido $OBTIDO)." >&2
    echo "geolite2: o download não entra na imagem." >&2
    exit 1
fi

# O tarball traz um diretório com a data da edição (GeoLite2-City_20260923/).
tar -xzf "$TMP/base.tar.gz" -C "$TMP"
ENCONTRADO="$(find "$TMP" -name 'GeoLite2-City.mmdb' -type f | head -n 1)"
if [ -z "$ENCONTRADO" ]; then
    echo "geolite2: ✖ o tarball não tinha GeoLite2-City.mmdb dentro." >&2
    exit 1
fi

mkdir -p "$(dirname "$DESTINO")"
cp "$ENCONTRADO" "$DESTINO"
echo "geolite2: ✓ base em $DESTINO ($(wc -c < "$DESTINO") bytes), sha256 conferido."
