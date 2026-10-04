"""密码哈希行为测试：Argon2id 新哈希与 bcrypt 存量兼容。"""

import bcrypt

from app.core.security import hash_password, verify_password, verify_password_and_update


def test_password_hash_uses_argon2id() -> None:
    hashed = hash_password("correct-password")

    assert hashed.startswith("$argon2id$")
    assert verify_password("correct-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_legacy_bcrypt_verifies_and_upgrades() -> None:
    legacy = bcrypt.hashpw(
        b"legacy-password",
        bcrypt.gensalt(rounds=12, prefix=b"2b"),
    ).decode()

    ok, upgraded = verify_password_and_update("legacy-password", legacy)

    assert ok is True
    assert upgraded is not None
    assert upgraded.startswith("$argon2id$")
    assert verify_password("legacy-password", upgraded) is True


def test_legacy_bcrypt_wrong_password_does_not_upgrade() -> None:
    legacy = bcrypt.hashpw(
        b"legacy-password",
        bcrypt.gensalt(rounds=12, prefix=b"2b"),
    ).decode()

    assert verify_password_and_update("wrong-password", legacy) == (False, None)


def test_unknown_hash_is_rejected() -> None:
    assert verify_password("password", "not-a-password-hash") is False
    assert verify_password_and_update("password", "not-a-password-hash") == (False, None)
