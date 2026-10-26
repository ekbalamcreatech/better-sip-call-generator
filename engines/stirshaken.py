"""
STIR/SHAKEN Engine
PASSporT JWT generation and verification per RFC 8225/8226
Supports self-signed and BYOC (Bring Your Own Certificate)
"""
import jwt
import time
import os
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import load_pem_x509_certificate
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime
import ipaddress
import socket
import http.client
import ssl
from urllib.parse import urlparse
from config import STIR_DIR
from fsutil import write_private, tighten


KEY_FILE  = os.path.join(STIR_DIR, "stir_key.pem")
CERT_FILE = os.path.join(STIR_DIR, "stir_cert.pem")
PUBLIC_URL = os.environ.get("SIPPTESTER_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
CERT_URL  = PUBLIC_URL + "/stir/cert"
_PUBLIC_HOST = urlparse(PUBLIC_URL).hostname or "127.0.0.1"

def generate_keypair() -> bool:
    """Generate EC P-256 key pair and self-signed certificate."""
    try:
        # generate private key
        key = ec.generate_private_key(ec.SECP256R1())

        # write private key
        write_private(KEY_FILE, key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

        # generate self-signed cert
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SIP Test Builder"),
            x509.NameAttribute(NameOID.COMMON_NAME, "STIR/SHAKEN Test Certificate"),
        ])

        cert = (x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(_PUBLIC_HOST)]),
                critical=False
            )
            .sign(key, hashes.SHA256())
        )

        with open(CERT_FILE, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        print(f"STIR keypair generated: {KEY_FILE}, {CERT_FILE}")
        return True

    except Exception as e:
        print(f"Keypair generation error: {e}")
        return False

def load_private_key(key_path: str = None):
    """Load private key from file."""
    path = key_path or KEY_FILE
    if not os.path.exists(path):
        generate_keypair()
    tighten(path)  # keys written by older versions may be world-readable
    with open(path, 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def generate_passport(
    orig_tn: str,
    dest_tn: str,
    attestation: str = "A",
    orig_id: str = None,
    key_path: str = None,
    cert_url: str = None,
    expires: int = 60
) -> dict:
    """
    Generate a PASSporT JWT token per RFC 8225.
    Returns dict with token, header value, and decoded payload.
    """
    try:
        if not os.path.exists(KEY_FILE):
            generate_keypair()

        private_key = load_private_key(key_path)
        cert_url = cert_url or CERT_URL
        orig_id  = orig_id or f"siptestbuilder-{int(time.time())}"

        # clean phone numbers - remove non-digits except +
        orig_tn = ''.join(c for c in orig_tn if c.isdigit() or c == '+')
        dest_tn = ''.join(c for c in dest_tn if c.isdigit() or c == '+')

        # add + prefix if not present
        if not orig_tn.startswith('+'):
            orig_tn = '+1' + orig_tn if len(orig_tn) == 10 else '+' + orig_tn
        if not dest_tn.startswith('+'):
            dest_tn = '+1' + dest_tn if len(dest_tn) == 10 else '+' + dest_tn

        iat = int(time.time())

        payload = {
            "attest": attestation,
            "dest":   {"tn": [dest_tn]},
            "iat":    iat,
            "orig":   {"tn": orig_tn},
            "origid": orig_id
        }

        headers = {
            "alg": "ES256",
            "ppt": "shaken",
            "typ": "passport",
            "x5u": cert_url
        }

        token = jwt.encode(
            payload,
            private_key,
            algorithm="ES256",
            headers=headers
        )

        # build SIP Identity header value
        identity_header = f"{token};info=<{cert_url}>;alg=ES256;ppt=shaken"

        return {
            "token": token,
            "identity_header": identity_header,
            "payload": payload,
            "headers": headers,
            "cert_url": cert_url,
            "attestation": attestation,
            "orig_tn": orig_tn,
            "dest_tn": dest_tn,
            "iat": iat,
            "expires_at": iat + expires
        }

    except Exception as e:
        print(f"PASSporT generation error: {e}")
        return {"error": str(e)}


_MAX_CERT_BYTES = 64 * 1024
_CERT_TIMEOUT_S = 5


def _is_own_cert_url(u) -> bool:
    """True only for exactly our own published cert URL (served from disk, no network)."""
    own = urlparse(CERT_URL)
    default = lambda x: x.port or (443 if x.scheme == "https" else 80)
    return (u.scheme, u.hostname, default(u), u.path) == (own.scheme, own.hostname, default(own), own.path)


def _public_addresses(host: str, port: int, allow_private: bool) -> list:
    """Resolve `host` ONCE and return its addresses, refusing any that are not public."""
    found = []
    for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        addr = ipaddress.ip_address(info[4][0])
        blocked = addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified or addr.is_reserved
        if blocked or (addr.is_private and not allow_private):
            raise ValueError(f"cert URL host resolves to a non-public address ({addr})")
        if str(addr) not in found:
            found.append(str(addr))
    if not found:
        raise ValueError("cert URL host did not resolve")
    return found


def _pinned_connection(scheme: str, host: str, port: int, ip: str):
    """
    HTTP(S) connection that connects to the already-validated `ip`, so a DNS
    answer that changes between our check and the connection (DNS rebinding)
    cannot redirect us. For HTTPS the certificate is still verified against `host`.
    """
    if scheme == "https":
        conn = http.client.HTTPSConnection(host, port, timeout=_CERT_TIMEOUT_S, context=ssl.create_default_context())
    else:
        conn = http.client.HTTPConnection(host, port, timeout=_CERT_TIMEOUT_S)

    def connect():
        sock = socket.create_connection((ip, port), _CERT_TIMEOUT_S)
        conn.sock = conn._context.wrap_socket(sock, server_hostname=host) if scheme == "https" else sock

    conn.connect = connect
    return conn


def _fetch_cert_pem(cert_url: str) -> bytes:
    """Fetch the signer certificate named in an Identity header's info= URL.

    The URL comes from untrusted input, so: HTTPS only (SIPPTESTER_STIR_ALLOW_HTTP_CERT_URLS=1
    allows http for labs), no redirects, size capped, DNS resolved once and the connection
    pinned to that validated address, and non-public addresses refused (loopback, link-local,
    metadata, private ranges). Labs hosting the cert on a private address can opt in with
    SIPPTESTER_STIR_ALLOW_PRIVATE_CERT_URLS=1.
    """
    u = urlparse(cert_url)
    allow_http = os.environ.get("SIPPTESTER_STIR_ALLOW_HTTP_CERT_URLS") == "1"
    if not u.hostname or u.scheme not in (("http", "https") if allow_http else ("https",)):
        raise ValueError("cert URL must be https" + (" or http" if allow_http else ""))
    if _is_own_cert_url(u):
        with open(CERT_FILE, "rb") as f:
            return f.read()
    port = u.port or (443 if u.scheme == "https" else 80)
    ip = _public_addresses(u.hostname, port, os.environ.get("SIPPTESTER_STIR_ALLOW_PRIVATE_CERT_URLS") == "1")[0]
    conn = _pinned_connection(u.scheme, u.hostname, port, ip)
    try:
        conn.request("GET", (u.path or "/") + (f"?{u.query}" if u.query else ""),
                     headers={"Accept": "application/pem-certificate-chain, application/x-pem-file, */*"})
        resp = conn.getresponse()
        if resp.status != 200:  # includes 3xx: redirects are never followed
            raise ValueError(f"cert URL returned HTTP {resp.status}")
        return resp.read(_MAX_CERT_BYTES)
    finally:
        conn.close()

def verify_passport(identity_header: str, fetch_cert: bool = True) -> dict:
    """
    Verify a PASSporT JWT from an Identity header.
    Returns verification result with attestation level.
    """
    try:
        # parse Identity header
        # format: <token>;info=<url>;alg=ES256;ppt=shaken
        parts = identity_header.split(';')
        token = parts[0].strip()

        # extract cert URL
        cert_url = None
        for part in parts:
            if 'info=' in part:
                cert_url = part.strip().replace('info=<','').replace('>','').strip()

        # decode without verification first to get claims
        unverified = jwt.decode(token, options={"verify_signature": False})

        result = {
            "token": token,
            "cert_url": cert_url,
            "raw_payload": unverified,
            "attestation": unverified.get("attest", "unknown"),
            "orig_tn": unverified.get("orig", {}).get("tn", "unknown"),
            "dest_tn": unverified.get("dest", {}).get("tn", ["unknown"])[0] if isinstance(unverified.get("dest", {}).get("tn"), list) else "unknown",
            "iat": unverified.get("iat", 0),
            "origid": unverified.get("origid", ""),
            "verified": False,
            "verification_error": None
        }

        # check expiry
        age = int(time.time()) - result["iat"]
        result["age_seconds"] = age
        if age > 60:
            result["verification_error"] = f"Token expired ({age}s old, max 60s)"
            return result

        # try to verify signature
        if fetch_cert and cert_url:
            try:
                cert_pem = _fetch_cert_pem(cert_url)
                cert = load_pem_x509_certificate(cert_pem)
                public_key = cert.public_key()
                jwt.decode(token, public_key, algorithms=["ES256"],
                          options={"verify_exp": False})
                result["verified"] = True
                result["cert_subject"] = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            except Exception as e:
                result["verification_error"] = f"Signature verification failed: {str(e)}"

        else:
            # verify against local cert
            if os.path.exists(CERT_FILE):
                with open(CERT_FILE, 'rb') as f:
                    cert = load_pem_x509_certificate(f.read())
                public_key = cert.public_key()
                try:
                    jwt.decode(token, public_key, algorithms=["ES256"],
                              options={"verify_exp": False})
                    result["verified"] = True
                except Exception as e:
                    result["verification_error"] = str(e)

        return result

    except Exception as e:
        return {"error": str(e), "verified": False}

def get_cert_info() -> dict:
    """Get info about the current certificate."""
    if not os.path.exists(CERT_FILE):
        return {"exists": False}
    try:
        with open(CERT_FILE, 'rb') as f:
            cert = load_pem_x509_certificate(f.read())
        return {
            "exists": True,
            "subject": cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value,
            "not_before": cert.not_valid_before.isoformat(),
            "not_after": cert.not_valid_after.isoformat(),
            "serial": str(cert.serial_number),
            "self_signed": cert.issuer == cert.subject,
            "cert_url": CERT_URL
        }
    except Exception as e:
        return {"exists": True, "error": str(e)}

def upload_cert(cert_pem: bytes, key_pem: bytes) -> bool:
    """Upload BYOC certificate and key."""
    try:
        # validate cert
        cert = load_pem_x509_certificate(cert_pem)
        # validate key
        serialization.load_pem_private_key(key_pem, password=None)
        # write files
        with open(CERT_FILE, 'wb') as f:
            f.write(cert_pem)
        byoc_key = os.path.join(STIR_DIR, "byoc_key.pem")
        write_private(byoc_key, key_pem)
        print(f"BYOC cert uploaded: {cert.subject}")
        return True
    except Exception as e:
        print(f"BYOC upload error: {e}")
        return False
