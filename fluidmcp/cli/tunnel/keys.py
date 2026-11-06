"""
Identity key storage for the tunnel client.

The private key never leaves this machine; only its public half is registered with GPT Engine.
"""

import os
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .protocol import generate_identity_key, load_private_key_file, private_key_to_b64, public_key_to_b64


def key_path() -> Path:
    """Active identity key: FMCP_TUNNEL_KEY_PATH, or ~/.fmcp/tunnel/identity.key."""
    configured = os.environ.get("FMCP_TUNNEL_KEY_PATH")
    return Path(configured) if configured else Path.home() / ".fmcp" / "tunnel" / "identity.key"


def next_key_path() -> Path:
    """Key created by a rotation, waiting to be activated."""
    path = key_path()
    return path.with_name(f"{path.stem}.next{path.suffix}")


def _write_new_key(path: Path) -> Ed25519PrivateKey:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = generate_identity_key()
    # O_EXCL: never overwrite an existing key; losing it would cut the tunnel until re-registered.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(private_key_to_b64(key) + "\n")
    return key


def generate_key(rotate: bool = False) -> Tuple[Path, str]:
    """
    Create the identity key, or with rotate=True a second key to activate later.

    Returns:
        (path written, base64 public key)

    Raises:
        FileExistsError: if the target key already exists
        FileNotFoundError: if rotating without an active key
    """
    if rotate:
        if not key_path().exists():
            raise FileNotFoundError(f"No active key at {key_path()}; run keygen without --rotate first")
        path = next_key_path()
    else:
        path = key_path()
    if path.exists():
        raise FileExistsError(f"Key already exists at {path}")
    return path, public_key_to_b64(_write_new_key(path))


def activate_next_key() -> str:
    """Replace the active key with the rotated one. Returns its base64 public key."""
    if not next_key_path().exists():
        raise FileNotFoundError(f"No rotated key at {next_key_path()}; run keygen --rotate first")
    public_key = public_key_to_b64(load_private_key_file(next_key_path()))
    os.replace(next_key_path(), key_path())
    return public_key


def load_identity_key() -> Ed25519PrivateKey:
    return load_private_key_file(key_path())
