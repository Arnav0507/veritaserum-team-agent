# Model providers

**Meta Model API.** Muse Spark extracts proposed facts inside each private compartment. Muse Wonder coordinates over approved facts, requests a bounded `compare_repairs` tool, observes actual simulator results, and returns a proposed action. The application still authorizes disclosure and execution. Meta's documented models and endpoints: [models](https://dev.meta.ai/docs/models), [tool calling](https://dev.meta.ai/docs/tool-calling).

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

The adapter uses HTTPS chat completions with bearer authentication, a 40-second timeout, bounded responses, and redirect rejection. There is no silent fallback from live inference to reference output, no cross-provider retry, and no prompt logging. Clicking **Review my evidence** in live mode sends that person's private notes to the configured private provider. Provider retention/training and deployment terms are separate from application authorization and must be suitable before real company data is used.

Protocol references: [Fireworks chat completions](https://docs.fireworks.ai/api-reference/post-chatcompletions), [Baseten model APIs](https://docs.baseten.co/inference/model-apis/overview).

