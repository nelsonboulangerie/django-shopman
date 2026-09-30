"""O dispositivo que age, declarado pela requisição e lido pelo escritor único."""

from shopman.utils import acting_device
from shopman.utils.acting_device import DEVICE_KEY


def test_fora_de_requisicao_nenhum_dispositivo_agiu():
    assert acting_device.current_device_id() == ""
    assert acting_device.stamp({"a": 1}) == {"a": 1}


def test_dentro_do_bloco_o_escritor_carimba_o_dispositivo():
    with acting_device.acting_device(lambda: "dev-1"):
        assert acting_device.stamp({"a": 1}) == {"a": 1, DEVICE_KEY: "dev-1"}
    assert acting_device.current_device_id() == ""


def test_o_chamador_nao_escolhe_o_dispositivo():
    with acting_device.acting_device(lambda: "dev-1"):
        assert acting_device.stamp({DEVICE_KEY: "forjado"}) == {DEVICE_KEY: "dev-1"}
    assert acting_device.stamp({DEVICE_KEY: "forjado"}) == {}


def test_o_resolvedor_roda_uma_vez_e_so_se_alguem_gravar():
    chamadas = []

    def resolver():
        chamadas.append(1)
        return "dev-1"

    with acting_device.acting_device(resolver):
        assert chamadas == []
        acting_device.stamp({})
        acting_device.stamp({})
    assert chamadas == [1]


def test_stamp_nao_altera_o_dict_de_quem_chamou():
    original = {"a": 1}
    with acting_device.acting_device(lambda: "dev-1"):
        acting_device.stamp(original)
    assert original == {"a": 1}
