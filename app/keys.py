"""The signing keys, held on disk so a restart does not invalidate everything.

``oidcutils.dev`` generates an ephemeral key at import and publishes exactly one
of them. That is the right default for a library, and wrong for a service a
client caches keys from: a restart changes the key while a client is still
holding the old JWKS, and every token fails with a signature error that looks
like a bug rather than a restart.

It also cannot express rotation. ``public_jwks`` returns a single key and
``mint_token`` writes a fixed ``kid``, so there is no way to publish the old key
beside the new one, which is the whole of what rotation is.

Both are fixed here by holding a keyring rather than a key. Signing is still
joserfc, the same library ``oidcutils`` signs with, so a token minted here
verifies exactly as one minted there does.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from joserfc import jwt
from joserfc.jwk import ECKey, RSAKey

from app.store import atomic_write

SigningKey = ECKey | RSAKey

CURVES = {"ES256": "P-256", "ES384": "P-384", "ES512": "P-521"}


def _algorithm_for(key: SigningKey) -> str:
    """Return the algorithm ``key`` signs with.

    Read from the key rather than configured, because a key and an algorithm
    that disagree produce tokens nothing can verify, and the key already says
    which it is. Same rule ``oidcutils`` applies, for the same reason.
    """
    if isinstance(key, RSAKey):
        return "RS256"
    curve = str(key.as_dict().get("crv"))
    return {v: k for k, v in CURVES.items()}.get(curve, "ES256")


@dataclass
class Keyring:
    """The keys this provider signs with and publishes.

    One key is active and signs. The rest are retired: still published, so a
    token minted before a rotation keeps verifying until it expires, and no
    longer used for anything new. That is what a real provider does and what a
    client's key cache is written against.
    """

    path: Path
    active_kid: str = ""
    keys: dict[str, SigningKey] = field(default_factory=dict)

    def load(self) -> None:
        """Read the keyring from disk, generating one if there is none.

        A first run writes a key rather than refusing to start. The alternative
        is a service that needs a setup step before it can do anything, which
        for a fixture is a step somebody will hit every time they clone.
        """
        if not self.path.exists():
            self.generate(make_active=True)
            return

        stored = json.loads(self.path.read_text())
        self.active_kid = stored["active"]
        self.keys = {}
        for kid, record in stored["keys"].items():
            data = record["jwk"]
            self.keys[kid] = (
                ECKey.import_key(data) if data["kty"] == "EC" else RSAKey.import_key(data)
            )

    def save(self) -> None:
        """Write the keyring to disk, private halves included.

        The private half has to be stored or the point is lost, so this file is
        the one thing here worth keeping out of a repository. It is inside
        ``instance/``, which is gitignored.
        """
        payload = {
            "active": self.active_kid,
            "keys": {
                kid: {"jwk": key.as_dict(private=True), "alg": _algorithm_for(key)}
                for kid, key in self.keys.items()
            },
        }
        atomic_write(self.path, json.dumps(payload, indent=2) + "\n")

    def generate(self, *, algorithm: str = "ES256", make_active: bool = True) -> str:
        """Add a new key and return its id.

        ``make_active`` is what makes this a rotation rather than an addition.
        Left true, new tokens are signed with the new key while the old one
        stays published; set false, the key is published but signs nothing,
        which is how a client's cache can be warmed before a cutover.
        """
        if algorithm == "RS256":
            key: SigningKey = RSAKey.generate_key(2048)
        else:
            key = ECKey.generate_key(CURVES.get(algorithm, "P-256"))

        kid = f"{algorithm.lower()}-{int(time.time())}-{len(self.keys)}"
        self.keys[kid] = key
        if make_active or not self.active_kid:
            self.active_kid = kid
        self.save()
        return kid

    def retire(self, kid: str) -> None:
        """Remove a key entirely, so tokens it signed stop verifying.

        Distinct from rotating away from it. A rotated key stays published and
        its tokens keep working; a retired one is gone, which is the case a
        client's error handling is rarely tested against.

        :raises ValueError: if the key is unknown or is the active one.
        """
        if kid not in self.keys:
            raise ValueError(f"No key with the id {kid!r}")
        if kid == self.active_kid:
            raise ValueError("The active key cannot be retired. Rotate to another first.")
        del self.keys[kid]
        self.save()

    def activate(self, kid: str) -> None:
        """Sign with ``kid`` from now on.

        :raises ValueError: if the key is unknown.
        """
        if kid not in self.keys:
            raise ValueError(f"No key with the id {kid!r}")
        self.active_kid = kid
        self.save()

    @property
    def active(self) -> SigningKey:
        """Return the key currently signing."""
        return self.keys[self.active_kid]

    def public_jwks(self) -> dict[str, Any]:
        """Return every published key, the active one first.

        Order matters to a client that picks a key without reading ``kid``.
        Putting the active one first means such a client works, and a client
        that does read ``kid`` is unaffected either way.
        """
        ordered = [self.active_kid, *(k for k in self.keys if k != self.active_kid)]
        keys = []
        for kid in ordered:
            pub = self.keys[kid].as_dict()
            pub["kid"] = kid
            pub["use"] = "sig"
            pub["alg"] = _algorithm_for(self.keys[kid])
            keys.append(pub)
        return {"keys": keys}

    def mint(self, claims: dict[str, Any], *, lifetime: int) -> str:
        """Return a signed token carrying ``claims``.

        The header names the key that signed it, which is how a client knows
        which of the published keys to verify against. ``oidcutils`` writes a
        constant there, which is why this does not call it.
        """
        now = int(time.time())
        key = self.active
        payload = {**claims, "iat": now, "exp": now + lifetime}
        header = {"alg": _algorithm_for(key), "kid": self.active_kid}
        return jwt.encode(header, payload, key)
