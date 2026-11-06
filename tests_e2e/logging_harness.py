"""Subprocess harness: drive FluidMCP's production logging/Sentry setup with dummy secrets.

Run by test_security_redaction.py in a fresh interpreter so global logging and
Sentry state never leaks into the test process. Secrets are read from the JSON
file named by ``E2E_SECRETS_FILE`` (a list of dummy credentials), never argv.

Modes:
  logs    configure logging exactly as ``fmcp serve`` does, then emit every
          secret through loguru (info/error/exception with a nested cause),
          stdlib logging (with a traceback), print(), and finally an uncaught
          nested exception handled by the interpreter's default excepthook.
  sentry  initialise Sentry exactly as ``fmcp serve`` does (SENTRY_DSN points at
          the test's local ingest server) and send an exception event whose
          message, cause, breadcrumbs and stack-frame locals carry the secrets.
"""

import json
import logging
import os
import sys


def load_secrets():
    with open(os.environ["E2E_SECRETS_FILE"]) as handle:
        return json.load(handle)


def raise_nested(secrets):
    api_key = secrets[0]  # a stack-frame local holding a credential
    try:
        raise ConnectionError("upstream rejected credentials: " + " ".join(secrets))
    except ConnectionError as inner:
        raise RuntimeError(f"provider call failed using {api_key}") from inner


def logs_mode(secrets):
    from loguru import logger
    from fluidmcp.cli import server

    server._configure_json_logging()
    joined = " ".join(secrets)
    logger.info(f"E2E-MARKER loguru info: {joined}")
    logger.bind(server_id="e2e").warning(f"E2E-MARKER loguru warning: {joined}")
    try:
        raise_nested(secrets)
    except RuntimeError:
        logger.exception("E2E-MARKER loguru exception")

    std = logging.getLogger("httpx")
    std.addHandler(logging.StreamHandler(sys.stderr))
    std.setLevel(logging.INFO)
    std.info("E2E-MARKER stdlib request: GET https://api.example.invalid/v1?api_key=%s", secrets[0])
    std.error("E2E-MARKER stdlib error: %s", joined)
    try:
        raise_nested(secrets)
    except RuntimeError:
        std.exception("E2E-MARKER stdlib exception")

    print(f"E2E-MARKER print: {joined}", flush=True)
    raise_nested(secrets)  # uncaught: written by sys.excepthook to stderr


def sentry_mode(secrets):
    import sentry_sdk
    from fluidmcp.cli import server

    # As in `fmcp serve`: logging redaction is active alongside Sentry, so the
    # process's own console output is sanitized too.
    server._configure_json_logging()
    server.init_sentry()
    logging.getLogger("e2e").warning("E2E-MARKER breadcrumb: %s", " ".join(secrets))
    try:
        raise_nested(secrets)
    except RuntimeError as exc:
        sentry_sdk.capture_exception(exc)
    logging.getLogger("e2e").error("E2E-MARKER logged error: %s", " ".join(secrets))
    sentry_sdk.flush(timeout=10)
    print("E2E-MARKER sentry flushed", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1]
    {"logs": logs_mode, "sentry": sentry_mode}[mode](load_secrets())
