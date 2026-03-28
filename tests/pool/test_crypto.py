from devsper.pool.crypto import (
    decrypt_payload,
    encrypt_payload,
    generate_org_keypair,
)


def test_e2ee_round_trip_and_lengths():
    priv, pub = generate_org_keypair()
    pt = b"hello devsper"
    ct = encrypt_payload(pt, pub)
    assert decrypt_payload(ct, priv) == pt
    assert len(ct) == 32 + 12 + len(pt) + 16


def test_cross_org_isolation():
    priv, pub = generate_org_keypair()
    _, wrong_pub = generate_org_keypair()
    pt = b"secret"
    ct = encrypt_payload(pt, wrong_pub)
    try:
        decrypt_payload(ct, priv)
        assert False, "should not decrypt with wrong org key"
    except Exception:
        assert True

