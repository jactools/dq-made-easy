from __future__ import annotations

from app.api.presenters.auth import build_oidc_state_entity
from app.api.presenters.auth import build_oidc_token_response_entity


def test_build_oidc_state_and_token_entities_use_canonical_keys() -> None:
    state_entity = build_oidc_state_entity(
        {"nonce": "456-xyz", "issuedAt": 456, "frontendOrigin": "https://frontend.example/path"}
    )
    assert state_entity is not None
    assert state_entity.issuedAt == 456
    assert state_entity.frontendOrigin == "https://frontend.example"

    token_entity = build_oidc_token_response_entity(
        {"access_token": "access-1", "id_token": "id-1", "refresh_token": "refresh-1"}
    )
    assert token_entity is not None
    assert token_entity.access_token == "access-1"
    assert token_entity.id_token == "id-1"
    assert token_entity.refresh_token == "refresh-1"
