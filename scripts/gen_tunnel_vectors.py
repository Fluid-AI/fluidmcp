#!/usr/bin/env python3
"""
Generate tests/tunnel_test_vectors.json for the fmcp-tunnel/1 protocol.

The JSON is the reference both FluidMCP and GPT Engine test against. Regenerate it
only when the protocol changes, and ship the new file to GPT Engine with protocol.py.

Usage:
    PYTHONPATH=. python scripts/gen_tunnel_vectors.py
"""

import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from fluidmcp.cli.tunnel.protocol import ClientHandshake, ControlMessage, Env, ServerHandshake, public_key_to_b64

OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "tunnel_test_vectors.json"
WALL = 1760400000
CONNECTOR_ID = "site-a"


def _seed(label: str) -> bytes:
    return hashlib.sha256(label.encode("ascii")).digest()


class _RecordingRng:
    def __init__(self, label: str):
        self._label = label
        self.values = []

    def __call__(self, size: int) -> bytes:
        value = hashlib.sha256(f"{self._label} {len(self.values)}".encode("ascii")).digest()[:size]
        self.values.append(value.hex())
        return value


def build_vectors() -> dict:
    client_seeds = [_seed("tv client key 1"), _seed("tv client key 2")]
    server_seeds = [_seed("tv server key 1"), _seed("tv server key 2")]
    client_keys = [Ed25519PrivateKey.from_private_bytes(s) for s in client_seeds]
    server_keys = [Ed25519PrivateKey.from_private_bytes(s) for s in server_seeds]
    client_rng, server_rng = _RecordingRng("tv client rng"), _RecordingRng("tv server rng")
    client_env = Env(rng=client_rng, wall=lambda: WALL, mono=lambda: 0.0)
    server_env = Env(rng=server_rng, wall=lambda: WALL, mono=lambda: 0.0)

    # Second key on each side is the active one, so rotation sets are exercised.
    client_publics = [k.public_key().public_bytes_raw() for k in client_keys]
    server_publics = [k.public_key().public_bytes_raw() for k in server_keys]
    client = ClientHandshake(client_keys[1], server_publics, CONNECTOR_ID, client_env)
    server = ServerHandshake(server_keys[1], client_publics, CONNECTOR_ID, server_env)
    client_hello = client.start()
    server_hello = server.receive_client_hello(client_hello)
    client_finish, client_channel = client.receive_server_hello(server_hello)
    server_channel = server.receive_client_finish(client_finish)
    channels = {"client": client_channel, "server": server_channel}

    steps = []

    def encrypt(actor: str, plaintext: bytes) -> bytes:
        frame = channels[actor].encrypt(plaintext)
        steps.append({"actor": actor, "action": "encrypt", "plaintext": plaintext.hex(), "frame": frame.hex()})
        return frame

    def decrypt(actor: str, frame: bytes) -> object:
        result = channels[actor].decrypt(frame)
        step = {"actor": actor, "action": "decrypt", "frame": frame.hex()}
        if isinstance(result, ControlMessage):
            step["control"] = {"kind": result.kind, "key_no": result.key_no,
                               "reply": result.reply.hex() if result.reply else None}
        else:
            step["plaintext"] = result.hex()
        steps.append(step)
        return result

    def rekey() -> None:
        frame = client_channel.start_rekey()
        steps.append({"actor": "client", "action": "start_rekey", "frame": frame.hex()})
        in_flight = encrypt("client", b'{"type":"response","id":"in-flight"}')
        ack = decrypt("server", frame).reply
        decrypt("server", in_flight)
        after = encrypt("server", b'{"type":"request","id":"after-rekey"}')
        decrypt("client", ack)
        decrypt("client", after)
        decrypt("server", encrypt("client", b'{"type":"response","id":"after-rekey"}'))

    decrypt("server", encrypt("client", b'{"type":"hello","protocol":1,"connector":"site-a"}'))
    decrypt("client", encrypt("server", b'{"type":"request","id":"1"}'))
    decrypt("server", encrypt("client", b'{"type":"response","id":"1","status":200}'))
    decrypt("server", encrypt("client", b""))
    rekey()
    rekey()

    return {
        "protocol": "fmcp-tunnel/1",
        "connector_id": CONNECTOR_ID,
        "wall": WALL,
        "client_identity_seeds": [s.hex() for s in client_seeds],
        "server_identity_seeds": [s.hex() for s in server_seeds],
        "active_client_key": 1,
        "active_server_key": 1,
        "client_public_keys_b64": [public_key_to_b64(k) for k in client_keys],
        "server_public_keys_b64": [public_key_to_b64(k) for k in server_keys],
        "client_rng": client_rng.values,
        "server_rng": server_rng.values,
        "client_hello": client_hello.hex(),
        "server_hello": server_hello.hex(),
        "client_finish": client_finish.hex(),
        "transcript_hash": client_channel.transcript_hash.hex(),
        "steps": steps,
    }


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build_vectors(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
