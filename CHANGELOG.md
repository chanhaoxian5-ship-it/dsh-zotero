# Changelog

## 0.2.0

- Add a guarded Python adapter while preserving the upstream helper byte-for-byte.
- Search DOI URLs and normalized DOIs across a fully paginated library; return DOI and collection keys.
- Add read-only `plan-import` and `duplicates` commands; skip existing DOI matches and repeated input records.
- Block ambiguous title/version identities and incomplete or changing library scans.
- Persist pending imports before POST, serialize plugin imports and verify newly created keys before reporting success.
- Recover from lost responses without resubmitting; retain unresolved/partial imports across process restarts.
- Return compact selected-target data and optionally check an expected collection ID.

Guarded writes currently support My Library only. Group-library reads are supported. Existing collection memberships, duplicates and Word citations are not modified. Write failures are tested against isolated HTTP fixtures; the real-library checks remain read-only.

## 0.1.0

- Register a native DSH `zotero` skill through a bundle patch and skill provider.
- Preserve OpenAI Zotero 0.1.2 and its Python helper with source attribution.
- Add a Node launcher for Python selection, UTF-8 output and safe argument forwarding.
- Adapt the instructions for Windows PowerShell, attachment reading and import deduplication.
- Add public installation instructions and Windows/Linux CI.

Tested with the DSH 0.2.1-rc.5 skill registry and Zotero Desktop 10.0.6 on Windows. Live model-driven chat and write/import flows have not been acceptance-tested for this adaptation.
