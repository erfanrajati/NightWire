# NightWire Documentation

This directory contains the extended documentation for NightWire `1.0.2`.

## Guides

| Document | Audience | Contents |
| --- | --- | --- |
| [USAGE.md](USAGE.md) | Users | Files, clipboard, clients, passwords, retention, and browser behavior. |
| [CONFIGURATION.md](CONFIGURATION.md) | Operators | Runtime variables, installer options, storage, ports, and networking. |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Users and operators | Common startup, network, upload, clipboard, password, and mobile issues. |
| [SECURITY.md](SECURITY.md) | Operators and reviewers | Threat model, password scope, transport limits, and deployment guidance. |
| [PROJECT.md](PROJECT.md) | Maintainers | Architecture, repository layout, persistence, polling, and performance principles. |
| [API.md](API.md) | Integrators and contributors | Internal HTTP endpoints, payloads, responses, and status codes. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributors | Development setup, standards, tests, manual validation, and release workflow. |

Start with the repository-level [README](../README.md) for the project overview and installation instructions.

## Documentation conventions

- Commands are written for a shell in the project root unless another directory is shown.
- `0` seconds means unlimited retention.
- Security guidance assumes the default HTTP deployment on a trusted LAN.
- API examples describe version `1.0.2` and may change in a future major release.
