# Validation record

## Scope

Local single-host prototype with synthetic checkout evidence. Tests exercise the deterministic reference provider and mock live-provider transport. The tested outcome is successful joint work across enforced application boundaries, not a measured LLM benchmark or a production security certification.

## Completed evidence

Automated suite includes 39 tests after the live Meta protocol correction. JavaScript syntax and Python compilation checks also passed. Tests run with ResourceWarning promoted to an error.

- Domain tests: three-person successful repair; private notes and source IDs absent from shared responses/model context; unapproved drafts stay private; cross-owner and cross-room denial; contributor/viewer restrictions; stale source revisions; withdrawal; revocation during inference; shared context changes during inference; racing executions yield one effect; durable restart; malformed/hostile output rejection; failed simulations do not commit; conflicting evidence cannot authorize execution.
- HTTP tests: three independent authenticated sessions complete the joint workflow; cookie flags; unauthenticated access; CSRF/origin; actor spoofing; private response scope; cache prevention; host rebinding; static-file traversal/allowlist; body limits; logout.
- Provider tests: request context serialized without credentials; HTTPS and no redirects; bounded responses; invalid responses do not echo secrets; misconfigured live mode fails instead of switching to reference mode.
- Additional membership test: a fifth contributor has a distinct private compartment and can introduce a conflict that requires resolution.
- Meta tool-loop tests: model requests a bounded experiment, receives actual pass/fail outcomes for three candidate repairs, and proposes a final decision. Unknown tools and extra tool arguments fail closed. Live demo fixtures contain prose rather than reference-mode fact markers. These are mocked transport tests, not evidence of a successful live Meta run.
- Browser walkthrough: Maya, Eli, and Noor analyzed and approved their respective statements through the actual UI; Noor coordinated and executed the repair; all four checkout checks displayed PASS; raw private notes were not displayed to other seats. The browser walkthrough changed identities sequentially; independent simultaneous sessions are covered at the HTTP layer.
- Responsive inspection: narrow default viewport rendered the stacked layout; 1440px inspection rendered the three-column layout with no horizontal overflow. Final screenshot is stored locally in `artifacts/verified_recovery.png`.

## Limitations

Live Meta validation succeeded on November 4. All three Muse Spark 1.3 private workers extracted the expected facts from natural prose (approximately 5.50, 6.73, and 5.03 seconds respectively). Muse Wonder 1.0 completed its tool loop in 7.02 seconds; the resulting operator-authorized repair committed with all four checks passing. The shared snapshot contained none of the private fixture markers. These timings are single-run observations, not latency benchmarks.

The initial coordinator call failed because the adapter forced a named tool choice; Meta supports only `tool_choice: "auto"`. After correcting the request, the coordinator was retried using the previously approved evidence. The successful live path therefore spans the original private-worker calls and the corrected coordinator retry, rather than one uninterrupted fresh run. The runtime abstains if the model chooses not to call the experiment tool.

The reference worker parses explicit fact lines, while the live adapter asks a model to extract the same bounded schema. The policy and simulator are intentionally narrow. A larger company corpus, real connectors, arbitrary tasks, independent penetration testing, performance/load tests, and model extraction accuracy have not been validated. A recorded three-minute video remains a submission deliverable.

## Regression command

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -v
node --check web/app.js
```
