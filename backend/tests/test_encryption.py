"""Fernet roundtrip + tampering detection."""
from app.utils.encryption import decrypt, encrypt


def test_encrypt_then_decrypt_roundtrip():
    plain = "hunter2-secret-with-special-chars-!@#$%"
    cipher = encrypt(plain)
    assert cipher is not None
    assert plain not in cipher          # not stored as plaintext
    assert cipher.startswith("gAAAAA")   # Fernet token prefix
    assert decrypt(cipher) == plain


def test_encrypt_handles_none_and_empty():
    assert encrypt(None) is None
    assert encrypt("") is None
    assert decrypt(None) is None
    assert decrypt("") is None


def test_decrypt_tampered_returns_none():
    plain = "before"
    cipher = encrypt(plain)
    assert cipher is not None
    # Flip a single character — Fernet HMAC should reject it.
    tampered = cipher[:-2] + ("AB" if cipher[-2:] != "AB" else "CD")
    assert decrypt(tampered) is None
