# Security

## Authorized use only

A SIP call generator can originate large volumes of traffic, run external
processes and capture packets. **Only point this tool at systems you own or have
explicit written permission to test.** Sending test calls, floods or crafted
scenarios at third-party systems may be illegal and can disrupt real phone
service. You are responsible for how you use it.

## Deployment guidance

- Do not expose it directly to the public internet. Put it on a lab network or
  behind a VPN, or behind a TLS reverse proxy that you control.
- Use HTTPS in front of it and set `SIPPTESTER_COOKIE_SECURE=1` (or
  `SIPPTESTER_TRUST_PROXY=1` when the proxy sets `X-Forwarded-Proto`).
- If it is served under a different hostname than the one it sees, set
  `SIPPTESTER_ALLOWED_ORIGINS` or the cross-site request check will block you.
- Run it as an unprivileged user. It needs permission to run `tcpdump`
  (root, `setcap`, or a narrow `sudoers` rule for `tcpdump`).
- Back up nothing from `storage/` or `stir/` into a public place: they hold
  password hashes and the STIR signing key.

## Built-in protections

- Scenario XML is parsed and checked against an allowlist of SIPp elements.
  `<exec>` and other command-running features are refused unless the operator
  sets `SIPPTESTER_ALLOW_EXEC=1` (this allows remote code execution by any
  logged-in user; do not enable it on a shared server).
- All request fields that reach a SIPp command line, CSV file or file path are
  validated.
- State-changing requests are checked for same-origin; sessions are
  invalidated on password change, role change and deletion.
- STIR/SHAKEN certificate fetching is HTTPS-only, pins the validated IP and
  refuses private addresses unless you opt in.
- Keys and user files are written with owner-only permissions.
- The AI scenario generator sends your prompt to the AI service an admin configured
  (Anthropic, OpenAI, Gemini or a self-hosted model). The API key you type is passed
  through this server for that one request and is never stored or logged. Because the
  key crosses your network to the server, use HTTPS in front of it on anything but a
  trusted LAN. Only admins can change the AI endpoint, and link-local/metadata
  addresses are refused.

## Reporting a vulnerability

Please open a private security advisory on the repository (or email the
maintainer listed in the repository profile). Do not file public issues for
unfixed vulnerabilities. This is a hobby-grade project maintained on a
best-effort basis.
