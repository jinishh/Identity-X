"""Cryptographic primitives. Each one solves a different problem (docs/03-integrity-model.md):

- AES-256-GCM envelope encryption  → confidentiality + ciphertext tamper detection
- SHA-256                          → "are these the same bytes?"
- Ed25519 over JCS (RFC 8785)       → "the platform recorded exactly this"
- Merkle root                      → one hash that seals a range of audit events

Prototype key handling: keys are files under data/keys. Production: Vault Transit / HSM.
"""

import base64
import hashlib
import os
from functools import lru_cache

import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config

KEK_ID = "kek-2026-01"
SIGNING_KEY_IDS = {
    "MANIFEST": "sys-manifest-2026-01",
    "CHECKPOINT": "sys-checkpoint-2026-01",
    "CERTIFICATE": "sys-certificate-2026-01",
}


# ───────────── hashing / canonical JSON ─────────────

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jcs(obj) -> bytes:
    """RFC 8785 canonical JSON — identical bytes in any implementation."""
    return rfc8785.dumps(obj)


def merkle_root(leaves_hex: list[str]) -> str:
    if not leaves_hex:
        return "0" * 64
    level = [bytes.fromhex(h) for h in leaves_hex]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ───────────── key material ─────────────

@lru_cache
def _kek() -> bytes:
    path = config.KEYS_DIR / f"{KEK_ID}.key"
    if not path.exists():
        path.write_bytes(os.urandom(32))
        path.chmod(0o400)
    return path.read_bytes()


@lru_cache
def _signing_key(purpose: str) -> Ed25519PrivateKey:
    kid = SIGNING_KEY_IDS[purpose]
    path = config.KEYS_DIR / f"{kid}.pem"
    if not path.exists():
        key = Ed25519PrivateKey.generate()
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        path.chmod(0o400)
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def public_key_bytes(purpose: str) -> bytes:
    return _signing_key(purpose).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def reset_key_cache() -> None:
    _kek.cache_clear()
    _signing_key.cache_clear()


# ───────────── small secrets (TOTP seeds) sealed under the KEK ─────────────

def seal(plaintext: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_kek()).encrypt(nonce, plaintext, b"cfv-seal")


def unseal(blob: bytes) -> bytes:
    return AESGCM(_kek()).decrypt(blob[:12], blob[12:], b"cfv-seal")


# ───────────── envelope encryption for files ─────────────

def encrypt_file(plaintext: bytes, aad: bytes) -> tuple[bytes, bytes, bytes]:
    """Returns (ciphertext, nonce, wrapped_dek). A fresh DEK per file; AAD binds the
    ciphertext to its database record so stored objects cannot be swapped."""
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
    wrap_nonce = os.urandom(12)
    wrapped = wrap_nonce + AESGCM(_kek()).encrypt(wrap_nonce, dek, KEK_ID.encode())
    return ciphertext, nonce, wrapped


def decrypt_file(ciphertext: bytes, nonce: bytes, wrapped_dek: bytes, aad: bytes) -> bytes:
    dek = AESGCM(_kek()).decrypt(wrapped_dek[:12], wrapped_dek[12:], KEK_ID.encode())
    return AESGCM(dek).decrypt(nonce, ciphertext, aad)


# ───────────── signatures ─────────────

def sign(purpose: str, obj) -> tuple[bytes, str]:
    """Sign the canonical form of obj. Returns (signature, kid)."""
    return _signing_key(purpose).sign(jcs(obj)), SIGNING_KEY_IDS[purpose]


def verify(purpose: str, obj, signature: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes(purpose)).verify(signature, jcs(obj))
        return True
    except Exception:
        return False
