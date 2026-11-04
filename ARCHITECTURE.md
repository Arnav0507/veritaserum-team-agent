# Veritaserum: joint work across private boundaries

Status: implementation plan, November 4, 2026. Supersedes the reservation workflow in PRODUCT_BRIEF.md. Existing research and the earlier brief are retained as historical inputs.

## Product and acceptance contract

A team has one persistent incident room and a shared coordinator with company runbooks. Each member has a private evidence compartment and a private worker. The coordinator requests bounded facts; members inspect and release precise statements to the whole room. The shared agent combines these statements, proposes a repair, and an authorized operator executes it against a checkout simulator. All participants see the same durable result and provenance.

The initial domain is intentionally bounded: an incident affecting EU wallet checkout. Support knows the affected segment, engineering knows the repair, and operations knows whether rollback is safe. Neither individual evidence nor public runbooks alone suffice. Success is a verified repair using all three disclosures, with private customer names, source notes, and deployment credentials absent from shared state and shared-model requests.

Acceptance: three independently authenticated users; durable room state; private evidence visible only to its owner; explicit release of an immutable exact statement; shared planning over released evidence; operator-only, version-checked execution; executable regression checks; auditable graph; stale plans rejected after disclosure withdrawal or membership change; repeat execution produces one effect. Reference mode must be explicitly labeled. Live inference must never silently fall back to scripted output.

## Trust model

Trusted: server, database host, authenticated administrator provisioning accounts, approved inference provider for the context sent to it, and the bounded simulator implementation. Untrusted: browsers, room members outside their own grants, private document contents, model outputs, client actor IDs, and tool requests.

This is application-level compartmentalization, not encryption against the server operator, confidential computing, or protection from a malicious database administrator. Private evidence is stored locally in SQLite and may be sent to a configured private inference provider only when the owner explicitly invokes that worker. Disclosures deliberately reveal information and may permit inference. Already disclosed facts cannot be made unknown by withdrawal. Response timing and fact existence are not covered by a noninterference claim.

Security invariant: raw private documents and private worker outputs never enter the shared coordinator context. The only bridge is a server-validated, owner-approved, typed claim. No generated free-text summaries cross automatically. Human approval is a declassification decision, not evidence that a claim is true.

## Architecture and data

Browser → authenticated HTTP boundary → domain service → SQLite transaction. Domain service invokes stateless private/coordinator model adapters outside transactions. A tool gateway validates action scope, operator role, current room revision, evidence dependencies, and simulator revision in one transaction before applying an effect.

SQLite WAL and BEGIN IMMEDIATE serialize mutations for a single-host prototype. Each request uses a separate connection; foreign keys and constraints reinforce application checks. Persistent tables: users; room memberships; private documents; private proposals; approved disclosures; shared events; plans; simulator state; expiring sessions. All compartment queries bind room AND authenticated owner. Model output is never used as SQL, HTML, shell code, or a credential.

Shared state is a materialized view plus an append-only event history. Every shared mutation advances the room revision. Plans pin that revision and the current simulator version. History records explicitly released information, action results, and authenticated actors, but no private proposal IDs/documents. The graph connects released evidence → plan → verified execution. These are execution records, not hidden model reasoning.

Concurrent inference uses snapshot/compare-and-swap: capture authorized input, release the database transaction, perform inference, then recheck membership, document version (private) or room revision (shared) before storing output. Stale outputs are discarded. Execution is atomic and idempotent by plan ID; a repeated request returns the prior result. Revocation prevents subsequent reads and mutation, including post-inference completion. Polling reads reauthenticate each time; there is no unscoped broadcast channel.

## Agent boundaries

The coordinator delegates requests by required role, not by borrowing a participant's credentials. Private workers are stateless calls with only that owner's documents, a bounded task, and an output schema. Model output must match an allowed fact key/value and cite an owned document. It remains a private proposal until the person approves the exact rendered claim. Arbitrary strings and model tool calls are rejected.

The shared model receives public runbooks and active released claims, never a union of private histories. It returns a bounded candidate action. The deterministic policy engine checks evidence completeness and contradictory claims and evaluates permitted actions. The model can select an eligible action or abstain; it cannot broaden permissions. Public conversational messages are explicitly room-visible and do not satisfy evidence requirements.

Reference mode is a deterministic agent implementation for reproducible engineering tests and a usable local demo. Live mode uses an OpenAI-compatible chat-completions adapter, separately configurable for private and shared inference. Fireworks and Baseten provide these interfaces; operator-supplied model IDs avoid assuming hackathon access. External calls have timeouts, size caps, no redirects, no prompt/body logging, and fail closed. No fine-tuning or automatic cross-provider retry with private data.

## Execution and meaningful verification

Only three typed actions exist: disable_fast_checkout, rollback, restart. A pure checkout simulator models the actual regression and schema compatibility. Execution changes simulator configuration and runs independent scenario expectations for EU wallet, US card, EU card, and data compatibility. Verification is computed each time, never a prerecorded success flag. The state commits only if checks pass. No arbitrary generated code runs on the host.

Test layers: pure policy and simulator behavior; tenant/owner authorization; exact disclosure and schema checks; provider input isolation; prompt injection; stale model completion; membership revocation; concurrent execution; durable restart; HTTP sessions/CSRF/size limits; full three-user workflow; browser accessibility/layout smoke. Tests include negative and successful outcomes. Tests do not establish a general privacy proof or model quality benchmark.

## Increment plan

1. Domain and security kernel: schema, identity, ownership, proposals, disclosure, revisions. Test cross-owner and cross-room denial.
2. Joint workflow: delegation, planning, bounded execution, durable provenance, reference provider. Verify successful multi-person repair and stale/conflicting evidence.
3. HTTP and UI: authenticated sessions, CSRF and origin checks, private/public visual separation, synchronized room, exact approval, interactive decision graph.
4. Provider integration and adversarial tests: live adapters, malformed/hostile model output, post-inference revocation, racing execution, restart, and browser QA.
5. Handoff: reproducible commands, test evidence, operational limitations, and next milestones. No publishing in this build.

## Operations and product evolution

Local deployment binds loopback; demo accounts are synthetic and conspicuously labeled. Sessions are random, hashed in the database, expiring, and HttpOnly/SameSite cookies; mutating requests require a session CSRF token and matching Origin. Real deployment requires TLS/Secure cookies, SSO, encrypted storage/backups, durable job queues, tenant-aware operational tooling, quotas, independent security review, and tested restore procedures. This prototype is not production hardened.

The server has bounded request bodies and model responses, login throttling, and safe error responses. Model failures preserve private drafts and shared evidence; no half-executed operation occurs. Logs record HTTP status without request payloads or secrets. Provider configuration errors are startup failures. Keep credentials in environment variables, never tracked files.

Beyond this milestone: connectors with per-user grants; department compartments; asynchronous jobs/cancellation; Postgres row-level defense and distributed workers; explicit audience changes; policy-owned release templates; calibrated leakage and utility evaluations; independently labeled conflict cases; SSO and hosted deployment. n collaborators means arbitrary membership rows, not one global prompt containing everyone's data. Membership growth does not increase authority.

## Originality and ownership

This implementation is developed locally for this project. No exclusivity, patentability, or freedom-to-operate claim is made. Shared agents, access-controlled memory, capability gateways, and declassification have prior art (see COLLABORATION_OPPORTUNITY_RESEARCH.md). Product differentiation is the measured ability to complete useful joint work across boundaries. No open-source license is granted by this repository; dependencies retain their own licenses. Hackathon public-submission requirements must be reconciled separately before publication.
