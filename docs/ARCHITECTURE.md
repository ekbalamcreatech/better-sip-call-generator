# Architecture and process flow

A high-level look at how A Better SIP Call Generator works. For day-to-day use see the
[User Guide](USER_GUIDE.md); for setup see the [README](../README.md).

## The idea in one paragraph

You describe what calls should look like (who calls whom, how fast, for how long, with
which media and security options). The app turns that into a SIPp scenario and a
schedule, starts SIPp for you, records the traffic, and turns SIPp's output into
counters, a ladder diagram, call-quality numbers, a PCAP and a PDF report. SIPp does the
SIP; this project is the control panel around it.

## Components

```mermaid
flowchart LR
    subgraph Browser["Browser (plain JavaScript, no build step)"]
        UI["Single-page UI<br/>workspaces, scripts, intervals,<br/>ladder, stats, quality, PDF"]
    end

    subgraph Server["FastAPI server (Python)"]
        MW["Middleware<br/>login, cross-site check,<br/>security headers"]
        API["Routes<br/>workspaces, library, media,<br/>quality, stir, users, llm"]
        VAL["Validation<br/>request models +<br/>scenario guard"]
        RUN["Workspace runner<br/>intervals, number plan,<br/>process control"]
        ENG["Engines<br/>auth, STIR/SHAKEN, RTP sender,<br/>pcap reader, MOS, LLM client"]
        STO[("JSON files<br/>users, SUTs, scenarios,<br/>templates, STIR keys")]
    end

    subgraph Host["Same machine, separate programs"]
        SIPP["SIPp<br/>(one process per script per interval)"]
        TCPD["tcpdump<br/>(one per workspace)"]
        RUND[("run/ directory<br/>scenario XML, number CSVs,<br/>SIPp message logs and stats, PCAP")]
    end

    SUT["System under test<br/>(SBC, PBX, carrier lab...)"]
    AI["AI service<br/>(optional, admin-chosen)"]

    UI <--> MW --> API
    API --> VAL --> RUN
    API --> ENG
    API <--> STO
    RUN --> SIPP
    RUN --> TCPD
    SIPP <--> SUT
    SIPP --> RUND
    TCPD --> RUND
    RUND --> API
    ENG -. optional .-> AI
```

## What happens when you run a test

```mermaid
flowchart TD
    A["Log in"] --> B["Claim a workspace<br/>TX = caller (SIPp UAC), RX = receiver (SIPp UAS)"]
    B --> C["Configure scripts<br/>target (SUT), source IP/port, % share,<br/>number plan, media, STIR, auth"]
    C --> D{"Need a scenario?"}
    D -->|"Describe it in words"| E["AI generates SIPp XML<br/>(optional)"]
    D -->|"Load or paste"| F["Saved scenario / own XML"]
    E --> G["Scenario in the script"]
    F --> G
    G --> H["Set intervals<br/>duration and calls per second per script,<br/>0 CPS = pause"]
    H --> I["Press Start"]

    I --> J["Validate<br/>every field, port conflicts,<br/>scenario XML allowlist"]
    J -->|"rejected"| X["Clear error, nothing runs"]
    J -->|"ok"| K["Start tcpdump capture"]
    K --> L

    subgraph L["For each interval, in order"]
        L1["Calls = CPS x duration x script share"]
        L2["Write number CSV for this script<br/>continuing where the last interval stopped"]
        L3["Start SIPp with -r rate and -m call count"]
        L4["Wait for the interval, then let in-flight calls finish<br/>(retransmissions, timeouts)"]
        L5["Read SIPp counters, add to run totals,<br/>advance the number-plan position"]
        L1 --> L2 --> L3 --> L4 --> L5
    end

    L --> M["Stop capture, finish"]
    M --> N["Results"]
    N --> N1["Counters: sent, completed, failed,<br/>in progress, retransmits"]
    N --> N2["SIP ladder per call<br/>(retries shown)"]
    N --> N3["SIP statistics and call quality<br/>(RTP, loss, jitter, MOS)"]
    N --> N4["PCAP download and PDF report"]
```

## Timeline of one call test (sequence)

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant S as Server
    participant P as SIPp
    participant T as tcpdump
    participant D as System under test

    U->>S: Start (scripts + intervals)
    S->>S: Validate fields, ports, scenario XML
    S->>T: Start capture
    loop each interval
        S->>P: Launch with rate, call count, number CSV
        P->>D: INVITE (and retries if unanswered)
        D-->>P: Responses (or silence)
        U->>S: Poll status every second
        S->>P: (reads SIPp stats file)
        S-->>U: sent / completed / failed / in progress
        P-->>S: Exits when its calls are done
        S->>S: Add counters to totals, advance numbers
    end
    S->>T: Stop capture
    U->>S: Open ladder / quality / PCAP / PDF
    S-->>U: Built from SIPp logs and the capture
```

## Key behaviors worth knowing

- **The schedule decides how many calls run.** Calls per interval = CPS x duration
  (rounded to the nearest whole call, minimum 1), split by each script's percentage. The
  number plan only chooses *which numbers* those calls use; it never changes how many.
- **Numbering continues.** A pause or a later interval picks up the number plan where the
  previous interval left off. (SIP Call-IDs are per SIPp process and restart each
  interval; the dialed numbers do not.)
- **Unanswered calls are not new calls.** SIPp retransmits an unanswered INVITE several
  times. The ladder shows those retries inside one call, and the counters report them
  separately as retransmits.
- **Counters are SIPp's own.** A call still in flight is "in progress", never "failed".
- **Each script uses its own files.** Scenario XML, number CSV and stats file names include
  the workspace and script, so scripts running at the same time cannot interfere.
- **Cleanup is automatic.** SIPp and tcpdump are tied to the server process. If the server
  stops or crashes, they stop too, and a startup check removes anything left behind.

## Security layers

```mermaid
flowchart LR
    R["Request"] --> L1["Login required<br/>PBKDF2 passwords,<br/>session expiry"]
    L1 --> L2["Same-origin check<br/>(CSRF) + security headers"]
    L2 --> L3["Role and ownership<br/>users see only their<br/>own workspaces"]
    L3 --> L4["Field validation<br/>hosts, ports, numbers,<br/>file names, credentials"]
    L4 --> L5["Scenario guard<br/>XML parsed against<br/>an allowlist; no exec"]
    L5 --> L6["SIPp launched with an<br/>argument list, never a shell"]
```

Details and deployment advice are in [SECURITY.md](../SECURITY.md).

## Where things live

| Path | What it holds |
|---|---|
| `main.py` | App setup, middleware, startup and shutdown |
| `routes/` | API endpoints |
| `workspaces/` | Starting and stopping SIPp, intervals, capture, ladder data, RTP sender |
| `engines/` | Scenario guard, login, STIR/SHAKEN, PCAP reading, MOS, AI client, number plans |
| `models.py` | Request models and all input validation rules |
| `storage/` | JSON-file storage code (the data files themselves are git-ignored) |
| `static/` | The web UI |
| `scenarios/`, `audio/` | Sample scenarios and reference audio |
| `run/` | Temporary files from running tests (private, git-ignored) |
