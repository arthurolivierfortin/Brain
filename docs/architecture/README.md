# Architecture

Durable design records: system shape, module boundaries, data flow, port maps, protocol contracts.

## What goes here

- **System diagrams** — containers, processes, ports, storage
- **Module responsibility maps** — what `store.py` owns, what `gate.py` owns, where boundaries are
- **Protocol contracts** — HTTP API shapes, MCP tool signatures, adapter interfaces
- **Data flow** — ingestion path, retrieval path, decay path

## What does NOT go here

- **Why** a decision was made → [`../decisions/`](../decisions/) (ADRs)
- **How** to do something operationally → [`../runbooks/`](../runbooks/)
- **Specs** for new features → [`../specs/`](../specs/)

## Naming

`<topic>.md` — lowercase, hyphenated, no dates. Architecture docs are living documents: update in place, rely on git history for the timeline.

## Index

_(empty — first doc lands when backend architecture is written up formally)_
