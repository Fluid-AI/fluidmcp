"""
fmcp-tunnel/1: end-to-end protection for the FluidMCP <-> GPT Engine tunnel.

Sans-IO: this module only turns bytes into bytes. Callers own the WebSocket.
This file is shared byte-for-byte with GPT Engine (services/mcp_tunnel_protocol.py);
change it only together with tests/tunnel_test_vectors.json. See docs/TUNNEL_PROTOCOL.md.
"""

import base64
import hashlib
import hmac
import os
import re
import stat
import struct
import time
from dataclasses import dataclass
from typing import Callable, NoReturn, Optional, Sequence, Tuple, Union

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION = 0x01
CTX_TRANSCRIPT = b"fmcp-tunnel/1 transcript"
CTX_SIG_SERVER = b"fmcp-tunnel/1 server signature"
CTX_SIG_CLIENT = b"fmcp-tunnel/1 client signature"
INFO_INIT = b"fmcp-tunnel/1 session keys"
INFO_REKEY = b"fmcp-tunnel/1 rekey keys"
CTX_REKEY_TH = b"fmcp-tunnel/1 rekey transcript"

MSG_CLIENT_HELLO = 0x01
MSG_SERVER_HELLO = 0x02
MSG_CLIENT_FINISH = 0x03

INNER_DATA = 0x00
INNER_REKEY = 0x01
INNER_REKEY_ACK = 0x02

DIR_C2S = 0x01
DIR_S2C = 0x02

MAX_FRAME = 10 * 1024 * 1024
HEADER_LEN = 12
TAG_LEN = 16
MIN_FRAME = HEADER_LEN + 1 + TAG_LEN
MAX_PLAINTEXT = MAX_FRAME - MIN_FRAME

MAX_SKEW = 60
HANDSHAKE_TIMEOUT = 10.0
REKEY_INTERVAL = 3600.0
REKEY_MSG_LIMIT = 100_000
REKEY_ACK_TIMEOUT = 30.0
OLD_KEY_GRACE = 30.0
SERVER_MAX_KEY_AGE = 7200.0
HARD_RECORDS_PER_KEY = 2 ** 20
MAX_KEYS_PER_SET = 2

CID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

CLIENT_HELLO_FIXED_LEN = 107
SERVER_HELLO_LEN = 170
SERVER_HELLO_SIGNED_LEN = 106
CLIENT_FINISH_LEN = 66


class ProtocolError(Exception):
    """Protocol violation. `code` is for local logs only and must never be sent to the peer."""

    def __init__(self, code: str):
        super().__init__("tunnel protocol error")
        self.code = code


@dataclass(frozen=True)
class Env:
    """Sources of randomness and time; replaced with fixed values in tests."""

    rng: Callable[[int], bytes] = os.urandom
    wall: Callable[[], float] = time.time
    mono: Callable[[], float] = time.monotonic


@dataclass(frozen=True)
class ControlMessage:
    """Re-key event returned by SecureChannel.decrypt. Send `reply` (if any) immediately."""

    kind: str
    key_no: int
    reply: Optional[bytes] = None


def _u8(n: int) -> bytes:
    return struct.pack(">B", n)


def _u32(n: int) -> bytes:
    return struct.pack(">I", n)


def _u64(n: int) -> bytes:
    return struct.pack(">Q", n)


def _lp(data: bytes) -> bytes:
    return _u8(len(data)) + data


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _transcript(*parts: bytes) -> bytes:
    return _sha256(_lp(CTX_TRANSCRIPT) + b"".join(parts))


def _in_set(candidate: bytes, allowed: Sequence[bytes]) -> bool:
    # Compare against every entry so timing doesn't reveal which key matched.
    found = False
    for key in allowed:
        found |= hmac.compare_digest(candidate, key)
    return found


def _x25519(private_key: X25519PrivateKey, peer_public: bytes) -> bytes:
    try:
        shared = private_key.exchange(X25519PublicKey.from_public_bytes(peer_public))
    except ValueError:
        raise ProtocolError("bad_dh") from None
    if shared == bytes(32):
        raise ProtocolError("bad_dh")
    return shared


def _x25519_public(private_key: X25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _ed25519_public(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _verify(public_key: bytes, signature: bytes, context: bytes, digest: bytes) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, _lp(context) + digest)
    except (InvalidSignature, ValueError):
        raise ProtocolError("bad_signature") from None


def _hkdf(secret: bytes, salt: bytes, info: bytes) -> Tuple[bytes, bytes, bytes]:
    okm = HKDF(algorithm=hashes.SHA256(), length=96, salt=salt, info=info).derive(secret)
    return okm[0:32], okm[32:64], okm[64:96]


def _derive_initial(shared: bytes, th_final: bytes) -> Tuple[bytes, bytes, bytes]:
    """Returns (k_c2s, k_s2c, chaining_key) for key_no 1."""
    return _hkdf(shared, th_final, _lp(INFO_INIT) + _u32(1))


def _derive_rekey(
    shared: bytes, chaining_key: bytes, th_final: bytes, key_no: int, eph_c: bytes, eph_s: bytes
) -> Tuple[bytes, bytes, bytes]:
    """Returns (k_c2s, k_s2c, chaining_key) for key_no; depends on all earlier keys via chaining_key."""
    rth = _sha256(_lp(CTX_REKEY_TH) + th_final + _u32(key_no) + eph_c + eph_s)
    return _hkdf(shared, chaining_key, _lp(INFO_REKEY) + _u32(key_no) + rth)


def _check_skew(ts: int, env: Env) -> None:
    if abs(int(env.wall()) - ts) > MAX_SKEW:
        raise ProtocolError("clock_skew")


class ClientHandshake:
    """Client (FluidMCP) side of the handshake: start() -> receive_server_hello()."""

    def __init__(
        self,
        identity_key: Ed25519PrivateKey,
        server_public_keys: Sequence[bytes],
        connector_id: str,
        env: Env = Env(),
    ):
        if not CID_RE.match(connector_id):
            raise ValueError("invalid connector_id")
        if not 1 <= len(server_public_keys) <= MAX_KEYS_PER_SET:
            raise ValueError("expected 1 or 2 server public keys")
        self._identity_key = identity_key
        self._server_public_keys = tuple(server_public_keys)
        self._connector_id = connector_id.encode("ascii")
        self._env = env
        self._client_hello: Optional[bytes] = None
        self._eph_key: Optional[X25519PrivateKey] = None
        self._eph_public = b""
        self._nonce = b""
        self._started_at = 0.0
        self._done = False

    def start(self) -> bytes:
        """Returns CLIENT_HELLO."""
        if self._client_hello is not None:
            raise ProtocolError("bad_state")
        self._eph_key = X25519PrivateKey.from_private_bytes(self._env.rng(32))
        self._eph_public = _x25519_public(self._eph_key)
        self._nonce = self._env.rng(32)
        self._started_at = self._env.mono()
        self._client_hello = (
            _u8(MSG_CLIENT_HELLO)
            + _u8(VERSION)
            + _u64(int(self._env.wall()))
            + self._eph_public
            + self._nonce
            + _ed25519_public(self._identity_key)
            + _u8(len(self._connector_id))
            + self._connector_id
        )
        return self._client_hello

    def receive_server_hello(self, message: bytes) -> Tuple[bytes, "SecureChannel"]:
        """Verifies SERVER_HELLO. Returns (CLIENT_FINISH, channel)."""
        if self._client_hello is None or self._done:
            raise ProtocolError("bad_state")
        self._done = True
        if self._env.mono() - self._started_at > HANDSHAKE_TIMEOUT:
            raise ProtocolError("handshake_timeout")
        if not isinstance(message, bytes) or len(message) != SERVER_HELLO_LEN:
            raise ProtocolError("bad_server_hello")
        if message[0] != MSG_SERVER_HELLO or message[1] != VERSION:
            raise ProtocolError("bad_server_hello")

        (ts,) = struct.unpack(">Q", message[2:10])
        eph_public_s = message[10:42]
        nonce_s = message[42:74]
        server_id_public = message[74:106]
        sig_s = message[106:170]

        if not _in_set(server_id_public, self._server_public_keys):
            raise ProtocolError("unknown_server_key")
        th_s = _transcript(self._client_hello, message[:SERVER_HELLO_SIGNED_LEN])
        _verify(server_id_public, sig_s, CTX_SIG_SERVER, th_s)
        _check_skew(ts, self._env)
        if eph_public_s == self._eph_public or nonce_s == self._nonce:
            raise ProtocolError("reflection")
        eph_key, self._eph_key = self._eph_key, None
        shared = _x25519(eph_key, eph_public_s)

        finish_prefix = _u8(MSG_CLIENT_FINISH) + _u8(VERSION)
        th_c = _transcript(self._client_hello, message, finish_prefix)
        client_finish = finish_prefix + self._identity_key.sign(_lp(CTX_SIG_CLIENT) + th_c)
        th_final = _transcript(self._client_hello, message, client_finish)
        channel = SecureChannel("client", shared, th_final, self._env)
        return client_finish, channel


class ServerHandshake:
    """Server (GPT Engine) side: receive_client_hello() -> receive_client_finish()."""

    def __init__(
        self,
        identity_key: Ed25519PrivateKey,
        client_public_keys: Sequence[bytes],
        expected_connector_id: str,
        env: Env = Env(),
    ):
        if not 1 <= len(client_public_keys) <= MAX_KEYS_PER_SET:
            raise ValueError("expected 1 or 2 client public keys")
        self._identity_key = identity_key
        self._client_public_keys = tuple(client_public_keys)
        self._expected_connector_id = expected_connector_id.encode("ascii", "replace")
        self._env = env
        self._started_at = env.mono()
        self._client_hello: Optional[bytes] = None
        self._server_hello: Optional[bytes] = None
        self._client_id_public = b""
        self._shared = b""
        self._done = False

    def _check_timeout(self) -> None:
        if self._env.mono() - self._started_at > HANDSHAKE_TIMEOUT:
            raise ProtocolError("handshake_timeout")

    def receive_client_hello(self, message: bytes) -> bytes:
        """Verifies CLIENT_HELLO. Returns SERVER_HELLO."""
        if self._client_hello is not None or self._done:
            raise ProtocolError("bad_state")
        self._check_timeout()
        if not isinstance(message, bytes) or len(message) < CLIENT_HELLO_FIXED_LEN:
            raise ProtocolError("bad_client_hello")
        if message[0] != MSG_CLIENT_HELLO or message[1] != VERSION:
            raise ProtocolError("bad_client_hello")
        cid_len = message[106]
        if not 1 <= cid_len <= 64 or len(message) != CLIENT_HELLO_FIXED_LEN + cid_len:
            raise ProtocolError("bad_client_hello")
        connector_id = message[107:]
        try:
            valid_cid = CID_RE.match(connector_id.decode("ascii")) is not None
        except UnicodeDecodeError:
            valid_cid = False
        if not valid_cid or not hmac.compare_digest(connector_id, self._expected_connector_id):
            raise ProtocolError("bad_connector_id")

        (ts,) = struct.unpack(">Q", message[2:10])
        _check_skew(ts, self._env)
        eph_public_c = message[10:42]
        client_id_public = message[74:106]
        if not _in_set(client_id_public, self._client_public_keys):
            raise ProtocolError("unknown_client_key")

        eph_key = X25519PrivateKey.from_private_bytes(self._env.rng(32))
        nonce_s = self._env.rng(32)
        eph_public_s = _x25519_public(eph_key)
        if eph_public_s == eph_public_c or nonce_s == message[42:74]:
            raise ProtocolError("reflection")
        self._shared = _x25519(eph_key, eph_public_c)

        signed = (
            _u8(MSG_SERVER_HELLO)
            + _u8(VERSION)
            + _u64(int(self._env.wall()))
            + eph_public_s
            + nonce_s
            + _ed25519_public(self._identity_key)
        )
        th_s = _transcript(message, signed)
        self._client_hello = message
        self._client_id_public = client_id_public
        self._server_hello = signed + self._identity_key.sign(_lp(CTX_SIG_SERVER) + th_s)
        return self._server_hello

    def receive_client_finish(self, message: bytes) -> "SecureChannel":
        """Verifies CLIENT_FINISH. Returns the channel; nothing else may be accepted before this."""
        if self._client_hello is None or self._server_hello is None or self._done:
            raise ProtocolError("bad_state")
        self._done = True
        self._check_timeout()
        if not isinstance(message, bytes) or len(message) != CLIENT_FINISH_LEN:
            raise ProtocolError("bad_client_finish")
        if message[0] != MSG_CLIENT_FINISH or message[1] != VERSION:
            raise ProtocolError("bad_client_finish")
        th_c = _transcript(self._client_hello, self._server_hello, message[:2])
        _verify(self._client_id_public, message[2:], CTX_SIG_CLIENT, th_c)
        th_final = _transcript(self._client_hello, self._server_hello, message)
        channel = SecureChannel("server", self._shared, th_final, self._env)
        self._shared = b""
        return channel


@dataclass
class _PendingRekey:
    key_no: int
    eph_key: X25519PrivateKey
    eph_public: bytes
    started_at: float


@dataclass
class _ReceiveKeys:
    key_no: int
    aead: AESGCM
    next_key_no: Optional[int] = None
    next_aead: Optional[AESGCM] = None
    old_deadline: float = 0.0


class SecureChannel:
    """
    Encrypted record layer after a completed handshake.

    Not task-safe: callers must run each encrypt/decrypt/start_rekey together with the
    send of its result under one asyncio.Lock, and close the connection if a send fails.
    """

    def __init__(self, role: str, shared: bytes, transcript_hash: bytes, env: Env):
        self.role = role
        self.transcript_hash = transcript_hash
        self._env = env
        self._own_dir = DIR_C2S if role == "client" else DIR_S2C
        self._peer_dir = DIR_S2C if role == "client" else DIR_C2S
        k_c2s, k_s2c, self._chaining_key = _derive_initial(shared, transcript_hash)
        send_key, recv_key = (k_c2s, k_s2c) if role == "client" else (k_s2c, k_c2s)
        self.key_no = 1
        self._send_aead = AESGCM(send_key)
        self._send_seq = 0
        self._send_count = 0
        self._recv = _ReceiveKeys(key_no=1, aead=AESGCM(recv_key))
        self._recv_seq = 0
        self._recv_count = 0
        self._key_established_at = env.mono()
        self._pending: Optional[_PendingRekey] = None
        self._dead = False

    def _fail(self, code: str) -> NoReturn:
        self._dead = True
        raise ProtocolError(code)

    def _check_alive(self) -> None:
        if self._dead:
            raise ProtocolError("channel_closed")

    def _seal(self, inner: bytes) -> bytes:
        self._check_alive()
        if self._send_seq >= 2 ** 63 or self._send_count >= HARD_RECORDS_PER_KEY:
            self._fail("record_limit")
        header = _u32(self.key_no) + _u64(self._send_seq)
        nonce = bytes(4) + _u64(self._send_seq)
        frame = header + self._send_aead.encrypt(nonce, inner, _u8(self._own_dir) + header)
        self._send_seq += 1
        self._send_count += 1
        return frame

    def encrypt(self, plaintext: bytes) -> bytes:
        """Returns a DATA record. Raises ValueError, without closing the channel, if too large."""
        if len(plaintext) > MAX_PLAINTEXT:
            raise ValueError("plaintext too large")
        return self._seal(_u8(INNER_DATA) + plaintext)

    def _promote_next_key(self) -> None:
        recv = self._recv
        self._recv = _ReceiveKeys(key_no=recv.next_key_no, aead=recv.next_aead)
        self._recv_count = 0

    def decrypt(self, frame: bytes) -> Union[bytes, ControlMessage]:
        """Returns DATA plaintext, or a ControlMessage for re-key traffic."""
        self._check_alive()
        if not isinstance(frame, bytes):
            self._fail("text_frame")
        if not MIN_FRAME <= len(frame) <= MAX_FRAME:
            self._fail("bad_length")
        key_no, seq = struct.unpack(">IQ", frame[:HEADER_LEN])
        if seq != self._recv_seq:
            self._fail("bad_sequence")

        recv = self._recv
        if recv.next_key_no is not None and self._env.mono() >= recv.old_deadline:
            self._promote_next_key()
            recv = self._recv
        if key_no == recv.key_no:
            aead, promote = recv.aead, False
        elif recv.next_key_no is not None and key_no == recv.next_key_no:
            aead, promote = recv.next_aead, True
        else:
            self._fail("bad_key_no")

        header = frame[:HEADER_LEN]
        try:
            inner = aead.decrypt(bytes(4) + header[4:], frame[HEADER_LEN:], _u8(self._peer_dir) + header)
        except InvalidTag:
            self._fail("bad_tag")
        self._recv_seq += 1
        if promote:
            self._promote_next_key()
        self._recv_count += 1
        if self._recv_count > HARD_RECORDS_PER_KEY:
            self._fail("record_limit")

        if not inner:
            self._fail("bad_inner")
        inner_type, body = inner[0], inner[1:]
        if inner_type == INNER_DATA:
            return body
        if inner_type == INNER_REKEY and self.role == "server":
            return self._on_rekey(key_no, body)
        if inner_type == INNER_REKEY_ACK and self.role == "client":
            return self._on_rekey_ack(body)
        self._fail("bad_inner")

    def _on_rekey(self, record_key_no: int, body: bytes) -> ControlMessage:
        if len(body) != 36 or self._recv.next_key_no is not None or record_key_no != self._recv.key_no:
            self._fail("bad_rekey")
        (new_key_no,) = struct.unpack(">I", body[:4])
        if new_key_no != self.key_no + 1 or new_key_no > 2 ** 32 - 1:
            self._fail("bad_rekey")
        eph_public_c = body[4:]
        eph_key = X25519PrivateKey.from_private_bytes(self._env.rng(32))
        eph_public_s = _x25519_public(eph_key)
        try:
            shared = _x25519(eph_key, eph_public_c)
        except ProtocolError:
            self._fail("bad_dh")
        k_c2s, k_s2c, chaining_key = _derive_rekey(
            shared, self._chaining_key, self.transcript_hash, new_key_no, eph_public_c, eph_public_s
        )
        ack = self._seal(_u8(INNER_REKEY_ACK) + _u32(new_key_no) + eph_public_s)

        # The client keeps sending under the old key until it processes the ack.
        self.key_no = new_key_no
        self._send_aead = AESGCM(k_s2c)
        self._send_count = 0
        self._recv.next_key_no = new_key_no
        self._recv.next_aead = AESGCM(k_c2s)
        self._recv.old_deadline = self._env.mono() + OLD_KEY_GRACE
        self._chaining_key = chaining_key
        self._key_established_at = self._env.mono()
        return ControlMessage("rekey", new_key_no, ack)

    def _on_rekey_ack(self, body: bytes) -> ControlMessage:
        pending = self._pending
        if pending is None or len(body) != 36:
            self._fail("bad_rekey_ack")
        (new_key_no,) = struct.unpack(">I", body[:4])
        if new_key_no != pending.key_no:
            self._fail("bad_rekey_ack")
        eph_public_s = body[4:]
        try:
            shared = _x25519(pending.eph_key, eph_public_s)
        except ProtocolError:
            self._fail("bad_dh")
        k_c2s, k_s2c, chaining_key = _derive_rekey(
            shared, self._chaining_key, self.transcript_hash, new_key_no, pending.eph_public, eph_public_s
        )
        self.key_no = new_key_no
        self._send_aead = AESGCM(k_c2s)
        self._send_count = 0
        self._recv = _ReceiveKeys(key_no=new_key_no, aead=AESGCM(k_s2c))
        self._recv_count = 0
        self._chaining_key = chaining_key
        self._key_established_at = self._env.mono()
        self._pending = None
        return ControlMessage("rekey_ack", new_key_no)

    def start_rekey(self) -> bytes:
        """Client only. Returns a REKEY record; keep sending DATA under the current key until the ack."""
        self._check_alive()
        if self.role != "client" or self._pending is not None:
            raise ProtocolError("bad_state")
        new_key_no = self.key_no + 1
        if new_key_no > 2 ** 32 - 1:
            self._fail("record_limit")
        eph_key = X25519PrivateKey.from_private_bytes(self._env.rng(32))
        eph_public = _x25519_public(eph_key)
        frame = self._seal(_u8(INNER_REKEY) + _u32(new_key_no) + eph_public)
        self._pending = _PendingRekey(new_key_no, eph_key, eph_public, self._env.mono())
        return frame

    def needs_rekey(self) -> bool:
        """Client only: True when the current key is due for replacement."""
        if self.role != "client" or self._pending is not None or self._dead:
            return False
        age = self._env.mono() - self._key_established_at
        return age >= REKEY_INTERVAL or self._send_count + self._recv_count >= REKEY_MSG_LIMIT

    def check_timers(self) -> None:
        """Call periodically (every few seconds). Raises ProtocolError when a timer has expired."""
        self._check_alive()
        now = self._env.mono()
        if self.role == "client":
            if self._pending is not None and now - self._pending.started_at > REKEY_ACK_TIMEOUT:
                self._fail("rekey_timeout")
            return
        if self._recv.next_key_no is not None and now >= self._recv.old_deadline:
            self._promote_next_key()
        if now - self._key_established_at > SERVER_MAX_KEY_AGE:
            self._fail("key_expired")


def generate_identity_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def private_key_to_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    return base64.b64encode(raw).decode("ascii")


def private_key_from_b64(value: str) -> Ed25519PrivateKey:
    raw = base64.b64decode(value.strip(), validate=True)
    if len(raw) != 32:
        raise ValueError("Ed25519 private key must be 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_key_to_b64(key: Union[Ed25519PrivateKey, Ed25519PublicKey]) -> str:
    if isinstance(key, Ed25519PrivateKey):
        key = key.public_key()
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def public_key_from_b64(value: str) -> bytes:
    raw = base64.b64decode(value.strip(), validate=True)
    if len(raw) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes")
    Ed25519PublicKey.from_public_bytes(raw)
    return raw


def parse_public_key_list(value: str) -> Tuple[bytes, ...]:
    """Parses a comma-separated list of 1 or 2 base64 public keys, ignoring duplicates."""
    keys = []
    for item in value.split(","):
        if item.strip():
            key = public_key_from_b64(item)
            if key not in keys:
                keys.append(key)
    if not 1 <= len(keys) <= MAX_KEYS_PER_SET:
        raise ValueError("expected 1 or 2 public keys")
    return tuple(keys)


def load_private_key_file(path: Union[str, "os.PathLike[str]"]) -> Ed25519PrivateKey:
    """Loads a base64 private key file, refusing files readable by group or others."""
    if os.name == "posix" and os.stat(path).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise PermissionError(f"{path} must not be accessible by group or others (chmod 600)")
    with open(path, "r", encoding="ascii") as f:
        return private_key_from_b64(f.read())
