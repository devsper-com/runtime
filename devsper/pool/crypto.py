"""
E2EE for task payloads.

Encryption scheme:
  - Per-org X25519 key pair (private key stored in org keyring, public key registered with platform).
  - For each task: ephemeral X25519 keypair -> shared secret -> HKDF-SHA256 -> AES-256-GCM.
  - Wire format: ephemeral_pub (32B) || nonce (12B) || ciphertext+tag (len(pt)+16B)

The pool stores and forwards ciphertext only; it never decrypts.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def generate_org_keypair() -> tuple[bytes, bytes]:
    priv = X25519PrivateKey.generate()
    priv_b = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub_b = priv.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return priv_b, pub_b


def encrypt_payload(plaintext: bytes, org_public_key_bytes: bytes) -> bytes:
    eph_priv = X25519PrivateKey.generate()
    eph_pub = eph_priv.public_key()
    org_pub = X25519PublicKey.from_public_bytes(org_public_key_bytes)
    shared = eph_priv.exchange(org_pub)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"devsper-task-v1",
    ).derive(shared)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    eph_pub_b = eph_pub.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return eph_pub_b + nonce + ct


def decrypt_payload(ciphertext: bytes, org_private_key_bytes: bytes) -> bytes:
    if len(ciphertext) < 32 + 12 + 16:
        raise ValueError("ciphertext too short")
    eph_pub_b = ciphertext[:32]
    nonce = ciphertext[32:44]
    ct = ciphertext[44:]
    org_priv = X25519PrivateKey.from_private_bytes(org_private_key_bytes)
    eph_pub = X25519PublicKey.from_public_bytes(eph_pub_b)
    shared = org_priv.exchange(eph_pub)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"devsper-task-v1",
    ).derive(shared)
    return AESGCM(key).decrypt(nonce, ct, None)

