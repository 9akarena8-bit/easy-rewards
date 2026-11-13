"""Public-key verification shared with the launcher. Contains no issuing secrets."""
from __future__ import annotations

import base64
import json
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

INSTALLATION_ID = re.compile(r"[A-Za-z0-9_-]{16,128}")
PAYLOAD_FIELDS = {"version", "license_id", "installation_id", "issued_at", "expires_at", "access"}
ACTIVATION_PREFIX = "FPT2."


def activation_code(document: dict) -> str:
    """Portable signed activation code (not a bearer admin credential)."""
    raw = json.dumps(document, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":")).encode("ascii")
    if len(raw) > 8192:
        raise ValueError("invalid_license_document")
    return ACTIVATION_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def parse_license_input(text: str) -> dict:
    """Accept original JSON file contents or an FPT2 offline code."""
    if not isinstance(text, str) or len(text) > 16384:
        raise ValueError("invalid_license_document")
    text = text.strip()
    try:
        data = text
        if text.startswith(ACTIVATION_PREFIX):
            encoded = text[len(ACTIVATION_PREFIX):]
            if not re.fullmatch(r"[A-Za-z0-9_-]{100,11000}", encoded):
                raise ValueError("invalid_license_document")
            data = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
            if len(data) > 8192:
                raise ValueError("invalid_license_document")
        document = json.loads(data)
        if not isinstance(document, dict):
            raise ValueError("invalid_license_document")
        return document
    except (ValueError, RecursionError) as exc:
        raise ValueError("invalid_license_document") from exc


def canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def verify_license(document: dict, public_key_pem: bytes, installation_id: str,
                   now: int | None = None) -> dict:
    """Return verified claims or raise ValueError. Local clock is NOT tamper-proof."""
    try:
        if not isinstance(document, dict) or set(document) != {"payload", "signature"}:
            raise ValueError("invalid_license_document")
        payload, signature = document["payload"], document["signature"]
        if not isinstance(payload, dict) or set(payload) != PAYLOAD_FIELDS:
            raise ValueError("invalid_license_payload")
        if (type(payload["version"]) is not int or payload["version"] not in (1, 2)
                or not isinstance(payload["license_id"], str)
                or not re.fullmatch(r"[A-F0-9]{32}", payload["license_id"])
                or not isinstance(payload["installation_id"], str)
                or not INSTALLATION_ID.fullmatch(payload["installation_id"])
                or payload["access"] not in ("paid", "friend", "owner")
                or type(payload["issued_at"]) is not int
                or not isinstance(signature, str) or len(signature) > 128):
            raise ValueError("invalid_license_payload")
        # Version 1 is the original fixed-term format. Version 2 allows an
        # explicitly perpetual owner/friend entitlement (expires_at=null).
        if payload["version"] == 1:
            if (payload["access"] == "owner" or type(payload["expires_at"]) is not int
                    or not 0 < payload["issued_at"] < payload["expires_at"] < 2**53):
                raise ValueError("invalid_license_payload")
        elif payload["version"] == 2:
            if (payload["access"] not in ("owner", "friend")
                    or payload["expires_at"] is not None or payload["issued_at"] <= 0):
                raise ValueError("invalid_license_payload")
        else:
            raise ValueError("invalid_license_payload")
        public_key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("invalid_public_key")
        raw_signature = base64.b64decode(signature, validate=True)
        if len(raw_signature) != 64:
            raise ValueError("invalid_license_signature")
        public_key.verify(raw_signature, canonical_payload(payload))
        if payload["installation_id"] != installation_id:
            raise ValueError("license_for_other_installation")
        current = int(time.time()) if now is None else now
        if payload["issued_at"] > current + 300:
            raise ValueError("license_not_yet_valid")
        if payload["expires_at"] is not None and payload["expires_at"] <= current:
            raise ValueError("license_expired")
        return dict(payload)
    except (InvalidSignature, TypeError, KeyError) as exc:
        raise ValueError("invalid_license_signature") from exc
