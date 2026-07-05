"""
Startup guards that refuse to run when configuration looks dangerous.

These checks run at module import time in app/main.py. If a guard
raises, the process exits before any route is registered or any port
is bound - the failure surfaces loudly in whatever init system started
the app, rather than silently producing a running-but-exposed backend.

## Current guards

- `check_network_binding_policy` - refuses to start if the process
  declares a public bind (0.0.0.0 or ::) without explicitly
  acknowledging that an authenticating reverse proxy sits in front.
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

BIND_HOST_ENV = "CYBEROPS_BIND_HOST"
TRUST_NETWORK_ENV = "CYBEROPS_TRUST_NETWORK"

# IPv4 all-interfaces and IPv6 all-interfaces. Anything else that reaches
# every interface (e.g., a specific public IP) is the operator's explicit
# choice and not covered by this guard - the value of this check is
# stopping the accidental default, not replacing a network admin.
_PUBLIC_BINDS = frozenset({"0.0.0.0", "::"})


class StartupGuardError(RuntimeError):
    """Raised when a startup guard refuses to let the process continue.

    The message is the source of truth for the operator. Init systems
    typically surface it as the last line of stderr before the process
    exits, which is where operators look first.
    """


def check_network_binding_policy(env: Optional[Mapping[str, str]] = None) -> None:
    """Refuse to start if CYBEROPS_BIND_HOST declares a public bind and
    CYBEROPS_TRUST_NETWORK is not set to '1'.

    The convention: any deployment that listens on all interfaces MUST
    declare CYBEROPS_BIND_HOST=0.0.0.0 (or '::') AND
    CYBEROPS_TRUST_NETWORK=1. Declaring the first without the second is
    almost always a mistake - typically a developer running the Docker
    image on their laptop and inadvertently exposing the unauthenticated
    API on their LAN, where the production deployment's YubiKey /
    oauth2-proxy gate doesn't exist.

    `env` defaults to `os.environ` and exists for tests to pass an
    explicit dict without mutating process state.
    """
    source = env if env is not None else os.environ

    bind_host = (source.get(BIND_HOST_ENV) or "").strip()
    if bind_host not in _PUBLIC_BINDS:
        return

    trust = (source.get(TRUST_NETWORK_ENV) or "").strip()
    if trust == "1":
        return

    raise StartupGuardError(
        f"{BIND_HOST_ENV}={bind_host!r} declares a public bind, but "
        f"{TRUST_NETWORK_ENV} is not set to '1'. This configuration "
        f"would expose the API to every host that can reach the bind "
        f"address - and the API is currently unauthenticated. "
        f"Either set {TRUST_NETWORK_ENV}=1 in the process environment "
        f"(and ONLY if an authenticating reverse proxy - YubiKey, VPN, "
        f"oauth2-proxy, Cloudflare Access, etc. - sits in front of this "
        f"backend), or bind to 127.0.0.1 instead."
    )
