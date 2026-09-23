"""A cidade aproximada de um IP, lida de uma base LOCAL, sem terceiro no caminho.

## Por que este módulo existe, e por que ele não faz rede

Até 23/09/2026 a tela "Segurança e dados" da loja escrevia a cidade ao lado de cada
dispositivo confiável mandando o IP do titular para o `ip-api.com`, em HTTP puro, sem TLS,
uma requisição de até 2 s **por dispositivo**, bloqueando o render. A PR #991 removeu a
chamada e a linha ficou só com navegador e data.

O rótulo, porém, tinha função: é ele que responde "fui eu que entrei?" quando a pessoa
não reconhece o navegador. A decisão do dono (23/09/2026) foi trazer a cidade de volta
**sem terceiro** — base de geolocalização local, lida do disco, dentro da imagem.

⚠️ **Nada aqui pode falar com a rede.** A dependência instalada é o `maxminddb`, o leitor
puro do formato, e não o `geoip2`: o `geoip2` embute também o cliente do *web service* da
MaxMind (com `requests`/`urllib3` atrás), e um cliente HTTP que existe é um cliente HTTP
que alguém chama. Não ter o código é mais forte que decidir não usá-lo. A trava
`shopman/shop/tests/test_no_plaintext_third_party_calls.py` cuida do esquema; o teste
`test_the_ip_of_the_owner_never_leaves_for_a_third_party` cuida da saída.

## A base: GeoLite2-City, e não a DB-IP Lite

A primeira escolha foi a DB-IP Lite, que não pede conta nem chave. **Ela foi medida e
reprovada**, em 3.000.000 de registros da `dbip-city-lite` de 2026-09:

- `location.accuracy_radius`: **0 ocorrências**. O `location` traz só `latitude` e
  `longitude`. Sem raio, não há como saber se a leitura é confiável — e mostrar sempre é
  justamente o que a decisão do dono proíbe.
- `subdivisions[].iso_code`: **0 ocorrências**. Vem só o nome por extenso ("Paraná"),
  nunca a sigla. A frase escolhida pelo dono é "Próximo a Londrina, PR · Brasil", com a
  sigla do estado.

Duas reprovações independentes, cada uma sozinha bastante. A GeoLite2-City tem os dois
campos — conferido nas fixtures oficiais da MaxMind (`GeoLite2-City-Test.mmdb`):
`accuracy_radius` em 242 de 242 registros, `iso_code` presente em `subdivisions`, e
`country.names["pt-BR"]` com o nome do país em português.

⚠️ **O preço da troca**: a GeoLite2 exige conta e chave de licença na MaxMind, e essa
chave passa a ser parte do deploy (`MAXMIND_LICENSE_KEY`, segredo de build). Ver o
`Dockerfile` e `docs/guides/geolite2-city.md`.

## O limiar, e por que ele não é chute

Ver `GEOIP_CITY_MAX_ACCURACY_RADIUS_KM` em `config/settings.py`: o número sai da distância
medida entre cidades brasileiras vizinhas, não de preferência.

## Falha fechado, sempre

Base ausente, IP privado, leitura sem cidade, sem sigla de estado, sem raio, ou com raio
acima do limiar: a resposta é `None` e a tela simplesmente **não mostra a linha**. Nunca
um palpite. É por isso que a incerteza que sobra (a sigla que a MaxMind publica para os
estados brasileiros não pôde ser conferida aqui sem a chave) não vira risco de tela
errada: se o campo não vier, não há linha.
"""

from __future__ import annotations

import ipaddress
import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Estado do leitor da base. `_reader` é `None` enquanto ninguém pediu nada e também
#: quando a base não existe — `_reader_resolved` é o que distingue os dois, para que a
#: ausência do arquivo seja descoberta UMA vez e não a cada dispositivo da lista.
_reader = None
_reader_resolved = False
_reader_lock = threading.Lock()


@dataclass(frozen=True)
class ApproximateCity:
    """Uma leitura que passou no teste de confiança. Nunca um palpite.

    `radius_km` fica no dataclass para o log e para o teste, não para a tela: quem lê a
    tela não tem o que fazer com "67% de confiança em 20 km", e o "Próximo a" da frase já
    comunica a aproximação sem nota de rodapé.
    """

    city: str
    region_code: str
    country: str
    radius_km: int

    @property
    def label(self) -> str:
        """"Londrina, PR · Brasil" — o miolo da frase, sem o "Próximo a".

        O prefixo é copy do Omotenashi (`DEVICE_LIST_NEAR_PREFIX`) e fica na tela, porque
        é ele que o dono pode reescrever no Admin sem mexer em código.
        """
        return f"{self.city}, {self.region_code} · {self.country}"


def _database_path() -> str:
    from django.conf import settings

    return getattr(settings, "GEOIP_CITY_DATABASE_PATH", "") or ""


def _max_radius_km() -> int:
    from django.conf import settings

    return int(getattr(settings, "GEOIP_CITY_MAX_ACCURACY_RADIUS_KM", 0) or 0)


def _get_reader():
    """Abre a base UMA vez e reaproveita — a lista de dispositivos não pode abrir por linha.

    ⚠️ O `MODE_MMAP` não é detalhe de performance: mapeia o arquivo uma vez e serve
    leituras concorrentes sem reabrir descritor, que é o que um servidor ASGI precisa.
    Reabrir por dispositivo traria de volta, em forma de I/O, exatamente o custo por dispositivo
    que a chamada de rede tinha.
    """
    global _reader, _reader_resolved

    if _reader_resolved:
        return _reader

    with _reader_lock:
        # Outro thread pode ter resolvido enquanto este esperava o lock.
        if _reader_resolved:
            return _reader

        path = _database_path()
        try:
            import maxminddb

            _reader = maxminddb.open_database(path, maxminddb.MODE_MMAP)
        except (FileNotFoundError, IsADirectoryError):
            # Esperado em desenvolvimento e na CI, onde a base não é baixada. É `info` e
            # não `warning` de propósito: a tela degrada para "sem a linha da cidade", que
            # é exatamente o estado que a PR #991 deixou, e não há nada a consertar.
            #
            # As duas exceções foram MEDIDAS no `maxminddb` 3.2.0, não supostas: caminho
            # vazio e caminho inexistente levantam `FileNotFoundError`; caminho que é um
            # diretório levanta `IsADirectoryError`. Arquivo corrompido NÃO cai aqui —
            # cai no `except` de baixo, que grita, porque aí há o que consertar.
            logger.info(
                "geoip_city_database_absent path=%s — a tela de dispositivos segue sem a "
                "linha de cidade (degradação esperada fora da imagem de produção)",
                path or "(GEOIP_CITY_DATABASE_PATH vazio)",
            )
            _reader = None
        except Exception:
            # Arquivo existe e não abre: base corrompida ou truncada no build. Isso é
            # defeito de verdade e precisa gritar — mas sem derrubar a tela de segurança,
            # que responde muito mais coisa que a cidade.
            logger.exception("geoip_city_database_unreadable path=%s", path)
            _reader = None

        _reader_resolved = True
        return _reader


def reset_reader_cache() -> None:
    """Esquece a base aberta. Existe para os TESTES, que trocam o caminho por fixture."""
    global _reader, _reader_resolved

    with _reader_lock:
        if _reader is not None:
            try:
                _reader.close()
            except Exception:  # pragma: no cover - fechar já fechado não interessa a ninguém
                logger.debug("geoip_city_reader_close_failed", exc_info=True)
        _reader = None
        _reader_resolved = False


def _is_worth_asking(ip: str) -> bool:
    """O IP pode ter cidade? Laço local, rede interna e afins nunca têm.

    ⚠️ Era `ip.startswith("127.") or ip.startswith("10.")` no código antigo, e isso deixava
    passar `172.16.0.0/12` e `192.168.0.0/16` — as duas faixas privadas mais comuns atrás
    de um proxy. `ipaddress` conhece todas, inclusive as de IPv6, e ainda rejeita o que não
    é IP nenhum.
    """
    if not ip:
        return False
    try:
        parsed = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    return not (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_multicast
        or parsed.is_unspecified
    )


def approximate_city(ip: str | None) -> ApproximateCity | None:
    """A cidade de um IP, **só quando a leitura é confiável**. Senão, `None`.

    A regra de exibição é o ponto da decisão do dono, e mora aqui e não na tela: quem
    monta a tela não tem como julgar um raio de precisão, e espalhar esse julgamento por
    superfície é como se perde a regra. A tela pergunta "tem cidade?" e recebe sim ou não.
    """
    if not _is_worth_asking(ip or ""):
        # ⚠️ Sai ANTES de tocar na base. Não é economia de I/O: é a garantia, exercitada em
        # teste, de que IP de rede interna não vira consulta nenhuma.
        return None

    reader = _get_reader()
    if reader is None:
        return None

    try:
        record = reader.get(ip.strip())
    except Exception:
        logger.exception("geoip_city_lookup_failed")
        return None

    if not isinstance(record, dict):
        return None

    location = record.get("location") or {}
    radius = location.get("accuracy_radius")
    if not isinstance(radius, int):
        # Sem raio não há como saber se a leitura serve. A base escolhida publica o campo
        # em todo registro; se um dia parar, o certo é não mostrar, não é assumir preciso.
        return None

    limit = _max_radius_km()
    if limit <= 0 or radius > limit:
        return None

    city = _localized(record.get("city"))
    country = _localized(record.get("country"))
    subdivisions = record.get("subdivisions") or []
    region_code = ""
    if subdivisions and isinstance(subdivisions[0], dict):
        region_code = (subdivisions[0].get("iso_code") or "").strip()

    if not city or not country or not region_code:
        # Falta peça da frase. "Próximo a Londrina · Brasil" sem a sigla, ou "Próximo a
        # , PR · Brasil" sem a cidade, é pior que não ter linha: vira defeito visível.
        return None

    return ApproximateCity(
        city=city,
        region_code=region_code,
        country=country,
        radius_km=radius,
    )


def _localized(node) -> str:
    """O nome em português quando a base tem, o inglês quando não tem.

    ⚠️ Para cidade brasileira os dois são a mesma palavra ("Londrina", "Maringá"), então o
    `en` não é um consolo: é o mesmo texto. Onde o `pt-BR` faz diferença de verdade é no
    país — "Brasil" e não "Brazil" —, e aí a base publica o campo.
    """
    if not isinstance(node, dict):
        return ""
    names = node.get("names") or {}
    if not isinstance(names, dict):
        return ""
    return (names.get("pt-BR") or names.get("en") or "").strip()
