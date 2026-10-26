# Third-party software and licenses

A Better SIP Call Generator is released under the [Apache License 2.0](LICENSE),
Copyright 2026 Oswaldo Aguirre. It stands on the work of the projects below.
Thank you to all of their authors and maintainers.

## SIPp (the engine)

| | |
|---|---|
| Project | [SIPp](https://github.com/SIPp/sipp), a free open-source test tool and traffic generator for the SIP protocol |
| License | GNU General Public License v3 or later |
| Copyright | (C) 2003-2026 The SIPp Authors |
| How it is used | Run as a separate external program (one process per script and interval). It generates every SIP call. |
| Included in this repo? | **No.** You install SIPp yourself. |

This project does not contain or modify SIPp code. It builds a SIPp command line and a
scenario XML file, starts the `sipp` executable, and reads back the files SIPp writes.
Anyone who builds, packages or redistributes SIPp together with this project must
follow SIPp's GPL terms for SIPp itself. This project is not affiliated with the SIPp
project.

## Bundled in this repository (served to the browser)

| Component | Version | License | Used for |
|---|---|---|---|
| [jsPDF](https://github.com/parallax/jsPDF) | 2.5.1 | MIT | Creating the PDF report in the browser |
| [jsPDF-AutoTable](https://github.com/simonbengtsson/jsPDF-AutoTable) | 3.5.28 | MIT | Tables inside the PDF report |

The full license texts are in `static/vendor/jspdf.LICENSE` and `static/vendor/autotable.LICENSE`.

## Python libraries (installed with `pip`, not bundled)

| Library | License | Used for |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | Web framework and API |
| [Starlette](https://github.com/encode/starlette) | BSD-3-Clause | Web toolkit under FastAPI |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | Web server |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | Request validation |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 | Login and file-upload forms |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 OR BSD-3-Clause | STIR/SHAKEN keys and certificates |
| [PyJWT](https://github.com/jpadilla/pyjwt) | MIT | STIR/SHAKEN PASSporT tokens |
| [HTTPX](https://github.com/encode/httpx) | BSD-3-Clause | Calling the configured AI service |

## Programs the application runs (installed separately)

| Program | License | Used for |
|---|---|---|
| SIPp | GPL-3.0-or-later | Generating SIP calls (see above) |
| [tcpdump / libpcap](https://www.tcpdump.org/) | BSD-3-Clause | Packet capture for PCAP, RTP quality and ladder diagrams |
| setpriv (util-linux) | GPL-2.0-or-later | Making sure SIPp and tcpdump stop if the application is killed |
| [FFmpeg](https://ffmpeg.org/) | LGPL-2.1-or-later / GPL (depends on the build) | Converting audio to G.711 and decoding captured RTP for quality scoring |
| [libbcg729](https://gitlab.linphone.org/BC/public/bcg729) (Belledonne Communications) | GPL-3.0-or-later | Optional. Encodes and decodes G.729, loaded at run time through `ctypes` if installed. Without it, G.729 is unavailable and everything else works. |
| editcap (Wireshark) | GPL-2.0-or-later | Optional. Converts pcapng captures to classic pcap when present. |

None of these programs or libraries are copied into this repository. They are installed
separately by whoever runs the application.

## Optional online services

If an admin enables AI scenario generation, prompts are sent to the provider that admin
chose (Anthropic, OpenAI, Google Gemini, or a self-hosted model). Use of those services
is subject to their own terms and your own API keys. No account or key is bundled.
Product and company names are trademarks of their respective owners and are used only to
say which service is supported.

## Standards

The STIR/SHAKEN support follows public specifications (IETF RFC 8224, RFC 8225, RFC 8226
and the ATIS-1000074 SHAKEN framework) and was written independently from them. The SIP
behavior follows RFC 3261 and related RFCs through SIPp. No specification text or
third-party code is copied.

## Project-created content

The sample scenarios in `scenarios/` are written for this project. The reference audio in
`audio/` is generated, not recorded: `reference.wav` is a 30-second synthetic test tone,
`reference.pcmu` is that tone converted to G.711 u-law with FFmpeg, and `reference.g729` is
the same tone encoded with libbcg729. No third-party recordings are included. All of it is
covered by the same Apache-2.0 license.
