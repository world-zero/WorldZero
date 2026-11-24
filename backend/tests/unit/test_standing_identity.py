import logging
from types import SimpleNamespace

from services.standing import public_identity


def test_an_unloaded_name_state_logs_a_warning(caplog):
    character = SimpleNamespace(
        id=7, display_name="Zork", username="zork", avatar_url="a"
    )
    with caplog.at_level(logging.WARNING):
        identity = public_identity(character)
    assert "name_state not loaded for character 7" in caplog.text
    assert identity.display_name == "Zork"
