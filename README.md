# Veritaserum

**One team agent. Individual control over private evidence.**

Veritaserum is a collaborative incident workspace for support, engineering, and operations. People investigate with private evidence workers, review the exact statements they want to share, and let a shared agent combine those statements into a proposed repair. Operations approves the action; the runtime checks permissions, evidence freshness, and the repair’s outcome before applying it.

The first integration is a checkout sandbox. This is an early local product: persistent investigations and user-authored evidence work today; production incident execution and company connectors are future work.

## Start a workspace

Python 3.11+ is required. There are no third-party runtime packages or frontend build steps.

```sh
python3 -m veritaserum.server --provider meta --prompt-key --port 8788
```

Enter your Meta API key at the hidden prompt, then open http://127.0.0.1:8788. Muse Spark handles private extraction; Muse Wonder investigates repairs through a bounded tool call. Credentials remain in process memory. See [provider setup](docs/PROVIDERS.md) for configuration and Fireworks or compatible endpoints.

For an offline evaluation without a model account:

```sh
python3 -m veritaserum.server
```

Open http://127.0.0.1:8787. Reference mode is explicitly labeled and reads `FACT key=value` markers; it does not interpret natural language. Workspace state persists in `data/veritaserum.sqlite`. Choose a separate `--db` path to keep environments independent.

## Work with your team

1. Sign in. The optional **Explore the sample workspace** section supplies synthetic accounts: `maya` / `maya-demo` (support), `eli` / `eli-demo` (engineering), `noor` / `noor-demo` (operations), and `alex` / `alex-demo` (observer).
2. As operations, choose **New investigation**, describe the goal, and select participants from your existing team. Each investigation starts with separate evidence and history. The current integration requires support, engineering, and operations roles.
3. Add private notes and select **Review my evidence**. Review each proposed statement before sharing it. Other participants cannot read your source notes or pending proposals.
4. The next-step guide shows which evidence is missing or conflicting. Once the team has aligned, **Find a repair** compares candidate actions against the checkout sandbox.
5. Operations reviews the results and selects **Approve & apply in sandbox**. Every check must pass before the configuration changes. The decision trail links approved evidence, the decision, and observed results.

You can switch investigations, edit company knowledge, update private evidence, withdraw statements, and remove access. Changed evidence or shared context invalidates pending plans. Withdrawing a statement prevents future use; it cannot erase information already shared. Unsaved note edits survive in-page updates but are discarded on logout or page reload.

Separate people should use separate browser profiles or clients: tabs in one profile share login cookies. The server binds only to localhost and is not a hosted team service yet.

## Add participants

A local administrator provisions accounts into an existing investigation. Use the same database path as the server:

```sh
python3 -m veritaserum.admin --db data/veritaserum.sqlite --room checkout --user sam --name "Sam Lee" --role engineering
```

The password is collected privately. Optionally add `--document /absolute/path/to/note.txt`. Members can see that investigation’s existing shared history, but receive their own private compartment. There is no four-person limit; roles currently remain support, engineering, operations, and viewer. Account invitations and SSO are not implemented.

## Boundary by construction

The shared model receives company knowledge and approved typed facts, not the raw private corpus. Model output cannot grant permissions. The application enforces ownership, membership, disclosure approval, bounded actions, revision checks, and atomic execution.

This is application-level isolation on a trusted server, not separate encrypted machines or information-theoretic privacy. The configured private model provider receives private notes when asked to analyze them. Public sample credentials and unencrypted local storage make this unsuitable for sensitive production data. Read the [security model](SECURITY.md) before extending or deploying it.

## Develop and verify

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -v
node --check web/app.js
```

Tests use temporary databases, synthetic inference, and local HTTP sockets; they do not spend model credits. A separate live smoke script is documented in [provider setup](docs/PROVIDERS.md).

- [Architecture and invariants](ARCHITECTURE.md)
- [Validation evidence and limitations](VALIDATION.md)
- [Contributing](CONTRIBUTING.md)
- [Product roadmap](docs/ROADMAP.md)
- [Hackathon submission notes](SUBMISSION_PLAN.md)

The backend is Python with SQLite; the interface is browser-native JavaScript and CSS. `service.py` owns authorization and workflows, `providers.py` owns inference, and `policy.py` owns the current domain’s fact schema and simulator.

## Source and ownership

Source is publicly viewable; no open-source license is granted. Public availability does not establish exclusive rights to the idea or patentability. The incident implementation was newly built for the hackathon; earlier planning and research are not represented as new implementation work.
