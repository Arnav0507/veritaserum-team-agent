# Veritaserum

A shared incident agent with private evidence workers and explicit disclosure approval.

**Working local prototype, using synthetic data.** Three people can complete a checkout repair while keeping their raw notes out of the shared context. The default agent is a clearly labeled deterministic reference implementation. The live Meta path has also been exercised successfully: Muse Spark 1.3 private workers and Muse Wonder 1.0 tool planning led to a verified repair. See [validation details and limitations](VALIDATION.md).

## Run

Python 3.11+; no third-party packages or build step required.

```sh
python3 -m veritaserum.server
```

Open http://127.0.0.1:8787. The server binds loopback only. Local state persists in `data/veritaserum.sqlite` (ignored by Git). To run a fresh demo without deleting history:

```sh
python3 -m veritaserum.server --port 8788 --db data/fresh-demo.sqlite
```

Demo accounts: `maya` / `maya-demo` (support), `eli` / `eli-demo` (engineering), `noor` / `noor-demo` (operations), `alex` / `alex-demo` (observer). These intentionally public passwords are for synthetic localhost use only. Different people should use separate browser profiles; tabs in the same profile share login cookies.

## Walkthrough

1. Sign in as Maya. Click **Coordinate next step** to request the missing evidence. Open the private customer note, then **Ask my private agent**. A private proposal appears; no disclosure has happened yet.
2. Approve the exact affected-segment statement. Sign out and enter as Eli. The shared statement is visible; Maya's source note is not.
3. Eli analyzes the private engineering note and approves its repair statement.
4. Noor analyzes the private deployment note and releases the rollback constraint. Click **Coordinate next step**, then **Approve & verify repair**.
5. The simulator changes configuration only after EU wallet, US card, EU card, and schema-compatibility checks pass. Click the decision-trail nodes to inspect the released evidence, dependencies, and runtime result.
6. For a boundary demonstration, create another pending plan and withdraw a contributing statement. The pending plan becomes stale and cannot execute. Withdrawal prevents future use, but does not erase shared history.

The reference worker parses explicit `FACT key=value` lines in synthetic private documents. Edit a private note to `FACT repair=restart` as Eli to observe a failed repair: the simulator rejects the result and preserves its earlier configuration. Use a fresh database for a clean degraded starting state.

Notes posted to the room are room-visible conversation; they invalidate pending plans, but do not replace the typed evidence requirements. This milestone is a bounded incident workflow, not a general coding assistant or company-wide search product.

## Architecture

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the threat model, invariants, incremental plan, trust assumptions, concurrency design, operations plan, and production milestones.

- `veritaserum/service.py`: ownership checks, private proposals, explicit disclosures, coordinator, versioned execution.
- `veritaserum/policy.py`: bounded fact/action vocabulary and executable checkout simulation.
- `veritaserum/providers.py`: stateless reference and live model adapters; private/shared contexts are separate calls.
- `veritaserum/store.py`: SQLite schema, transactions, password hashing, synthetic fixtures.
- `veritaserum/server.py`: loopback HTTP, sessions, CSRF, host/origin checks, body limits, static allowlist.
- `web/`: responsive interface with private workspace, shared agent, and inspectable decision trail.
- `tests/`: successful collaboration, adversarial boundaries, concurrency, transport, and HTTP integration tests.

Private agents are isolated by application authorization and context construction. They are not separate VMs or separate encrypted databases. The trusted server can read stored data. No arbitrary shell, generated code, production credentials, or autonomous external side effects are exposed.

## More collaborators

There is no four-user limit in the membership model. A trusted local administrator can provision another participant:

```sh
python3 -m veritaserum.admin --user sam --name "Sam Lee" --role engineering
```

The command prompts for a password without echoing or passing it in argv. Optionally supply `--document /absolute/path/to/private-note.txt`. Choose **Another provisioned participant** at login. Roles currently remain support, engineering, operations, and viewer. Additional evidence can conflict; the coordinator refuses to choose an action until the owners resolve the conflict. New room members can see the room's existing shared history. Operations can revoke room membership from the UI.

## Live inference

**Primary hackathon path: Meta Model API.** Muse Spark extracts proposed facts inside each private compartment. Muse Wonder coordinates over approved facts, requests a bounded `compare_repairs` tool, observes actual simulator results, and returns a proposed action. The application still authorizes disclosure and execution. Meta's documented models and endpoints: [models](https://dev.meta.ai/docs/models), [tool calling](https://dev.meta.ai/docs/tool-calling).

```sh
python3 -m veritaserum.server --provider meta --prompt-key --port 8788 --db data/muse-demo.sqlite
```

Enter the Meta API key at the hidden prompt. Alternatively set `MODEL_API_KEY` securely and omit `--prompt-key`. Defaults are `--private-model muse-spark-1.3` and `--shared-model muse-wonder-1.0`. A newly seeded live database contains prose evidence without reference-mode `FACT` lines. Existing databases are never silently rewritten. The coordinator makes two model requests around one read-only tool call; the later operator-approved execution separately revalidates and commits the result. Tool-call count and token output are bounded. Account model access and credits must be confirmed with a real run.

To use Spark for both roles, add `--shared-model muse-spark-1.3`. Run `python3 scripts/live_smoke.py --port 8788` to exercise the synthetic three-person workflow against the running server; this spends model credits and approves only the known synthetic fixture statements. Add `--coordinate-only` to reuse already-approved evidence. The script never prints source documents, session tokens, or API keys.

Fireworks is an optional fallback. Start it with your account-enabled **Meta** model ID to retain Meta-model usage; the API key is read privately from the terminal and is not stored:

```sh
python3 -m veritaserum.server --provider fireworks --model YOUR_FIREWORKS_MODEL_ID --prompt-key --port 8788 --db data/live-demo.sqlite
```

Alternatively set `FIREWORKS_API_KEY` and `FIREWORKS_MODEL` securely in the process environment, then run `python3 -m veritaserum.server --provider fireworks`. Both agent roles use separate stateless requests. The default reference server remains available for reproducible testing.

Private and shared providers are configured independently using environment variables. Configuration is not read from `.env` files automatically. Keep credentials out of Git, shell history, screenshots, and chat.

For each prefix (`PRIVATE` and `SHARED`), configure:

```text
PRIVATE_MODE=live
PRIVATE_ENDPOINT=https://api.fireworks.ai/inference/v1/chat/completions
PRIVATE_MODEL=<model ID enabled for your account>
PRIVATE_API_KEY=<set securely in the process environment>

SHARED_MODE=live
SHARED_ENDPOINT=https://inference.baseten.co/v1/chat/completions
SHARED_MODEL=<model ID enabled for your account>
SHARED_API_KEY=<set securely in the process environment>
```

Use either provider for both roles, or a compatible endpoint for an available Meta model. Fireworks is useful for private workers and the coordinator; fine-tuning is not needed for the security boundary. Start with one provider and measure quality before adding routing. Provider model IDs and hackathon access must be verified in the actual account. The code requires JSON output, validates it, and fails closed on malformed output; supported model capabilities vary.

The adapter uses HTTPS chat completions with bearer authentication, a 40-second timeout, bounded responses, and redirect rejection. There is no silent fallback from live inference to reference output, no cross-provider retry, and no prompt logging. Clicking **Ask my private agent** in live mode sends that person's private notes to the configured private provider. Provider retention/training and deployment terms are separate from application authorization and must be suitable before real company data is used.

Protocol references: [Fireworks chat completions](https://docs.fireworks.ai/api-reference/post-chatcompletions), [Baseten model APIs](https://docs.baseten.co/inference/model-apis/overview).

## Verify

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -v
node --check web/app.js
```

The HTTP tests need permission to bind an ephemeral loopback socket. Tests use temporary databases and synthetic inference; they make no external provider calls. [VALIDATION.md](VALIDATION.md) records the completed checks and limitations.

## Security scope and next milestones

What is enforced: authenticated membership, per-owner private reads, exact owner-approved releases, typed model output, role-scoped actions, stale-plan rejection, membership rechecks after inference, atomic simulator commits, and replay-safe execution by plan ID.

What remains: SSO, TLS hosting, storage encryption/backups, asynchronous durable jobs, robust service quotas, real company connectors, dynamic policy administration, richer task domains, independent security assessment, and live-model quality/leakage evaluation. The prototype does not prove information-theoretic privacy: owners can intentionally release sensitive facts, approved facts can support inference, and a server administrator is trusted.

Public source availability is separate from granting an open-source license; no open-source license is granted here. This does not establish exclusive rights to the concept or patentability. See the [originality discussion](ARCHITECTURE.md#originality-and-ownership). This incident prototype was newly implemented for the hackathon; earlier Veritaserum planning/research is not represented as new implementation work.
