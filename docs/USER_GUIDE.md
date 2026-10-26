# User guide

A short tour of the concepts and the usual workflow.

## Concepts

- **Workspace.** One independent test. A **TX** workspace places calls (SIPp acts as the
  caller). An **RX** workspace answers calls (SIPp acts as the receiver). Each belongs to
  one user. You can run several at once.
- **SUT.** The system under test: the address and port you send calls to. Anyone can add
  one to the shared list; only its creator or an admin can edit or delete it.
- **Script.** One call flow inside a TX workspace: a target, source IP and port, a share of
  the traffic, a number plan, optional media, STIR/SHAKEN and authentication, and the
  SIPp scenario XML. A workspace can run several scripts together.
- **Interval.** A time slice of the test with a duration and a calls-per-second rate for
  each script. Intervals run in order. **0 CPS pauses** that script for the interval.
  Rates can be fractions (0.5 = one call every two seconds).
- **Number plan.** The calling and called numbers. A fixed number repeats; a range such as
  `555[0001-0200]` counts up. The plan picks which numbers are used. It never changes the
  call count, which comes from CPS x duration.

## Typical workflow

1. **Log in.** On a fresh install, use the `admin` password printed once at first start.
2. **Add a workspace** and choose TX or RX.
3. **Set the target** (pick a SUT or add one) and the source IP and port.
4. **Get a scenario.** Load a saved or sample one, paste your own SIPp XML, or describe the
   call in words and press Generate (needs the AI provider set up, see below).
5. **Add intervals.** For example 10 s at 5 CPS, a 5 s pause, then 10 s at 5 CPS = 100 calls.
6. **Start.** Watch the counters:
   - **Sent** - calls started
   - **Completed** - finished successfully
   - **Failed** - SIPp counted them as failed (includes calls that never got an answer)
   - **In progress** - still open
   - **Retransmits** - messages sent again because there was no reply
7. **Review results:** the SIP ladder (pick a call), SIP statistics, call quality, then
   export the **PCAP** or a **PDF report**.

To test receiving, set up an RX workspace first, start it, then point a TX workspace (or
your own equipment) at it.

## Saving and sharing

- Save scenarios, scripts and whole workspaces as templates.
- Everyone can load them. Only the owner or an admin can overwrite or delete, so to change
  someone else's, load it and save it under a new name.
- Your own workspaces are private to you (admins can see and stop any workspace).

## AI scenario generation (optional)

An admin chooses the provider once under **Config > AI Provider**: Anthropic, OpenAI,
Google Gemini, or a self-hosted OpenAI-compatible model (Ollama, LM Studio, vLLM). Type
your API key into the header box when generating; it is used for that request only and is
never stored. Self-hosted models without authentication need no key. Generated XML is
always checked by the scenario guard before it can run.

## Roles

| | user | admin |
|---|---|---|
| Run own workspaces, add SUTs, save scenarios | yes | yes |
| See and stop everyone's workspaces | no | yes |
| Manage users, STIR certificate, AI provider, run history | no | yes |
| Edit or delete others' saved items | no | yes |

## Limits and good practice

- Only test systems you own or are authorized to test. See [SECURITY.md](../SECURITY.md).
- Per-script rate is capped by `SIPPTESTER_MAX_CPS` (default 1000). Workspaces per user and
  overall are capped too (see the README configuration table).
- Raw SIPp `<exec>` actions are blocked by default because they run commands on the server.
- A test can only be as precise as the machine running it: very high rates need CPU and a
  clean network path.

## Troubleshooting

- **Nothing happens on Start:** a red message explains why (a bad field, a port already used
  by another workspace, or a scenario element that is not allowed).
- **Calls all fail with no answer:** check the SUT address and port, firewalls, and that the
  source IP exists on this machine. The ladder shows the retries.
- **No PCAP or quality data:** tcpdump needs permission (see the README, "Packet capture
  permissions").
- **UI looks out of date after an upgrade:** hard-refresh the page once.
