import pytest

from app.dash_app.pages.connectors.components.connector_card import connector_card
from app.dash_app.styles import COLOR_GRAY_LIGHT, COLOR_SUCCESS


@pytest.mark.unit
def test_connector_card_uses_green_dot_for_configured_status():
    component = connector_card(
        connector_type="github",
        display_name="GitHub",
        icon="fa-solid fa-github",
        status="configured",
    )

    status_row = component.children[1]
    status_dot = status_row.children[0]

    assert status_dot.style["backgroundColor"] == COLOR_SUCCESS
    assert status_dot.style["backgroundColor"] != COLOR_GRAY_LIGHT
