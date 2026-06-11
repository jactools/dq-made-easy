from pydantic import BaseModel
import pytest

from app.infrastructure.security import EncryptionConfigurationError
from app.infrastructure.security import EntityFieldEncryptor


TEST_ENCRYPTION_KEY = "i0aU2BE0dzqEVAWxfEsvffw5zw93FjFZrr24RPVyo8c="


class SampleEntity(BaseModel):
    name: str
    enabled: bool
    secret: str
    metadata: dict[str, object]


@pytest.fixture
def encryptor() -> EntityFieldEncryptor:
    return EntityFieldEncryptor.from_key(TEST_ENCRYPTION_KEY)


def test_encrypt_and_decrypt_selected_attributes(encryptor: EntityFieldEncryptor) -> None:
    payload = {
        "name": "dq-made-easy",
        "enabled": True,
        "secret": "super-secret",
        "metadata": {"version": 1},
    }

    encrypted = encryptor.encrypt_attributes(payload, ["secret"])

    assert encrypted["name"] == "dq-made-easy"
    assert encrypted["enabled"] is True
    assert encrypted["metadata"] == {"version": 1}
    assert encrypted["secret"].startswith("enc:v1:")

    decrypted = encryptor.decrypt_attributes(encrypted, ["secret"])

    assert decrypted == payload


def test_encrypt_and_decrypt_entire_entity(encryptor: EntityFieldEncryptor) -> None:
    entity = SampleEntity(
        name="dq-made-easy",
        enabled=True,
        secret="super-secret",
        metadata={"attributes": ["a", "b"], "count": 2},
    )

    encrypted = encryptor.encrypt_entity(entity)

    assert encrypted["name"].startswith("enc:v1:")
    assert encrypted["secret"].startswith("enc:v1:")

    decrypted = encryptor.decrypt_entity(encrypted)

    assert decrypted["name"] == "dq-made-easy"
    assert decrypted["enabled"] is True
    assert decrypted["secret"] == "super-secret"
    assert decrypted["metadata"] == {"attributes": ["a", "b"], "count": 2}


def test_from_env_raises_when_encryption_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_CONFIG_ENCRYPTION_KEY", raising=False)

    with pytest.raises(EncryptionConfigurationError, match="APP_CONFIG_ENCRYPTION_KEY"):
        EntityFieldEncryptor.from_env()