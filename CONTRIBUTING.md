# Contributing

Start with the README workflow and ARCHITECTURE.md invariants. Use Python 3.11+ and a fresh database under `data/`; no dependency installation is needed. Run the full unittest command in README and `node --check web/app.js` before proposing a change.

Keep authorization in the service, not only in browser controls or model prompts. Every new workflow should test both successful collaboration and unauthorized access. Inference must occur outside database write transactions; recheck membership and revisions before committing its result. Do not send private documents to the shared provider, log prompts, or include credentials in fixtures.

Schema changes must migrate existing workspaces additively and preserve evidence/history. Add tests for stale inputs, repeated requests, and the relevant HTTP boundary. Test the browser with multiple identities, investigation switching, an interrupted request, and narrow-screen layout.

Use synthetic data in screenshots and issues. Describe the problem, changed behavior, validation, and known limitations in pull requests. Public source visibility does not grant an open-source license; discuss proposed contributions with the maintainer before contributing substantial work.
