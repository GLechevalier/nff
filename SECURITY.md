# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (PyPI) | Yes |
| older releases | No — upgrade to latest |

## Scope

nff runs locally on your machine and communicates with hardware over USB. The attack surface is limited, but relevant concerns include:

- **Arbitrary code execution** via malicious sketch content passed to `nff flash`
- **Serial port injection** — crafted input sent via `serial_write` to a connected device
- **MCP server exposure** — the MCP server binds locally; any misconfiguration that exposes it to a network
- **Dependency vulnerabilities** — in `esptool`, `pyserial`, or `arduino-cli`

Out of scope: vulnerabilities in Wokwi's hosted infrastructure (report those to Wokwi directly).

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: gauthier.lechevalier26@gmail.com  
Subject line: `[nff security] <short description>`

Include:
- nff version (`pip show nff`)
- OS and Python version
- Steps to reproduce or a proof-of-concept
- What an attacker could achieve

**Response timeline:**
- Acknowledgement within 48 hours
- Assessment and severity within 7 days
- Fix or mitigation within 30 days for confirmed issues

You will be credited in the release notes unless you prefer to remain anonymous.
