#!/usr/bin/env python3

import argparse
import re
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

parser = argparse.ArgumentParser()

parser.add_argument("--pve", default="https://192.168.68.6:8006")
parser.add_argument("--user", default="root@pam")
parser.add_argument("--passfile", default=".pve-pass")
parser.add_argument("--domain", default="lan")
parser.add_argument("--out-dir", default="./out")

args = parser.parse_args()

PVE = args.pve
USER = args.user
PASSFILE = args.passfile
DOMAIN = args.domain
OUT_DIR = Path(args.out_dir)

# Notes/description: exemplos aceitos:
#   web=http:8080
#   web=https:8443
#   web=2283   (assume http)
WEB_RE = re.compile(
    r"(?im)\bweb(?:_port)?\s*[:=]\s*(?:(https?)\s*[:])?\s*(\d{1,5})\b")


def pick_ipv4_from_interfaces(ifaces):
    for iface in ifaces or []:
        for ip in (iface.get("ip-addresses") or []):
            # no seu caso vem "inet" (e pode vir inet6)
            if ip.get("ip-address-type") == "inet":
                addr = ip.get("ip-address")
                if addr and not addr.startswith("127."):
                    return addr
    return None


def web_from_description(desc):
    if not desc:
        return None, None
    m = WEB_RE.search(desc)
    if not m:
        return None, None
    scheme = (m.group(1) or "http").lower()
    port = int(m.group(2))
    if 1 <= port <= 65535:
        return scheme, port
    return None, None


def traefik_dynamic_yaml(hostname, ip, scheme, port):
    name = str(hostname).lower()
    fqdn = f"{name}.lan"
    url = f"{scheme}://{ip}:{port}"

    # se backend é https self-signed, habilita transport inseguro (mínimo)
    transport_block = ""
    transport_ref = ""
    if scheme == "https":
        transport_ref = f"\n        serversTransport: {name}-transport"
        transport_block = f"""
  serversTransports:
    {name}-transport:
      insecureSkipVerify: true
"""

    return f"""http:
  routers:
    {name}:
      rule: "Host(`{fqdn}`)"
      entryPoints: ["web","websecure"]
      service: {name}-svc
      tls: {{}}

  services:
    {name}-svc:
      loadBalancer:
        servers:
          - url: "{url}"{transport_ref}{transport_block}
"""


def safe_filename(name: str):
    # bem básico
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-").lower()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    password = open(PASSFILE, "r", encoding="utf-8").read().strip()

    r = requests.post(
        f"{PVE}/api2/json/access/ticket",
        data={"username": USER, "password": password},
        verify=False,
        timeout=10,
    )
    r.raise_for_status()
    ticket = r.json()["data"]["ticket"]

    s = requests.Session()
    s.verify = False
    s.headers.update({"Cookie": f"PVEAuthCookie={ticket}"})

    nodes = s.get(f"{PVE}/api2/json/nodes", timeout=10).json()["data"]

    for n in nodes:
        node = n["node"]
        lxcs = s.get(f"{PVE}/api2/json/nodes/{node}/lxc",
                     timeout=10).json()["data"]

        for ct in lxcs:
            vmid = ct["vmid"]

            cfg = s.get(
                f"{PVE}/api2/json/nodes/{node}/lxc/{vmid}/config",
                timeout=10
            ).json()["data"]

            hostname = cfg.get("hostname") or ct.get("name") or str(vmid)

            scheme, port = web_from_description(cfg.get("description"))
            if not scheme or not port:
                continue  # sem info nas notes

            try:
                ifaces = s.get(
                    f"{PVE}/api2/json/nodes/{node}/lxc/{vmid}/interfaces",
                    timeout=10
                ).json()["data"]
            except Exception:
                continue

            ip = pick_ipv4_from_interfaces(ifaces)
            if not ip:
                continue

            yml = traefik_dynamic_yaml(hostname, ip, scheme, port)

            fname = safe_filename(str(hostname)) + ".yaml"
            (OUT_DIR / fname).write_text(yml, encoding="utf-8")

    print(f"OK: arquivos gerados em {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
