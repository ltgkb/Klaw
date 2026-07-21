import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_development_secrets():
    with pytest.raises(ValidationError):
        Settings(environment="prod", jwt_secret_key="change-me-in-production-please-use-a-long-random-string")


def test_production_accepts_strong_secrets():
    settings = Settings(
        environment="prod",
        jwt_secret_key="a" * 64,
        encryption_key="b" * 64,
    )
    assert settings.environment == "prod"
