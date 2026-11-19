"""Os 40 testes de conformidade (v2, Apêndice A.2): invariantes, WP dono e escopo exigido.

Escopo (plano 3.10): ``core`` se prova com os falsos; ``adapter`` o adaptador
real precisa repetir; ``real_mechanism`` só vale rodado no mecanismo do
adaptador (no núcleo é simulação).
"""

from __future__ import annotations

from dataclasses import dataclass

SCOPES: tuple[str, ...] = ("core", "adapter", "real_mechanism")


@dataclass(frozen=True, slots=True)
class ConformanceTest:
    id: str
    title: str
    invariants: tuple[str, ...]
    owner: str
    scope: str


def _t(id_: str, title: str, invariants: str, owner: str, scope: str = "core") -> ConformanceTest:
    return ConformanceTest(id_, title, tuple(invariants.split()) if invariants else (), owner, scope)


K_TESTS: tuple[ConformanceTest, ...] = (
    _t("K01", "mesma entrada com identidade estável chega duas vezes", "N12", "F4", "adapter"),
    _t("K02", "duas mensagens iguais com identidades diferentes", "N12", "F4", "adapter"),
    _t("K03", "confirmação chega antes dos termos", "N06 N12", "F8", "adapter"),
    _t("K04", "fonte crítica falha ou está vencida", "N02", "F5"),
    _t("K05", "modelo devolve ação fora do catálogo", "N05", "F7"),
    _t("K06", "confirmação de outro cliente, inquilino ou ambiente", "N06 N11", "F8", "adapter"),
    _t("K07", "preço, destinatário ou item muda depois da confirmação", "N07", "F8", "adapter"),
    _t("K08", "mesma chave e conteúdo depois de resposta perdida", "N08 N09", "F8", "adapter"),
    _t("K09", "mesma chave com conteúdo diferente", "N08", "F8", "adapter"),
    _t("K10", "queda depois do efeito e antes do recibo local", "N09 N13", "F8", "adapter"),
    _t("K11", "revogação vence antes do ponto de efeito", "N07 N10", "F8", "real_mechanism"),
    _t("K12", "transferência depois da submissão externa", "N10", "F8", "real_mechanism"),
    _t("K13", "dois trabalhadores com a mesma versão do episódio", "N13", "F4", "real_mechanism"),
    _t("K14", "o trabalhador morre no meio da execução", "N09", "F8", "real_mechanism"),
    _t("K15", "a concessão vence entre a decisão e a execução", "N07", "F8", "adapter"),
    _t("K16", "chave expirada com efeito anterior desconhecido", "N09", "F8", "adapter"),
    _t("K17", "o canal devolve desconhecido ao enviar", "N16", "F7", "adapter"),
    _t("K18", "o canal confirma entrega e não suporta leitura", "N16", "F7", "adapter"),
    _t("K19", "reclamação e dúvida na mesma entrada", "N15 N19", "F9"),
    _t("K20", "a fila não aceita a transferência", "N04 N15", "F9", "adapter"),
    _t("K21", "o cliente encerra com compromisso aberto", "N15", "F9"),
    _t("K22", "promessa com prazo vence sem resposta da equipe", "N04", "F9", "adapter"),
    _t("K23", "redação traz preço ou estado sem fato", "N01 N03", "F6", "adapter"),
    _t("K24", "resposta afirma uma ação sem recibo", "N01", "F6", "adapter"),
    _t("K25", "instrução embutida na mensagem do cliente", "N23", "F7"),
    _t("K26", "instrução embutida em catálogo ou resposta da equipe", "N23", "F7"),
    _t("K27", "a política permite prometer sem estoque físico", "N02", "F6", "adapter"),
    _t("K28", "memória corrigida ou vencida", "", "F10"),
    _t("K29", "sim depois de a equipe devolver a conversa", "N06", "F4"),
    _t("K30", "duas leituras numa mudança e numa consulta", "", "F5"),
    _t("K31", "problema aberto ou atrito alto", "N19", "F5"),
    _t("K32", "decisão sorteada e guarda que bloqueia depois", "N14 N17", "F5"),
    _t("K33", "a janela do resultado não terminou", "N21", "F10", "adapter"),
    _t("K34", "modelo sem preço cadastrado", "N21", "F10"),
    _t("K35", "fonte externa corrige um resultado", "N14", "F10", "adapter"),
    _t("K36", "ambiente de sombra", "", "F7", "adapter"),
    _t("K37", "troca de canal ou de modelo falso", "N24", "F7"),
    _t("K38", "o núcleo roda sem Django, sem SDK, sem rede", "N26", "F0"),
    _t("K39", "requisito crítico ausente no perfil", "", "F2", "adapter"),
    _t("K40", "reexecução de turno gravado com a mesma semente", "", "F5"),
)

K_BY_ID: dict[str, ConformanceTest] = {test.id: test for test in K_TESTS}
INVARIANTS: tuple[str, ...] = tuple(f"N{number:02d}" for number in range(1, 27))
