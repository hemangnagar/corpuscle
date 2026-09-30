# Architecture

Two halves with a hard line between them. Below the line, a deterministic core measures, gates and
signs, and never calls a model. Above it, agents investigate and propose through a logged tool
surface, and nothing they propose takes effect until a named person approves it. The signed bundle
is the only artifact that leaves the core, and it records both halves: the numbers, and every tool
call the agents made.

## Components and the trust boundary

```mermaid
flowchart TB
    subgraph AGENTS["Agent layer  (src/corpuscle_agents, the only code that calls a model)"]
        direction LR
        PLAN["Scan planner<br/>(Phase 3)"]
        TRIAGE["Triage investigator<br/>(built)"]
        AUTHOR["Report author<br/>(Phase 3)"]
        BYO["Customer's own agent<br/>via MCP"]
    end

    subgraph SURFACE["Tool surface  (corpuscle.tools; REST and MCP mirror it one to one)"]
        direction LR
        T1["list_findings<br/>get_finding"]
        T2["get_record<br/>read_document<br/>diff_documents"]
        T3["propose<br/>(the only write)"]
        LOG["every call logged:<br/>tool, args_hash, result_hash"]
    end

    subgraph CORE["Deterministic core  (src/corpuscle: no model, no network)"]
        direction LR
        ADAPT["Adapters<br/>envelope at ingest"]
        ANALYZE["Analyzers<br/>pinned detectors"]
        GATE["Finding gate<br/>policy → findings + evidence"]
        SIGN["Signer<br/>DSSE over in-toto"]
        ADAPT --> ANALYZE --> GATE --> SIGN
    end

    subgraph BUNDLE["Signed bundle  (.corpuscle/, travels with the corpus)"]
        direction LR
        REC["records.jsonl<br/>per doc, by content hash"]
        MAN["manifest.json<br/>results · findings · agent_runs"]
        DSSE["manifest.dsse.json<br/>signature over the Merkle root"]
    end

    STORE["Proposal store<br/>.corpuscle/proposals/<br/>pending → approved | rejected"]
    APPROVER(["Named approver<br/>AO · ISSM · data steward"])
    VERIFY["Offline verifier<br/>directory + bundle + public key"]
    CORPUS[("Corpus")]
    POLICY["policy/*.yaml<br/>what counts, at what severity"]

    CORPUS --> ADAPT
    POLICY --> GATE
    SIGN --> BUNDLE
    BUNDLE -. read only .-> SURFACE
    CORPUS -. read only .-> T2
    PLAN & TRIAGE & AUTHOR & BYO --> SURFACE
    T3 --> STORE
    STORE --> APPROVER
    APPROVER -- "approve: amend + re-sign<br/>assessment · narrative · remediation<br/>approved_by · agent_runs" --> SIGN
    BUNDLE --> VERIFY

    classDef agent fill:#fff4e5,stroke:#c77700,color:#000
    classDef core fill:#e8f1fb,stroke:#1d5fa8,color:#000
    classDef bundle fill:#e9f7ec,stroke:#2b7a3d,color:#000
    classDef human fill:#f3e8fb,stroke:#7a3da8,color:#000
    class PLAN,TRIAGE,AUTHOR,BYO agent
    class ADAPT,ANALYZE,GATE,SIGN,T1,T2,T3,LOG core
    class REC,MAN,DSSE,STORE bundle
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
    participant Core as Deterministic core
    participant Bundle as Signed bundle
    participant Agent as Triage investigator
    participant Tools as Tool surface (logged)
    participant Store as Proposal store
    participant Human as Named approver
    participant Verifier as Offline verifier

    Core->>Core: measure (dup.near_rate = 0.2857)
    Core->>Core: gate: DUP-002 fail, high, 4 evidence hashes
    Core->>Bundle: sign manifest (findings, results, pins, policy hash)

    Human->>Agent: corpuscle triage --finding DUP-002
    Agent->>Tools: get_finding(DUP-002)
    Tools-->>Agent: finding + evidence hashes
    Agent->>Tools: diff_documents(a, b)
    Tools-->>Agent: similarity 0.99, one word changed
    Agent->>Tools: get_record(a)
    Tools-->>Agent: envelope, metrics, flags (no text)
    Agent->>Tools: propose(real, narrative, remediation, evidence)
    Tools->>Store: proposal + agent_run (every call hashed)
    Note over Bundle: nothing has changed

    Human->>Store: corpuscle approve prop-… --approver "Dana Reyes, ISSM" --key …
    Store->>Core: checks: finding exists, gate judged it, not already approved
    Core->>Bundle: amend finding (assessment, narrative, remediation, approved_by)
    Core->>Bundle: append agent_run; re-sign
    Note over Bundle: observed, threshold, status, severity, records, Merkle root: unchanged

    Verifier->>Bundle: verify offline
    Bundle-->>Verifier: signature, records hash, Merkle root, files: PASS
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
