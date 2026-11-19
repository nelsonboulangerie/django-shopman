"""Cada falso declara ``capabilities()`` e passa no arnês de forma da própria porta."""

from __future__ import annotations

import pytest

from conversational_commerce.ports import PORT_NAMES, PORTS
from conversational_commerce.testing.conformance.harness import CHECKS, run_checks


def test_eight_ports_each_with_a_check():
    assert set(PORTS) == set(PORT_NAMES) == set(CHECKS)
    assert len(PORT_NAMES) == 8


@pytest.mark.parametrize("name", PORT_NAMES)
def test_fake_passes_the_shape_of_its_port(name, world, env):
    assert run_checks(name, world.ports()[name], env) == []


@pytest.mark.parametrize("name", PORT_NAMES)
def test_capabilities_are_declared_values(name, world):
    capabilities = world.ports()[name].capabilities()
    assert capabilities.port == name
    assert all(capabilities.supports(op) or op in capabilities.unsupported for op in capabilities.operations)


class _Broken:
    """Uma porta que não é porta: o arnês tem de reprovar."""

    def capabilities(self):
        return None


@pytest.mark.parametrize("name", PORT_NAMES)
def test_harness_fails_a_broken_port(name, env):
    failures = run_checks(name, _Broken(), env)
    assert failures, "o arnês aprovou uma porta quebrada"
    assert failures[0].check == "capabilities"
