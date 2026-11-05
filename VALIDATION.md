# Validation record

## Scope

Local single-host prototype with synthetic checkout evidence. Tests exercise the deterministic reference provider and mock live-provider transport. The tested outcome is successful joint work across enforced application boundaries, not a measured LLM benchmark or a production security certification.

## Completed evidence

Automated suite includes 54 tests after the investigation and evidence lifecycle changes. JavaScript syntax and Python compilation checks also passed. Tests run with ResourceWarning promoted to an error.

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

## Product workflow verification

A new investigation was created through the browser, with private notes authored separately as support, engineering, and operations. Each person reviewed and released their statement; the shared agent proposed a repair and operations applied it with all four checks passing. Source-note visibility, withdrawal/re-sharing, and retention of unsaved private edits during shared updates were checked. This run used the deterministic reference provider.

The updated interface was inspected at 1440px and 390px with no horizontal overflow. Product screenshot: `artifacts/product_workspace.png`.

## Shared-context receipt and boundary challenge

Successful planning now records the application context passed to the shared provider before inference. The UI shows it on the plan; older plans explicitly lack receipts. The receipt is not the complete wire request, system instructions, tool transcript, or hidden reasoning. A new live Meta coordinator run with previously approved synthetic evidence produced a receipt and passed all execution checks; the inspector was verified in the browser.

`tests/test_boundary_receipts.py` runs two fresh reference-provider workspaces with different fake private credentials and an instruction to reveal them. It checks exact equality between the receipt and captured shared-provider input, exclusion of the fake credential from the shared snapshot and another participant's private view, and identical normalized shared inputs across both worlds. It also verifies withdrawal rejects execution and re-approval plus replanning permits successful repair. This is a bounded deterministic regression test, not a live-model prompt-injection benchmark or formal noninterference proof.

## Conversational collaboration

Contributor-created team chats now support team messages that trigger coordination, role-scoped requests visible in private workspaces, and persisted owner-scoped private conversations with a model reply. Private user messages become versioned evidence; extraction proposes statements separately and still requires owner approval. Three additional tests cover contributor creation/delegation, private conversation isolation, viewer rejection, and revocation during a private reply. Chat remains scoped to the checkout domain. Each private send consumes one of the existing 20 evidence-note slots; it makes a conversational model call followed by a separate extraction request in the UI.

Live browser verification: a team message created role-specific private requests. Muse Spark replied conversationally to an operations message containing a fake token, then extracted a rollback statement. The statement remained pending approval and the shared claims remained empty. The new chat HTTP routes also passed CSRF and cross-user isolation checks.
