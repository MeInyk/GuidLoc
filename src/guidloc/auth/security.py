"""Password hashing utilities backed by bcrypt via passlib."""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Return a secure bcrypt hash of the given plaintext password."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a previously stored hash."""
    return _pwd_context.verify(plain_password, password_hash)
