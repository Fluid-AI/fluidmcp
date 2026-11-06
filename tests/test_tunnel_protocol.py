"""Tests for the fmcp-tunnel/1 protocol (fluidmcp/cli/tunnel/protocol.py)."""

import json
import os
import struct
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from fluidmcp.cli.tunnel import protocol
from fluidmcp.cli.tunnel.protocol import (
    ClientHandshake,
    ControlMessage,
    Env,
    ProtocolError,
    ServerHandshake,
    generate_identity_key,
    load_private_key_file,
    parse_public_key_list,
    private_key_from_b64,
    private_key_to_b64,
    public_key_from_b64,
    public_key_to_b64,
)

VECTORS = json.loads((Path(__file__).parent / "tunnel_test_vectors.json").read_text(encoding="utf-8"))
WALL = 1760400000
CONNECTOR = "site-a"


class Clock:
    def __init__(self, wall: float = WALL):
        self.wall = wall
        self.mono = 1000.0


def make_env(clock: Clock) -> Env:
    return Env(rng=os.urandom, wall=lambda: clock.wall, mono=lambda: clock.mono)


def raw_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes_raw()


def queue_rng(values):
    queue = [bytes.fromhex(v) for v in values]

    def rng(size: int) -> bytes:
        value = queue.pop(0)
        assert len(value) == size
        return value

    rng.remaining = queue
    return rng


@pytest.fixture
def keys():
    return generate_identity_key(), generate_identity_key()


def connect(client_key, server_key, client_clock=None, server_clock=None, connector_id=CONNECTOR):
    client_clock = client_clock or Clock()
    server_clock = server_clock or Clock()
    client = ClientHandshake(client_key, [raw_public(server_key)], connector_id, make_env(client_clock))
    server = ServerHandshake(server_key, [raw_public(client_key)], connector_id, make_env(server_clock))
    server_hello = server.receive_client_hello(client.start())
    client_finish, client_channel = client.receive_server_hello(server_hello)
    server_channel = server.receive_client_finish(client_finish)
    return client_channel, server_channel


def assert_error(code, func, *args):
    with pytest.raises(ProtocolError) as exc:
        func(*args)
    assert exc.value.code == code


class TestVectors:
    """The committed vectors must reproduce byte for byte (shared with GPT Engine)."""

    def _handshake(self):
        client_keys = [Ed25519PrivateKey.from_private_bytes(bytes.fromhex(s)) for s in VECTORS["client_identity_seeds"]]
        server_keys = [Ed25519PrivateKey.from_private_bytes(bytes.fromhex(s)) for s in VECTORS["server_identity_seeds"]]
        client_rng, server_rng = queue_rng(VECTORS["client_rng"]), queue_rng(VECTORS["server_rng"])
        wall = VECTORS["wall"]
        client = ClientHandshake(
            client_keys[VECTORS["active_client_key"]],
            [raw_public(k) for k in server_keys],
            VECTORS["connector_id"],
            Env(rng=client_rng, wall=lambda: wall, mono=lambda: 0.0),
        )
        server = ServerHandshake(
            server_keys[VECTORS["active_server_key"]],
            [raw_public(k) for k in client_keys],
            VECTORS["connector_id"],
            Env(rng=server_rng, wall=lambda: wall, mono=lambda: 0.0),
        )
        return client, server, client_rng, server_rng

    def test_public_keys_match(self):
        seeds = VECTORS["client_identity_seeds"] + VECTORS["server_identity_seeds"]
        expected = VECTORS["client_public_keys_b64"] + VECTORS["server_public_keys_b64"]
        for seed, b64 in zip(seeds, expected):
            assert public_key_to_b64(Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed))) == b64

    def test_handshake_and_steps_match(self):
        client, server, client_rng, server_rng = self._handshake()
        client_hello = client.start()
        assert client_hello.hex() == VECTORS["client_hello"]
        server_hello = server.receive_client_hello(client_hello)
        assert server_hello.hex() == VECTORS["server_hello"]
        client_finish, client_channel = client.receive_server_hello(server_hello)
        assert client_finish.hex() == VECTORS["client_finish"]
        server_channel = server.receive_client_finish(client_finish)
        assert client_channel.transcript_hash.hex() == VECTORS["transcript_hash"]
        assert server_channel.transcript_hash.hex() == VECTORS["transcript_hash"]

        channels = {"client": client_channel, "server": server_channel}
        for step in VECTORS["steps"]:
            channel = channels[step["actor"]]
            if step["action"] == "encrypt":
                assert channel.encrypt(bytes.fromhex(step["plaintext"])).hex() == step["frame"]
            elif step["action"] == "start_rekey":
                assert channel.start_rekey().hex() == step["frame"]
            else:
                result = channel.decrypt(bytes.fromhex(step["frame"]))
                if "control" in step:
                    assert isinstance(result, ControlMessage)
                    assert result.kind == step["control"]["kind"]
                    assert result.key_no == step["control"]["key_no"]
                    reply = result.reply.hex() if result.reply else None
                    assert reply == step["control"]["reply"]
                else:
                    assert result.hex() == step["plaintext"]
        assert client_rng.remaining == [] and server_rng.remaining == []


class TestHandshake:
    def test_round_trip(self, keys):
        client_channel, server_channel = connect(*keys)
        assert server_channel.decrypt(client_channel.encrypt(b"ping")) == b"ping"
        assert client_channel.decrypt(server_channel.encrypt(b"pong")) == b"pong"

    def test_unknown_client_key_rejected(self, keys):
        client_key, server_key = keys
        client = ClientHandshake(client_key, [raw_public(server_key)], CONNECTOR)
        server = ServerHandshake(server_key, [raw_public(generate_identity_key())], CONNECTOR)
        assert_error("unknown_client_key", server.receive_client_hello, client.start())

    def test_impostor_server_rejected(self, keys):
        client_key, server_key = keys
        impostor = generate_identity_key()
        client = ClientHandshake(client_key, [raw_public(server_key)], CONNECTOR)
        server = ServerHandshake(impostor, [raw_public(client_key)], CONNECTOR)
        assert_error("unknown_server_key", client.receive_server_hello, server.receive_client_hello(client.start()))

    def test_tampered_server_hello_rejected(self, keys):
        client_key, server_key = keys
        client = ClientHandshake(client_key, [raw_public(server_key)], CONNECTOR)
        server = ServerHandshake(server_key, [raw_public(client_key)], CONNECTOR)
        server_hello = bytearray(server.receive_client_hello(client.start()))
        server_hello[20] ^= 1
        assert_error("bad_signature", client.receive_server_hello, bytes(server_hello))

    def test_tampered_client_finish_rejected(self, keys):
        client_key, server_key = keys
        client = ClientHandshake(client_key, [raw_public(server_key)], CONNECTOR)
        server = ServerHandshake(server_key, [raw_public(client_key)], CONNECTOR)
        client_finish, _ = client.receive_server_hello(server.receive_client_hello(client.start()))
        tampered = bytearray(client_finish)
        tampered[10] ^= 1
        assert_error("bad_signature", server.receive_client_finish, bytes(tampered))

    def test_replayed_client_finish_rejected(self, keys):
        client_key, server_key = keys
        client = ClientHandshake(client_key, [raw_public(server_key)], CONNECTOR)
        client_hello = client.start()
        server = ServerHandshake(server_key, [raw_public(client_key)], CONNECTOR)
        client_finish, _ = client.receive_server_hello(server.receive_client_hello(client_hello))

        replay = ServerHandshake(server_key, [raw_public(client_key)], CONNECTOR)
        replay.receive_client_hello(client_hello)
        assert_error("bad_signature", replay.receive_client_finish, client_finish)

    def test_rotation_accepts_either_key(self, keys):
        client_key, server_key = keys
        old_client_key = generate_identity_key()
        client = ClientHandshake(client_key, [raw_public(generate_identity_key()), raw_public(server_key)], CONNECTOR)
        server = ServerHandshake(server_key, [raw_public(old_client_key), raw_public(client_key)], CONNECTOR)
        client_finish, _ = client.receive_server_hello(server.receive_client_hello(client.start()))
        server.receive_client_finish(client_finish)

    def test_connector_mismatch_rejected(self, keys):
        client_key, server_key = keys
        client = ClientHandshake(client_key, [raw_public(server_key)], "other")
        server = ServerHandshake(server_key, [raw_public(client_key)], CONNECTOR)
        assert_error("bad_connector_id", server.receive_client_hello, client.start())

    def test_malformed_client_hello_rejected(self, keys):
        client_key, server_key = keys
        client_hello = ClientHandshake(client_key, [raw_public(server_key)], CONNECTOR).start()
        for bad in (client_hello[:-1], client_hello[:106] + b"\x00", client_hello[:106] + b"\x41" + b"a" * 65):
            server = ServerHandshake(server_key, [raw_public(client_key)], CONNECTOR)
            assert_error("bad_client_hello", server.receive_client_hello, bad)

    @pytest.mark.parametrize("offset,accepted", [(60, True), (-60, True), (61, False), (-61, False)])
    def test_clock_skew(self, keys, offset, accepted):
        client_key, server_key = keys
        client = ClientHandshake(client_key, [raw_public(server_key)], CONNECTOR, make_env(Clock(WALL + offset)))
        server = ServerHandshake(server_key, [raw_public(client_key)], CONNECTOR, make_env(Clock()))
        if accepted:
            server.receive_client_hello(client.start())
        else:
            assert_error("clock_skew", server.receive_client_hello, client.start())

    def test_handshake_timeout(self, keys):
        client_key, server_key = keys
        server_clock = Clock()
        client = ClientHandshake(client_key, [raw_public(server_key)], CONNECTOR, make_env(Clock()))
        server = ServerHandshake(server_key, [raw_public(client_key)], CONNECTOR, make_env(server_clock))
        client_finish, _ = client.receive_server_hello(server.receive_client_hello(client.start()))
        server_clock.mono += protocol.HANDSHAKE_TIMEOUT + 0.001
        assert_error("handshake_timeout", server.receive_client_finish, client_finish)

    def test_invalid_connector_id_refused_locally(self, keys):
        with pytest.raises(ValueError):
            ClientHandshake(keys[0], [raw_public(keys[1])], "bad id")


class TestRecords:
    def test_replay_rejected(self, keys):
        client_channel, server_channel = connect(*keys)
        frame = client_channel.encrypt(b"once")
        server_channel.decrypt(frame)
        assert_error("bad_sequence", server_channel.decrypt, frame)

    @pytest.mark.parametrize("position", [13, -1])
    def test_tampered_record_rejected(self, keys, position):
        client_channel, server_channel = connect(*keys)
        frame = bytearray(client_channel.encrypt(b"payload"))
        frame[position] ^= 1
        assert_error("bad_tag", server_channel.decrypt, bytes(frame))

    def test_reflected_record_rejected(self, keys):
        _, server_channel = connect(*keys)
        assert_error("bad_tag", server_channel.decrypt, server_channel.encrypt(b"mirror"))

    def test_text_and_bad_length_rejected(self, keys):
        client_channel, server_channel = connect(*keys)
        assert_error("text_frame", server_channel.decrypt, "text")
        _, server_channel = connect(*keys)
        assert_error("bad_length", server_channel.decrypt, b"\x00" * (protocol.MIN_FRAME - 1))

    def test_channel_dead_after_failure(self, keys):
        client_channel, server_channel = connect(*keys)
        assert_error("bad_length", server_channel.decrypt, b"short")
        assert_error("channel_closed", server_channel.decrypt, client_channel.encrypt(b"late"))

    def test_oversized_plaintext_keeps_channel_open(self, keys):
        client_channel, server_channel = connect(*keys)
        with pytest.raises(ValueError):
            client_channel.encrypt(b"x" * (protocol.MAX_PLAINTEXT + 1))
        assert server_channel.decrypt(client_channel.encrypt(b"still open")) == b"still open"


class TestRekey:
    def test_rekey_with_records_in_flight(self, keys):
        client_channel, server_channel = connect(*keys)
        rekey = client_channel.start_rekey()
        in_flight = client_channel.encrypt(b"old key")
        control = server_channel.decrypt(rekey)
        assert control.kind == "rekey" and control.key_no == 2
        assert server_channel.decrypt(in_flight) == b"old key"
        new_key_frame = server_channel.encrypt(b"new key")
        assert client_channel.decrypt(control.reply).kind == "rekey_ack"
        assert client_channel.decrypt(new_key_frame) == b"new key"
        assert server_channel.decrypt(client_channel.encrypt(b"both on 2")) == b"both on 2"
        assert client_channel.key_no == server_channel.key_no == 2

    def test_old_key_rejected_after_grace(self, keys):
        server_clock = Clock()
        client_channel, server_channel = connect(*keys, server_clock=server_clock)
        server_channel.decrypt(client_channel.start_rekey())
        late = client_channel.encrypt(b"too late")
        server_clock.mono += protocol.OLD_KEY_GRACE + 1
        assert_error("bad_key_no", server_channel.decrypt, late)

    def test_rekey_ack_timeout(self, keys):
        client_clock = Clock()
        client_channel, _ = connect(*keys, client_clock=client_clock)
        client_channel.start_rekey()
        client_clock.mono += protocol.REKEY_ACK_TIMEOUT + 1
        assert_error("rekey_timeout", client_channel.check_timers)

    def test_server_closes_without_rekey(self, keys):
        server_clock = Clock()
        _, server_channel = connect(*keys, server_clock=server_clock)
        server_clock.mono += protocol.SERVER_MAX_KEY_AGE + 1
        assert_error("key_expired", server_channel.check_timers)

    def test_needs_rekey_after_interval(self, keys):
        client_clock = Clock()
        client_channel, _ = connect(*keys, client_clock=client_clock)
        assert not client_channel.needs_rekey()
        client_clock.mono += protocol.REKEY_INTERVAL
        assert client_channel.needs_rekey()

    def test_rekey_from_server_rejected(self, keys):
        client_channel, server_channel = connect(*keys)
        frame = server_channel._seal(bytes([protocol.INNER_REKEY]) + struct.pack(">I", 2) + bytes(32))
        assert_error("bad_inner", client_channel.decrypt, frame)

    def test_unsolicited_ack_rejected(self, keys):
        client_channel, server_channel = connect(*keys)
        frame = server_channel._seal(bytes([protocol.INNER_REKEY_ACK]) + struct.pack(">I", 2) + bytes(32))
        assert_error("bad_rekey_ack", client_channel.decrypt, frame)

    def test_skipped_key_number_rejected(self, keys):
        client_channel, server_channel = connect(*keys)
        eph = protocol._x25519_public(protocol.X25519PrivateKey.generate())
        frame = client_channel._seal(bytes([protocol.INNER_REKEY]) + struct.pack(">I", 3) + eph)
        assert_error("bad_rekey", server_channel.decrypt, frame)


class TestKeyHelpers:
    def test_private_key_round_trip(self):
        key = generate_identity_key()
        assert public_key_to_b64(private_key_from_b64(private_key_to_b64(key))) == public_key_to_b64(key)

    def test_parse_public_key_list(self):
        a, b = public_key_to_b64(generate_identity_key()), public_key_to_b64(generate_identity_key())
        assert parse_public_key_list(f"{a}, {b}, {a}") == (public_key_from_b64(a), public_key_from_b64(b))
        with pytest.raises(ValueError):
            parse_public_key_list(f"{a},{b},{public_key_to_b64(generate_identity_key())}")
        with pytest.raises(ValueError):
            parse_public_key_list(" , ")

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
    def test_load_private_key_file_requires_0600(self, tmp_path):
        path = tmp_path / "identity.key"
        path.write_text(private_key_to_b64(generate_identity_key()))
        path.chmod(0o644)
        with pytest.raises(PermissionError):
            load_private_key_file(path)
        path.chmod(0o600)
        load_private_key_file(path)
