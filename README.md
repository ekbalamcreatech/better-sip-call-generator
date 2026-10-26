A Better SIP Call Generator

A web UI for generating SIP test calls with SIPp:
build call scenarios (optionally from a plain-English description with AI), run
them at a chosen rate against a SIP system, and get a ladder diagram, SIP
statistics, call-quality numbers, a PCAP and a PDF report.
Use it only against systems you own or are authorized to test.
See [SECURITY.md](SECURITY.md).

Built on SIPp. SIPp, the free open-source SIP test tool,
generates every call. This project is the web control panel around it, and the credit for
the SIP engine belongs to the SIPp authors. See Credits and licenses.

Docs: [User guide](docs/USER_GUIDE.md) · [Architecture and process flow](docs/ARCHITECTURE.md) ·
[Security](SECURITY.md) · [Contributing](CONTRIBUTING.md)

This project is provided as-is and maintained on a best-effort basis. Contributions, bug reports, and improvements are welcome.
Features
- TX and RX workspaces. TX runs a SIPp UAC (caller). RX runs a SIPp UAS (receiver).
  Several workspaces can run at once, per user, with conflict checks on IP and port.
- Scripts and intervals. Mix several scenarios in one test, split by percentage,
  and change the call rate over time (decimal CPS supported, e.g. 0.5 calls/sec).
- AI scenario generator (optional). Describe a call in text and get SIPp XML back.
  An admin picks the AI service once (Config > AI Provider): Anthropic, OpenAI, Google
  Gemini, or a self-hosted OpenAI-compatible model such as Ollama, LM Studio or vLLM.
  You paste your API key in the header box; it is forwarded for that one request and
  never stored. A self-hosted model with no authentication needs no key. Everything
  else works without AI.
- Media. G.711 µ-law/A-law and G.729 RTP from a bundled reference clip or your own
  audio, DTMF, plus loss, jitter and burst-loss impairment.
- Auth and STIR/SHAKEN. Optional SIP digest credentials, and PASSporT/Identity
  header generation and verification with a generated or uploaded certificate.
- Results. Live SIP ladder, SIP message counts, per-call quality, PCAP download,
  PDF report export.
- Teams. Users and admins. Users see their own workspaces; everyone shares the
  SUT list and saved scenarios/templates (only the owner or an admin can overwrite
  or delete them, so others load and save under a new name).

Requirements
- Linux (uses /proc, setpriv and tcpdump)
- Python 3.10+
- SIPp 3.7 or newer, on PATH
- tcpdump and setpriv (util-linux)
- ffmpeg (audio conversion and decoding captured RTP for quality scores)
- Optional: libbcg729 for G.729 (Debian/Ubuntu: sudo apt install libbcg729-0) and
  editcap from Wireshark for pcapng conversion
SIPp is licensed under GPLv3 and is not included here. Install it from your distro
or build it from source.

Quick start
Install the system dependencies listed under Requirements before proceeding.
git clone https://github.com/ekbalamcreatech/better-sip-call-generator.git
cd better-sip-call-generator
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
On first start the app creates an admin account and prints a random password
once to the console (or the journal). Open http://127.0.0.1:8000, log in, and
change the password.

To set the first password yourself, start with
SIPPTESTER_INITIAL_ADMIN_PASSWORD='your-long-password'.
Packet capture permissions
tcpdump needs privileges. Pick one:
- Run the app as root (not recommended), or
- sudo setcap cap_net_raw,cap_net_admin=eip $(readlink -f $(which tcpdump)), then set
  SIPPTESTER_SUDO=0, or
- Allow only tcpdump through sudo (default behaviour uses sudo -n):
  # /etc/sudoers.d/sip-call-generator
  youruser ALL=(root) NOPASSWD: /usr/bin/tcpdump
Run as a service (systemd)
# /etc/systemd/system/sip-call-generator.service
[Unit]
Description=A Better SIP Call Generator
After=network.target

[Service]
User=youruser
WorkingDirectory=/opt/better-sip-call-generator
Environment=SIPPTESTER_CAPTURE_IFACE=eth0
ExecStart=/opt/better-sip-call-generator/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
After saving the service file, run:
sudo systemctl daemon-reload
sudo systemctl enable --now sip-call-generator
Find the first-run admin password with
journalctl -u sip-call-generator | grep -A3 'First run'.

Keep it on 127.0.0.1 and put a TLS reverse proxy in front if other people need it.
Configuration
All settings are environment variables.
Variable        Default Meaning
SIPPTESTER_HOME app directory   Where data (storage/, run/, stir/, audio/, scenarios/) lives
SIPPTESTER_CAPTURE_IFACE        auto per target Force the tcpdump interface
SIPPTESTER_SUDO auto    0 = never use sudo for tcpdump
SIPPTESTER_INITIAL_ADMIN_PASSWORD       random  First-run admin password
SIPPTESTER_SESSION_TIMEOUT_MINUTES      20      Idle login timeout
SIPPTESTER_COOKIE_SECURE        auto    1 forces the Secure cookie flag
SIPPTESTER_TRUST_PROXY  off     Trust X-Forwarded-Proto from a reverse proxy
SIPPTESTER_ALLOWED_ORIGINS      same host only  Comma-separated extra origins allowed to make changes
SIPPTESTER_PUBLIC_URL   unset   Public base URL (used for the STIR certificate URL)
SIPPTESTER_MAX_CPS      1000    Highest allowed calls per second per script
SIPPTESTER_MAX_WORKSPACES_PER_USER      8       Workspace slots per user
SIPPTESTER_MAX_WORKSPACES_TOTAL 16      Workspace slots overall
SIPPTESTER_ALLOW_EXEC   off     Allow SIPp <exec> in scenarios. Dangerous: lets any user run commands on the server
SIPPTESTER_STIR_ALLOW_HTTP_CERT_URLS    off     Allow http:// certificate URLs when verifying PASSporTs
SIPPTESTER_STIR_ALLOW_PRIVATE_CERT_URLS off     Allow certificate URLs that resolve to private addresses


Layout
main.py          app setup, middleware, startup/shutdown
routes/          HTTP endpoints (auth, workspaces, library, media, quality, stir, users)
workspaces/      starting/stopping SIPp, capture, ladder, RTP sender, state
engines/         scenario guard, auth, STIR/SHAKEN, audio and PCAP parsing
storage/         JSON-file storage (no database)
static/          single-page UI (plain JavaScript, no build step)
Roles
        user    admin
Create and manage own workspaces and saved items        yes     yes
Load others' scenarios/templates        yes     yes
Overwrite/delete others' saved items    no      yes
See and stop everyone's workspaces      no      yes
Manage users, STIR certificate, run history     no      yes


Limitations
- Linux only. Data is kept in JSON files, so it suits a lab team, not thousands of users.
- It is a load generator for test systems, not a hardened internet-facing service.
- Sessions are in memory and are lost on restart.

Credits and licenses
This project is free software under the Apache License 2.0, Copyright 2026
Oswaldo Aguirre. See LICENSE.
- SIPp (GPL-3.0-or-later, Copyright The SIPp Authors) is
  the engine. It is not included here; you install it separately and this project runs it as
  a separate program. This project is independent and is not affiliated with or endorsed by
  the SIPp project.
- jsPDF and jsPDF-AutoTable (MIT) are bundled for the PDF report.
- FastAPI, Starlette, Uvicorn, Pydantic, python-multipart, cryptography, PyJWT and HTTPX
  (MIT, BSD-3-Clause or Apache-2.0) are installed with pip.
- tcpdump/libpcap, setpriv, FFmpeg, and optional libbcg729 are installed separately
  and are not bundled with this repository. libbcg729 is loaded as a library for G.729 support.
The complete list, with versions and what each is used for, is in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) and NOTICE.
