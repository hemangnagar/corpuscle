# Architecture

Two halves with a hard line between them. Below the line, a deterministic core measures, gates and
signs, and never calls a model. Above it, agents investigate and propose through a logged tool
surface, and nothing they propose takes effect until a named person approves it. The signed bundle
is the only artifact that leaves the core, and it records both halves: the numbers, and every tool
call the agents made.

## Layers and the trust boundary

Read left to right. The agent layer is the only code that calls a model; the core never does.
The only way anything from the top reaches the signer is through a named person, and the
agents read the bundle only through the tool surface, which logs every call.

```mermaid
flowchart LR
    subgraph AGENTS["Agent layer<br/>the only code that calls a model"]
        TRIAGE["Triage investigator<br/>(built)"]
        OTHER["Scan planner, report author,<br/>or your own agent over MCP"]
    end

    subgraph SURFACE["Tool surface<br/>every call logged: tool, args hash, result hash"]
        READ["Read from the bundle:<br/>findings, records,<br/>documents, diffs"]
        PROPOSE["propose<br/>(the only write)"]
    end

    STORE["Proposal store<br/>pending until<br/>a person decides"]
    APPROVER(["Named approver<br/>AO, ISSM,<br/>data steward"])

    subgraph CORE["Deterministic core<br/>no model, no network"]
        CORPUS[("Corpus")]
        POLICY["Policy:<br/>what counts,<br/>at what severity"]
        PIPE["Adapters<br/>Analyzers<br/>Finding gate<br/>Signer"]
    end

    subgraph BUNDLE["Signed bundle<br/>travels with the corpus"]
        FILES["records.jsonl<br/>manifest.json<br/>manifest.dsse.json"]
    end

    VERIFY["Offline verifier<br/>directory, bundle,<br/>public key"]

    TRIAGE --> READ
    OTHER --> READ
    READ -- "investigate, then" --> PROPOSE
    PROPOSE --> STORE
    STORE --> APPROVER
    APPROVER -- "approve:<br/>amend finding,<br/>append agent run,<br/>re-sign" --> PIPE
    CORPUS --> PIPE
    POLICY --> PIPE
    PIPE -- "measure,<br/>gate, sign" --> FILES
    FILES --> VERIFY
    FILES -. "read only" .-> READ

    classDef agent fill:#fff3e0,stroke:#e65100,color:#000
    classDef surface fill:#f1f8e9,stroke:#33691e,color:#000
    classDef core fill:#e3f2fd,stroke:#0d47a1,color:#000
    classDef bundle fill:#ede7f6,stroke:#4527a0,color:#000
    classDef human fill:#fce4ec,stroke:#880e4f,color:#000
    class TRIAGE,OTHER agent
    class READ,PROPOSE,STORE surface
    class PIPE,CORPUS,POLICY core
    class FILES,VERIFY bundle
    class APPROVER human
```

What the boundary guarantees:

| The agent can | The agent cannot |
|---|---|
| Read any finding, record and document | Change an observed value, threshold, status or severity |
| Diff documents, follow evidence, decide what to look at | Write to the bundle |
| Propose an assessment, narrative and remediation | Approve its own proposal |
| Be any model, including the customer's own agent over MCP | Act unlogged: every call is hashed into `agent_runs` |

## The triage flow, end to end

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Triage investigator
    participant Tools as Tool surface
    participant Store as Proposal store
    participant Human as Named approver
    participant Core as Deterministic core
    participant Bundle as Signed bundle

    Core->>Core: measure (near duplicate rate 0.2857)
    Core->>Core: gate raises DUP-002, fail, high, four evidence hashes
    Core->>Bundle: sign the manifest

    Human->>Agent: corpuscle triage --finding DUP-002
    Agent->>Tools: get_finding(DUP-002)
    Tools-->>Agent: finding with evidence hashes
    Agent->>Tools: diff_documents(a, b)
    Tools-->>Agent: similarity 0.99, one word changed
    Agent->>Tools: get_record(a)
    Tools-->>Agent: envelope, metrics, flags (never text)
    Agent->>Tools: propose(real, narrative, remediation, evidence)
    Tools->>Store: proposal plus agent run, every call hashed
    Note over Bundle: unchanged so far

    Human->>Store: corpuscle approve prop-xxx --approver "Dana Reyes, ISSM"
    Store->>Core: check the finding exists, was gated, has no prior approval
    Core->>Bundle: amend the finding with assessment, narrative, remediation, approver
    Core->>Bundle: append the agent run and re-sign
    Note over Core,Bundle: observed value, threshold, status, severity, records and Merkle root unchanged

    Human->>Bundle: corpuscle verify (offline)
    Bundle-->>Human: signature, records hash, Merkle root, files all pass
```

## Why it is built this way

- **Agents propose, the core disposes.** A model's judgement is not reproducible or signable. Its
  investigation is valuable, so it is recorded and signed as what it is: an agent run with a
  conclusion, approved by a person, beside numbers that did not move.
- **The objection this answers.** "The model will take care of data quality." Yes: bring the model.
  The question the authorizing official asks afterwards is what the model looked at, what it
  concluded, and who agreed. The manifest answers all three.
- **Bring your own agent.** The tool surface is the product boundary, not our agent. A customer's
  agent over MCP gets the same six calls, the same log, and the same approval gate.
