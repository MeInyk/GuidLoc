"""Static contract tests for location-change agent instructions."""

from guidloc.agents.location_change_tools import propose_location_change
from guidloc.agents.openai_agent import ORCHESTRATOR_INSTRUCTIONS


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def test_orchestrator_disallows_unsupported_location_change_fields() -> None:
    instructions = _normalise(ORCHESTRATOR_INSTRUCTIONS)

    assert "unsupported fields include photos/images" in instructions
    assert "do not ask for these fields" in instructions
    assert "can currently save only the supported text/structured location fields" in instructions
    for unsupported in ("menu", "opening hours", "phone", "website", "social media"):
        assert unsupported in instructions


def test_orchestrator_follow_up_uses_only_supported_optional_fields() -> None:
    instructions = _normalise(ORCHESTRATOR_INSTRUCTIONS)

    assert "supported location-change fields are only" in instructions
    assert "ask only for supported optional fields: description, price_level, tags" in instructions
    supported_fields = (
        "name",
        "description",
        "address",
        "latitude",
        "longitude",
        "category",
        "price_level",
        "tags",
        "is_active",
    )
    for field in supported_fields:
        assert field in instructions


def test_propose_location_change_tool_rejects_photo_like_fields_in_description() -> None:
    description = _normalise(propose_location_change.description)

    assert "supported fields are only" in description
    assert "does not accept photos" in description
    assert "images" in description
    supported_optional_phrase = "optional: description, price_level, tags, is_active"
    assert supported_optional_phrase in description


def test_orchestrator_knows_how_to_amend_view_and_cancel_user_requests() -> None:
    instructions = _normalise(ORCHESTRATOR_INSTRUCTIONS)

    assert "a request id is not a location id" in instructions
    assert "amend_location_change_request" in instructions
    assert "read_my_location_change_requests" in instructions
    assert "cancel_location_change_request" in instructions
    assert "do not create a new update request for a real location" in instructions
    assert "summarise only their requests" in instructions
    assert "cancel/delete/withdraw a submitted request" in instructions
