"""HTTPS SSL compatibility helpers for packaged Windows builds."""

from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path
from typing import Iterable


def _candidate_custom_ca_paths() -> Iterable[Path]:
    env_path = str(os.environ.get("OASIS_CA_BUNDLE", "") or "").strip()
    if env_path:
        yield Path(env_path)

    repo_root = Path(__file__).resolve().parents[3]
    yield repo_root / "certs" / "custom-ca.pem"
    yield repo_root / "certs" / "custom-ca.crt"
    yield repo_root / "certs" / "custom-ca.cer"


def _load_windows_cert_store(context: ssl.SSLContext) -> None:
    if os.name != "nt" or not hasattr(ssl, "enum_certificates"):
        return

    pem_parts: list[str] = []
    for store_name in ("ROOT", "CA"):
        try:
            for cert_bytes, encoding, trust in ssl.enum_certificates(store_name):
                if encoding != "x509_asn":
                    continue
                if trust not in (True, None) and "1.3.6.1.5.5.7.3.1" not in str(trust):
                    continue
                try:
                    pem_parts.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
                except Exception:
                    continue
        except Exception:
            continue

    if not pem_parts:
        return

    bundle_path = Path(tempfile.gettempdir()) / "oasis_windows_ca_bundle.pem"
    bundle_path.write_text("".join(pem_parts), encoding="utf-8")
    context.load_verify_locations(cafile=str(bundle_path))


def create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.load_default_certs()

    try:
        import certifi  # type: ignore

        context.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass

    _load_windows_cert_store(context)

    for path in _candidate_custom_ca_paths():
        try:
            if path.exists() and path.is_file():
                context.load_verify_locations(cafile=str(path))
        except Exception:
            continue

    return context

