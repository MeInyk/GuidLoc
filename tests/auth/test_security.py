from guidloc.auth.security import hash_password, verify_password


def test_hash_password_returns_non_plaintext() -> None:
    plain = "stest-jwt-secret-key-that-is-at-least-32-bytes"
    hashed = hash_password(plain)

    assert hashed != plain
    assert hashed.startswith("$2")  # bcrypt prefix
    assert len(hashed) > 40


def test_verify_password_accepts_correct_password() -> None:
    plain = "correct horse battery staple"
    hashed = hash_password(plain)

    assert verify_password(plain, hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct-password")

    assert verify_password("wrong-password", hashed) is False


def test_hash_password_produces_unique_hashes_for_same_input() -> None:
    plain = "same-password"

    assert hash_password(plain) != hash_password(plain)
