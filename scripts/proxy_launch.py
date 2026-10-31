#!/usr/bin/env python3
"""One-shot SOCKS5 options for Altare Wine; no persistent proxy settings."""
from __future__ import annotations

import ipaddress
import re
import socket


def parse_proxy(spec: str) -> dict:
    """Accept host:port or host:port:user:password (IPv4 or DNS, not IPv6)."""
    parts = spec.strip().split(":", 3)
    if len(parts) not in (2, 4):
        raise ValueError("Use ip:port or ip:port:user:password")
    host, raw_port = parts[:2]
    if not host or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,252}", host):
        raise ValueError("Invalid proxy host (use IPv4 or DNS name)")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,251}[A-Za-z0-9])?", host):
            raise ValueError("Invalid proxy host")
    if not raw_port.isdecimal() or not 1 <= int(raw_port) <= 65535:
        raise ValueError("Proxy port must be 1..65535")
    user, password = ("", "") if len(parts) == 2 else (parts[2], parts[3])
    for field in (user, password):
        if any(ch.isspace() or ord(ch) < 33 or ord(ch) > 126 for ch in field):
            raise ValueError("Proxy credentials must not contain spaces/control characters")
        if len(field.encode("utf-8")) > 255:
            raise ValueError("Proxy credential exceeds 255 bytes")
    if len(parts) == 4 and (not user or not password):
        raise ValueError("Proxy username and password must both be set")
    return {"host": host, "port": int(raw_port), "username": user, "password": password}


def proxychains_config(proxy: dict) -> str:
    p = parse_proxy(
        f"{proxy['host']}:{proxy['port']}" +
        (f":{proxy['username']}:{proxy['password']}" if proxy["username"] else "")
    )
    # Keep localhost for the game's local IPC (e.g. Data/socket.ini).
    return (
        "strict_chain\nproxy_dns\nlocalnet 127.0.0.0/255.0.0.0\n"
        "tcp_connect_time_out 8000\ntcp_read_time_out 15000\n[ProxyList]\n"
        f"socks5 {p['host']} {p['port']}" +
        (f" {p['username']} {p['password']}" if p["username"] else "") + "\n"
    )


def check_socks5(proxy: dict, timeout: float = 6.0) -> None:
    """Check proxy connectivity and optional username/password authentication."""
    with socket.create_connection((proxy["host"], proxy["port"]), timeout=timeout) as client:
        client.settimeout(timeout)
        method = 2 if proxy["username"] else 0
        client.sendall(bytes((5, 1, method)))
        reply = client.recv(2)
        if len(reply) != 2 or reply[0] != 5 or reply[1] != method:
            raise RuntimeError("SOCKS5 handshake/authentication method rejected")
        if method == 2:
            username = proxy["username"].encode("utf-8")
            password = proxy["password"].encode("utf-8")
            client.sendall(bytes((1, len(username))) + username +
                           bytes((len(password),)) + password)
            result = client.recv(2)
            if len(result) != 2 or result[1] != 0:
                raise RuntimeError("SOCKS5 credentials rejected")
