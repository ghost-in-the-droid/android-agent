# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public issue**
2. Email **security@ghostinthedroid.com** or open a private security advisory on GitHub
3. Include a description of the vulnerability and steps to reproduce

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Scope

This project controls Android devices via ADB and runs subprocesses. Key security considerations:

- **No authentication** on the API by default — the server binds to `0.0.0.0:5055`. Do not expose to the public internet without adding auth.
- **ADB access** grants full device control. Only connect trusted devices.
- **Subprocess execution** — the scheduler and bot system launch Python scripts. Config is stored in the database, not user-supplied at runtime.
- **API keys** are loaded from `.env` and never logged or returned in API responses.

## Best Practices

- Run behind a reverse proxy (nginx/caddy) with authentication if exposing to a network
- Use `.env` for all secrets — never commit credentials
- Keep ADB debugging disabled on devices when not in use
