"""HTTPS certificates. Phones only allow camera access on secure origins, so
the ground station serves HTTPS; to avoid browser security warnings it signs
its server certificate with its own small certificate authority:

  certs/ca.pem, ca-key.pem   "Coconut VTOL ground station local CA", made once
                             (10 years). Trust it once per device and every
                             server certificate it signs is accepted, including
                             new ones after the laptop's IP changes.
  certs/cert.pem, key.pem    the server certificate for localhost + this
                             laptop's IPs, signed by the CA; remade when the IPs
                             change.

Trusting the CA is the user's step (it changes the device's trust settings),
see README "No security warning": Windows `certutil -user -addstore Root
certs\\ca.pem`; phones download it from https://<laptop>:8443/ca.crt.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_NAME = "Coconut VTOL ground station local CA"


def local_ips() -> list[str]:
    ips = {"127.0.0.1"}
    try:                                     # the interface used for outbound traffic
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))     # no packet is sent
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        ips.update(a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return sorted(ips, key=lambda ip: (ip.startswith("127."), ip))


def _cert_ips(cert_path: Path) -> set[str]:
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:                 # not a server certificate of ours: remake it
        return set()
    return {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}


def _issued_by(cert_path: Path, ca: x509.Certificate) -> bool:
    return x509.load_pem_x509_certificate(cert_path.read_bytes()).issuer == ca.subject


def _write_key(path: Path, key) -> None:
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                       serialization.NoEncryption()))


def ensure_ca(cert_dir: Path) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_path, ca_key_path = cert_dir / "ca.pem", cert_dir / "ca-key.pem"
    if ca_path.exists() and ca_key_path.exists():
        return (x509.load_pem_x509_certificate(ca_path.read_bytes()),
                serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, CA_NAME),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Coconut VTOL")])
    now = dt.datetime.now(dt.timezone.utc)
    ca = (x509.CertificateBuilder()
          .subject_name(name).issuer_name(name)
          .public_key(key.public_key())
          .serial_number(x509.random_serial_number())
          .not_valid_before(now - dt.timedelta(days=1))
          .not_valid_after(now + dt.timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                       content_commitment=False, key_encipherment=False, data_encipherment=False,
                                       key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
          .sign(key, hashes.SHA256()))
    _write_key(ca_key_path, key)
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    return ca, key


def ensure_cert(cert_dir: Path) -> tuple[Path, Path, list[str]]:
    ca, ca_key = ensure_ca(cert_dir)
    cert_path, key_path = cert_dir / "cert.pem", cert_dir / "key.pem"
    ips = local_ips()
    if (cert_path.exists() and key_path.exists() and set(ips) <= _cert_ips(cert_path)
            and _issued_by(cert_path, ca)):
        return cert_path, key_path, ips
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Coconut VTOL ground station")]))
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=397))     # within what iOS/macOS accept for TLS
            .add_extension(x509.SubjectAlternativeName(
                [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]),
                critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _write_key(key_path, key)
    # serve the chain (server cert + CA) so clients can build the path
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path, ips


def ca_der(cert_dir: Path) -> bytes:
    """The CA certificate in DER form, the format phones install from a download."""
    ca, _ = ensure_ca(cert_dir)
    return ca.public_bytes(serialization.Encoding.DER)
