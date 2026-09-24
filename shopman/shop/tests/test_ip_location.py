"""A cidade aproximada do dispositivo: quando aparece, quando NÃO aparece, e o que nunca sai.

Estes testes prendem três promessas, e cada uma já foi quebrada uma vez ou está a um
descuido de ser:

1. **Nada sai para a rede.** A tela "Segurança e dados" mandava o IP do titular para o
   `ip-api.com` em HTTP puro (removido na PR #991). A volta do rótulo, em 23/09/2026, é
   por base LOCAL — e "local" é afirmação que precisa de prova, não de comentário.
2. **A leitura ruim não vira rótulo.** A base devolve um raio de precisão junto com a
   resposta, e é ele que decide. Em celular, onde o IP aponta a saída da operadora, a
   linha tem de ficar só com navegador e data.
3. **A base abre UMA vez.** O defeito original não era só o vazamento: era uma requisição
   de até 2 s *por dispositivo*, bloqueando o render. Trocar isso por um `open()` por dispositivo
   seria repetir o erro em outra moeda.

⚠️ Os dicionários de registro abaixo não são inventados: são a forma REAL da GeoLite2-City,
copiada da fixture oficial da MaxMind (`GeoLite2-City-Test.mmdb`, 242 registros, todos com
`location.accuracy_radius`), com os nomes trocados para cidade brasileira. Se a MaxMind
mudar o formato, o que falha é o código de produção, e não estes testes — por isso o
`test_a_base_de_verdade_falha_fechada` exercita o `maxminddb` de verdade.
"""

from __future__ import annotations

import datetime

import pytest

from shopman.shop.services import ip_location
from shopman.shop.tests.mmdb_fixtures import mmdb_minimo


@pytest.fixture(autouse=True)
def _base_limpa():
    """Cada teste começa sem leitor aberto e termina sem deixar um para o vizinho."""
    ip_location.reset_reader_cache()
    yield
    ip_location.reset_reader_cache()


def _registro(*, radius=20, city="Londrina", uf="PR", country="Brasil"):
    """Um registro no formato da GeoLite2-City. Omitir uma chave = a base não trouxe."""
    registro: dict = {"location": {"latitude": -23.3103, "longitude": -51.1628}}
    if radius is not None:
        registro["location"]["accuracy_radius"] = radius
    if city is not None:
        registro["city"] = {"geoname_id": 3458449, "names": {"en": city}}
    if uf is not None:
        registro["subdivisions"] = [{"geoname_id": 3455077, "iso_code": uf, "names": {"en": "Paraná"}}]
    if country is not None:
        registro["country"] = {"iso_code": "BR", "names": {"en": "Brazil", "pt-BR": country}}
    return registro


class _MetadadosFalsos:
    """Só o campo que a trava de idade usa — é o contrato inteiro que ela precisa."""

    def __init__(self, build_epoch: int):
        self.build_epoch = build_epoch


class _BaseFalsa:
    """Um leitor de base que conta quantas vezes foi consultado.

    ⚠️ Ele responde `metadata()` e `close()` porque o leitor de VERDADE responde. Os
    testes que exercitam o `_get_reader` real (a abertura única, por exemplo) passam por
    esses dois métodos, e um falso que não os tem faria esses testes medirem o caminho de
    erro achando que medem o caminho bom.
    """

    def __init__(self, registro=None, *, build_epoch: int | None = None):
        self.registro = registro
        self.consultas: list[str] = []
        self.build_epoch = (
            build_epoch
            if build_epoch is not None
            else int(datetime.datetime.now(datetime.UTC).timestamp())
        )
        self.fechado = False

    def get(self, ip):
        self.consultas.append(ip)
        return self.registro

    def metadata(self):
        return _MetadadosFalsos(self.build_epoch)

    def close(self):
        self.fechado = True


@pytest.fixture
def base(monkeypatch):
    """Instala uma base falsa, com IDADE, e conta quantas VEZES ela foi aberta.

    ⚠️ A base falsa nasce **recém-construída**, e o default importa: trocar o leitor por
    um falso pula o `_get_reader` de verdade, que é quem lê a data do arquivo. Sem cravar
    a data aqui, toda base falsa teria idade desconhecida — e idade desconhecida conta
    como velha, o que faria a suíte inteira testar o caminho errado achando que testa o
    certo. `idade_dias` é o que os testes de envelhecimento giram.
    """
    aberturas = []

    def _instalar(registro=None, *, idade_dias: int = 0, sem_data: bool = False):
        falsa = _BaseFalsa(registro)

        def _abrir():
            aberturas.append(falsa)
            return falsa

        monkeypatch.setattr(ip_location, "_get_reader", _abrir)
        epoch = None
        if not sem_data:
            construida = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
                days=idade_dias
            )
            epoch = int(construida.timestamp())
        monkeypatch.setattr(ip_location, "_build_epoch", epoch)
        falsa.aberturas = aberturas
        return falsa

    return _instalar


# ── A leitura confiável vira a frase escolhida pelo dono ─────────────────────


def test_a_leitura_confiavel_vira_a_frase_do_dono(base, settings):
    """A frase é "Próximo a Londrina, PR · Brasil" — cidade, sigla do estado, país.

    O "Próximo a" não está aqui: é copy do Omotenashi e mora na tela, para o dono poder
    reescrever no Admin. O que o serviço entrega é o miolo.
    """
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50
    base(_registro(radius=20))

    cidade = ip_location.approximate_city("200.150.100.50")

    assert cidade is not None
    assert cidade.label == "Londrina, PR · Brasil"
    assert cidade.radius_km == 20


def test_o_pais_sai_em_portugues(base, settings):
    """"Brasil", não "Brazil". A base publica `pt-BR` para país; usamos."""
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50
    base(_registro(radius=10))

    assert ip_location.approximate_city("200.150.100.50").country == "Brasil"


# ── A leitura ruim não vira rótulo nenhum ────────────────────────────────────


def test_acima_do_limiar_nao_mostra_nada(base, settings):
    """O caso do celular: IP da saída da operadora, raio grande, nome provavelmente errado.

    ⚠️ A resposta certa é `None` — NÃO é mostrar a cidade com uma ressalva ao lado. Rótulo
    com asterisco é o defeito "nota de rodapé do engenheiro": empurra para o leitor uma
    decisão que o servidor já tinha como tomar.
    """
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50
    base(_registro(radius=500))

    assert ip_location.approximate_city("200.150.100.50") is None


def test_o_limiar_e_inclusivo_na_borda(base, settings):
    """Raio IGUAL ao limiar passa; um a mais não passa. A borda é escrita, não deduzida."""
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50

    base(_registro(radius=50))
    assert ip_location.approximate_city("200.150.100.50") is not None

    ip_location.reset_reader_cache()
    base(_registro(radius=51))
    assert ip_location.approximate_city("200.150.100.50") is None


def test_sem_raio_nao_mostra_nada(base, settings):
    """Base sem raio de precisão não autoriza rótulo.

    Foi exatamente isto que reprovou a DB-IP Lite: medida em 3.000.000 de registros, ela
    traz só latitude e longitude. Sem raio não há como saber se a leitura serve, e a
    decisão do dono é mostrar só o que é confiável — então a ausência do campo silencia.
    """
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50
    base(_registro(radius=None))

    assert ip_location.approximate_city("200.150.100.50") is None


@pytest.mark.parametrize(
    "faltando",
    ["city", "uf", "country"],
    ids=["sem cidade", "sem sigla do estado", "sem país"],
)
def test_frase_incompleta_nao_vai_para_a_tela(base, settings, faltando):
    """Meia frase é pior que frase nenhuma.

    "Próximo a Londrina · Brasil" (sem a sigla) e "Próximo a , PR · Brasil" (sem a cidade)
    são defeito visível na tela do cliente. A regra é a mesma para as três peças.
    """
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50
    base(_registro(**{faltando: None}))

    assert ip_location.approximate_city("200.150.100.50") is None


def test_base_ausente_nao_derruba_a_tela(settings):
    """Sem base instalada — o caso de desenvolvimento, da CI e da imagem sem chave.

    A tela degrada para "navegador e data", que é o estado que a PR #991 deixou. O que não
    pode é levantar: a tela de segurança responde muito mais coisa que a cidade.
    """
    settings.GEOIP_CITY_DATABASE_PATH = ""
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50

    assert ip_location.approximate_city("200.150.100.50") is None


# ── IP que não tem cidade nem é perguntado ───────────────────────────────────


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.7",
        # ⚠️ Estas duas faixas o código ANTIGO deixava passar: ele testava `startswith("10.")`
        # e `startswith("127.")` e mais nada, então todo cliente atrás de um proxy em
        # 172.16/12 ou 192.168/16 virava consulta.
        "172.16.31.9",
        "192.168.0.10",
        "169.254.1.1",
        "",
        "nem-ip-e",
        "200.150.100.999",
    ],
)
def test_ip_sem_cidade_nao_consulta_a_base(base, settings, ip):
    """Rede interna, laço local e texto que não é IP: `None`, e SEM tocar na base.

    A asserção que importa é a segunda. Devolver `None` depois de consultar também
    passaria no olho, e deixaria de pé um acesso a disco por dispositivo para nada.
    """
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50
    falsa = base(_registro(radius=10))

    assert ip_location.approximate_city(ip) is None
    assert falsa.consultas == []
    assert falsa.aberturas == [], "saiu do caminho rápido e chegou a ABRIR a base"


# ── A base abre uma vez, não uma por dispositivo ────────────────────────────────


def test_a_base_abre_uma_vez_para_muitos_dispositivos(settings, monkeypatch, tmp_path):
    """Oito dispositivos, uma abertura.

    O defeito original custava até 2 s POR dispositivo. Trocar a chamada de rede por um
    `open()` por dispositivo seria o mesmo erro em outra moeda — e passaria despercebido,
    porque ler arquivo é rápido o bastante para ninguém reclamar até a lista crescer.
    """
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50

    aberturas = []
    falso = _BaseFalsa(_registro(radius=10))

    def _abrir(path, mode):
        aberturas.append(path)
        return falso

    import maxminddb

    monkeypatch.setattr(maxminddb, "open_database", _abrir)
    settings.GEOIP_CITY_DATABASE_PATH = str(tmp_path / "GeoLite2-City.mmdb")

    for octeto in range(1, 9):
        assert ip_location.approximate_city(f"200.150.100.{octeto}") is not None

    assert len(aberturas) == 1, f"a base abriu {len(aberturas)} vezes para 8 dispositivos"
    assert len(falso.consultas) == 8, "cada dispositivo precisa da própria consulta"


# ── O leitor de verdade, e não o falso ───────────────────────────────────────


@pytest.mark.parametrize(
    "caminho, motivo",
    [
        ("", "caminho vazio é o default de quem nunca configurou a base"),
        ("/caminho/que/nao/existe/GeoLite2-City.mmdb", "imagem sem a base baixada"),
        ("<dir>", "alguém apontou a setting para um diretório"),
        ("<lixo>", "download truncado ou arquivo corrompido no build"),
    ],
)
def test_a_base_de_verdade_falha_fechada(settings, tmp_path, caminho, motivo):
    """Exercita o `maxminddb` REAL — é aqui que a promessa de falhar fechado se prova.

    Os testes acima trocam o leitor por um falso, o que é certo para a regra de exibição e
    errado para esta pergunta: quais exceções o leitor de verdade levanta, e o `except`
    pega todas? Arquivo corrompido é o caso que um `except FileNotFoundError` sozinho
    deixaria passar — e ele derrubaria a tela inteira, não só a linha da cidade.
    """
    if caminho == "<dir>":
        caminho = str(tmp_path)
    elif caminho == "<lixo>":
        arquivo = tmp_path / "GeoLite2-City.mmdb"
        arquivo.write_bytes(b"isto nao e um mmdb" * 100)
        caminho = str(arquivo)

    settings.GEOIP_CITY_DATABASE_PATH = caminho
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50

    assert ip_location.approximate_city("200.150.100.50") is None, motivo


def test_a_cidade_nunca_vira_coluna_no_banco():
    """A localização derivada é CALCULADA na hora de exibir, e não gravada. Requisito.

    O IP já é guardado em `TrustedDevice.ip_address`, e isso tem justificativa própria
    (evidência de acesso). Gravar também a cidade derivada criaria um dado pessoal NOVO —
    com prazo de retenção, com direito de exportação, com mais uma linha na política — em
    troca de uma leitura de arquivo mapeado em memória, que é barata.

    ⚠️ Este teste existe porque o atalho é tentador e silencioso: um `city = models.CharField`
    no model "para não recalcular" passaria em code review como otimização inocente.
    """
    from shopman.doorman.models import TrustedDevice

    nomes = {campo.name.lower() for campo in TrustedDevice._meta.get_fields()}
    proibidos = {"city", "cidade", "location", "localizacao", "region", "geo", "latitude", "longitude"}

    colisao = nomes & proibidos
    assert not colisao, (
        f"TrustedDevice ganhou campo de localização: {sorted(colisao)}.\n"
        "A cidade da tela de segurança é derivada na exibição e não se grava — ver o "
        "docstring de `shopman/shop/services/devices.py::list_devices`."
    )


def test_o_modulo_nao_importa_cliente_http():
    """A garantia é de CÓDIGO AUSENTE, não de disciplina.

    A dependência escolhida é o `maxminddb` (leitor puro do formato) e não o `geoip2`, que
    embute o cliente do web service da MaxMind. Um cliente HTTP que existe é um cliente
    HTTP que alguém chama — inclusive sem querer, copiando um exemplo da documentação.
    """
    import shopman.shop.services.ip_location as modulo

    fonte = __import__("pathlib").Path(modulo.__file__).read_text(encoding="utf-8")
    codigo = "\n".join(
        linha for linha in fonte.splitlines()
        if not linha.strip().startswith("#")
    )
    # O docstring do módulo fala de `geoip2` e de `requests` para explicar por que NÃO são
    # usados; o que não pode é import.
    for proibido in ("import requests", "import urllib", "import http", "import socket", "import geoip2"):
        assert proibido not in codigo, f"o módulo passou a importar {proibido!r}"

    with pytest.raises(ImportError):
        __import__("geoip2")


# ── A base envelhece, e envelhecer calado era o buraco ───────────────────────
#
# Estes prendem a quarta promessa, que é a mais escorregadia das quatro: as três de cima
# falham ALTO (não abre, levanta, descarta). Esta falha BAIXO — a base velha abre, lê e
# responde errado com raio bom e a confiança de sempre. Se estes testes caírem, o defeito
# que volta não aparece em log nenhum.


def _limiares(settings, *, avisar=21, esconder=90):
    settings.GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50
    settings.GEOIP_CITY_STALE_ALERT_DAYS = avisar
    settings.GEOIP_CITY_MAX_AGE_DAYS = esconder


def test_base_dentro_do_prazo_mostra_a_cidade(base, settings):
    """O caso de controle: sem ele, um teste de envelhecimento que passa não prova nada."""
    _limiares(settings)
    base(_registro(radius=20), idade_dias=3)

    lida = ip_location.approximate_city("200.150.100.50")

    assert lida is not None and lida.label == "Londrina, PR · Brasil"


def test_base_velha_demais_nao_mostra_cidade(base, settings):
    """Passado o limiar largo, a cidade some — mesmo com a leitura perfeita.

    ⚠️ O registro aqui é BOM: raio de 20 km, cidade, sigla e país todos presentes. É esse
    o ponto — nenhum filtro existente reprovaria esta leitura. A única coisa errada com
    ela é a idade da base, e antes desta trava isso não era "errado" em lugar nenhum.
    """
    _limiares(settings)
    base(_registro(radius=20), idade_dias=91)

    assert ip_location.approximate_city("200.150.100.50") is None


def test_a_borda_do_limiar_de_exibicao_e_inclusiva(base, settings):
    """Exatamente no limiar já esconde; um dia antes ainda mostra.

    A borda é escrita porque `>` e `>=` são a mesma linha para quem lê rápido, e a
    diferença entre elas é um dia inteiro de cidade possivelmente errada na tela.
    """
    _limiares(settings, esconder=90)

    base(_registro(radius=20), idade_dias=89)
    assert ip_location.approximate_city("200.150.100.50") is not None

    base(_registro(radius=20), idade_dias=90)
    assert ip_location.approximate_city("200.150.100.50") is None


def test_data_ilegivel_conta_como_velha(base, settings):
    """Base presente sem data legível não vira "provavelmente nova". Vira velha.

    É a mesma regra do raio ausente: mostrar uma cidade cuja confiabilidade não se pôde
    conferir É um palpite, e este módulo não dá palpite.
    """
    _limiares(settings)
    base(_registro(radius=20), sem_data=True)

    assert ip_location.approximate_city("200.150.100.50") is None

    frescor = ip_location.database_freshness()
    assert frescor.present is True
    assert frescor.age_days is None
    assert frescor.too_old_to_show is True


def test_a_faixa_do_aviso_ainda_mostra_a_cidade(base, settings):
    """Entre os dois limiares: o operador é avisado e a tela CONTINUA mostrando.

    As duas faixas existem para não ter só um botão. Se o aviso já apagasse a linha, a
    cidade morreria aos 21 dias na prática — porque o bump é manual — e o rótulo viraria
    enfeite permanentemente mudo.
    """
    _limiares(settings)
    base(_registro(radius=20), idade_dias=30)

    assert ip_location.approximate_city("200.150.100.50") is not None

    frescor = ip_location.database_freshness()
    assert frescor.stale is True
    assert frescor.too_old_to_show is False
    assert frescor.age_days == 30


def test_base_ausente_nao_e_base_velha(settings, tmp_path):
    """Sem base não há idade, não há o que bumpar, e não há alerta a dar.

    Ausência é o estado previsto em dev, na CI e em imagem construída sem chave da
    MaxMind. Marcar isso como `stale` mandaria o operador atrás de um problema que não
    existe todo dia, até ele aprender a ignorar o tipo de alerta inteiro.
    """
    _limiares(settings)
    settings.GEOIP_CITY_DATABASE_PATH = str(tmp_path / "nao-existe.mmdb")

    frescor = ip_location.database_freshness()

    assert frescor.present is False
    assert frescor.stale is False
    assert frescor.too_old_to_show is False
    assert frescor.age_days is None


def test_limiar_zerado_desliga_a_trava(base, settings):
    """Zero desliga, como o raio faz — é assim que a casa solta um guardrail pela env."""
    _limiares(settings, avisar=0, esconder=0)
    base(_registro(radius=20), idade_dias=4000)

    assert ip_location.approximate_city("200.150.100.50") is not None
    frescor = ip_location.database_freshness()
    assert frescor.stale is False and frescor.too_old_to_show is False


def test_a_data_sai_da_base_de_VERDADE(settings, tmp_path):
    """Exercita o `maxminddb` REAL: a data que o arquivo carrega é a data que lemos.

    ⚠️ Os testes acima trocam o leitor por um falso, o que é certo para a regra de idade e
    errado para esta pergunta: `metadata().build_epoch` continua existindo e continua
    sendo segundos desde 1970? Toda a trava de envelhecimento pendura nessa única chamada.
    Se uma versão nova do `maxminddb` mudar a API, o que falha em produção é a proteção
    inteira — em silêncio, que é exatamente o modo de falhar que esta frente veio matar.

    O arquivo abaixo é um `.mmdb` mínimo mas VÁLIDO, montado byte a byte (árvore vazia,
    separador de 16 bytes, marcador e o mapa de metadados). Ele não responde consulta
    nenhuma — e não precisa: a pergunta aqui é só a data.
    """
    _limiares(settings)
    construida = datetime.datetime(2026, 2, 4, tzinfo=datetime.UTC)
    arquivo = tmp_path / "GeoLite2-City.mmdb"
    arquivo.write_bytes(mmdb_minimo(int(construida.timestamp())))
    settings.GEOIP_CITY_DATABASE_PATH = str(arquivo)

    frescor = ip_location.database_freshness()

    assert frescor.present is True
    assert frescor.built_at == construida
    esperado = (datetime.datetime.now(datetime.UTC) - construida).days
    assert frescor.age_days == esperado
