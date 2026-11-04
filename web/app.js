'use strict';
const $ = id => document.getElementById(id);
let auth = null, state = null, privateState = null, busy = false, polling = false, generation = 0;
const labels = {affected_segment: 'Support evidence', repair: 'Engineering evidence', rollback_safe: 'Operations evidence'};
function el(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
function button(text, fn, cls = 'secondary') { const b = el('button', text, cls); b.type = 'button'; b.onclick = fn; return b; }
function notice(text, error = false) { $('notice').textContent = text; $('notice').className = error ? 'error' : ''; }
async function api(path, body) {
  const options = {credentials: 'same-origin', cache: 'no-store', headers: {}};
  if (auth) options.headers['X-Expected-User'] = auth.user;
  if (body !== undefined) { options.method = 'POST'; options.headers = {...options.headers, 'Content-Type': 'application/json', 'X-CSRF-Token': auth?.csrf || ''}; options.body = JSON.stringify(body); }
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || 'Request failed'); error.status = response.status; throw error; }
  return result;
}
const endpoint = op => `/api/rooms/checkout/${op}`;
function clearSession() {
  generation++; auth = state = privateState = null;
  for (const id of ['private-documents', 'proposals', 'claims', 'messages', 'graph', 'activity', 'members', 'plan', 'node-detail']) $(id).replaceChildren();
  $('workspace').hidden = true; $('login-view').hidden = false;
}
async function refresh(force = false) {
  if (!auth || polling) return;
  polling = true; const epoch = generation;
  try {
    const identity = await api('/api/me');
    if (epoch !== generation) return;
    if (identity.user !== auth.user || identity.csrf !== auth.csrf) {
      clearSession(); $('login-error').textContent = 'The browser session changed in another tab. Sign in again.'; return;
    }
    const [next, priv] = await Promise.all([api(endpoint('state')), api(endpoint('private'))]);
    if (epoch !== generation) return;
    const sharedChanged = force || JSON.stringify(next) !== JSON.stringify(state);
    const privateChanged = force || JSON.stringify(priv) !== JSON.stringify(privateState);
    state = next; privateState = priv;
    if (sharedChanged) renderShared();
    if (privateChanged) renderPrivate();
  } catch (e) {
    if (epoch !== generation) return;
    if (e.status === 401 || e.status === 403) { clearSession(); $('login-error').textContent = e.message; }
    else notice(e.message, true);
  } finally { polling = false; }
}
async function act(op, body = {}, success = '') {
  if (busy) return;
  busy = true; notice('Working…');
  document.querySelectorAll('#workspace button').forEach(b => b.disabled = true);
  try {
    const result = await api(endpoint(op), body);
    notice(result.status === 'needs_evidence' ? 'Requests sent to the relevant private workspaces. Each owner decides what to share.' :
      result.status === 'abstained' ? 'The coordinator abstained. No action was proposed.' :
      result.committed === false ? 'Verification failed. The configuration was not changed.' : success || 'Done.');
    return result;
  } catch (e) { notice(e.message, true); }
  finally { busy = false; document.querySelectorAll('#workspace button').forEach(b => b.disabled = false); await refresh(true); }
}
function renderPrivate() {
  const docs = $('private-documents'); docs.replaceChildren();
  for (const doc of privateState.documents) {
    const box = el('details', undefined, 'doc');
    box.append(el('summary', doc.title), el('pre', doc.body));
    const edit = el('details'); edit.append(el('summary', 'Edit my private evidence'));
    const textarea = el('textarea'); textarea.value = doc.body; textarea.setAttribute('aria-label', `Edit ${doc.title}`);
    edit.append(textarea, button('Save private revision', () => act('document', {document_id: doc.id, body: textarea.value, version: doc.version}, 'Private evidence updated. Any earlier disclosure from it is now withdrawn.')));
    box.append(edit); docs.append(box);
  }
  if (!privateState.documents.length) docs.append(el('p', 'No private sources assigned to this seat.', 'muted'));
  $('analyze').disabled = state.role === 'viewer' || busy;
  $('private-mode').textContent = state.providers.private.startsWith('live') ? 'This sends your private notes to the configured inference provider. Results remain private until you approve.' : 'Reference worker · extracts explicit fact lines from these synthetic notes. No external inference.';
  const proposals = $('proposals'); proposals.replaceChildren();
  if (privateState.proposals.length) proposals.append(el('h3', 'Review before sharing'));
  for (const p of privateState.proposals) {
    const box = el('article', undefined, 'proposal');
    box.append(el('span', p.released ? 'SHARED WITH ROOM' : p.disclosure_id ? 'WITHDRAWN' : 'PRIVATE PROPOSAL', 'eyebrow'),
      el('p', p.statement, 'exact'), el('p', `Private source: ${p.source_id} · revision ${p.source_version}`, 'hint'));
    if (!p.disclosure_id) {
      box.append(el('p', 'Sharing releases this exact statement and your identity to all room members. Confirm it is accurate and appropriate to disclose.', 'hint'));
      const approve = button('Approve & share exact statement', () => act('disclose', {proposal_id: p.id}, 'Only the approved statement was shared. Your source note stayed private.'));
      approve.disabled = busy; box.append(approve);
    }
    proposals.append(box);
  }
}
function graphNode(title, type, record, cls = '') {
  const b = button('', () => { $('node-detail').hidden = false; $('node-detail').textContent = JSON.stringify(record, null, 2); }, `graph-node ${cls}`);
  b.append(el('small', type), el('span', title)); return b;
}
function renderShared() {
  $('revision').textContent = `r${state.revision}`;
  $('identity').textContent = `${auth.name} · ${state.role}`;
  const healthy = state.checks.every(c => c.passed);
  $('agent-title').textContent = healthy ? 'Checkout recovered. The team made it possible.' : 'Let’s restore checkout without losing data.';
  $('agent-summary').textContent = healthy ? 'Approved evidence from support, engineering, and operations led to a verified repair. The private source notes stayed in their owners’ workspaces.' :
    state.assessment.missing.length ? 'I know the company runbook. I need approved facts from each relevant private workspace before proposing a repair.' :
    state.assessment.conflicts.length ? 'The shared evidence conflicts. Resolve those statements before execution.' : 'The required evidence is shared. I can now propose a bounded repair for operations to review.';
  $('health').textContent = healthy ? '● Verified recovery' : '● Checkout degraded';
  $('health').className = healthy ? 'health good' : 'health';
  $('mode').textContent = `Coordinator: ${state.providers.shared}  /  Local checkout simulator · no production access`;
  $('runbook').textContent = state.runbook;
  const req = $('requirements'); req.replaceChildren();
  for (const [key, label] of Object.entries(labels)) {
    const ready = !state.assessment.missing.includes(key) && !state.assessment.conflicts.includes(key);
    req.append(el('span', `${ready ? '✓' : '○'} ${label}`, `requirement ${ready ? 'ready' : ''}`));
  }
  const claims = $('claims'); claims.replaceChildren();
  for (const c of state.claims) {
    const box = el('div', undefined, 'claim');
    if (c.owner === auth.user) box.append(button('Withdraw', () => {
      if (confirm('Withdraw this statement from future planning? It remains in the shared history and may already be known to others.')) act('withdraw', {disclosure_id: c.id}, 'Withdrawn from future planning. Earlier shared history remains visible.');
    }, 'quiet'));
    box.append(el('strong', c.statement), el('small', `${c.owner} explicitly approved · shared evidence`)); claims.append(box);
  }
  if (state.assessment.conflicts.length) claims.append(el('p', `Conflicting evidence: ${state.assessment.conflicts.join(', ')}. Owners must resolve or withdraw conflicting statements.`, 'muted'));
  $('coordinate').disabled = state.role === 'viewer' || busy;
  $('message-form').hidden = state.role === 'viewer';
  const plan = state.plans[0]; const area = $('plan'); area.replaceChildren();
  if (plan) {
    const box = el('article', undefined, `plan-card ${plan.stale ? 'stale' : ''}`);
    box.append(el('span', plan.stale ? 'STALE · REPLAN REQUIRED' : plan.status.toUpperCase(), 'eyebrow'), el('h3', plan.action.replaceAll('_', ' ')),
      el('p', `Depends on ${plan.evidence.length} approved statements · room revision ${plan.revision}.`));
    const plannedEvent = state.events.find(e => e.kind === 'planned' && e.payload.id === plan.id);
    if (plannedEvent?.payload.comparisons) {
      box.append(el('h3', 'Sandbox comparison'));
      for (const comparison of plannedEvent.payload.comparisons) {
        const row = el('div', undefined, `check ${comparison.passed ? '' : 'failed'}`);
        row.append(el('span', comparison.action.replaceAll('_', ' ')), el('span', comparison.passed ? '✓ VERIFIED' : '× FAILED'));
        box.append(row);
      }
    }
    if (plan.status === 'proposed') {
      box.append(el('p', state.role === 'operations' ? 'Approve this exact action to run it against the local simulator. Changes commit only if all checks pass.' : 'Waiting for an operations member to authorize simulator execution.'));
      if (state.role === 'operations') { const b = button('Approve & verify repair', () => act('execute', {plan_id: plan.id}, 'Repair verified and committed. All four regression checks pass.'), 'primary'); b.disabled = plan.stale || busy; box.append(b); }
    } else box.append(el('p', plan.result?.committed ? 'Repair committed after all regression checks passed.' : 'Verification failed. No configuration change committed.'));
    area.append(box);
  }
  const messages = $('messages'); messages.replaceChildren();
  for (const e of state.events.filter(e => e.kind === 'message').slice(0, 8).reverse()) {
    const n = el('div', undefined, 'message'); n.append(el('small', `${e.actor} · r${e.revision}`), el('span', e.payload.text)); messages.append(n);
  }
  const graph = $('graph'); graph.replaceChildren();
  graph.append(graphNode('Company runbook', 'public knowledge', {runbook: state.runbook}));
  for (const c of state.claims) graph.append(graphNode(c.statement, `approved by ${c.owner}`, c));
  graph.append(el('div', '↓', 'graph-arrow'));
  if (plan) {
    graph.append(graphNode(plan.action.replaceAll('_', ' '), plan.stale ? 'stale proposal' : 'shared plan', {id: plan.id, revision: plan.revision, dependencies: plan.evidence}));
    if (plan.result) { graph.append(el('div', '↓', 'graph-arrow')); graph.append(graphNode(plan.result.committed ? 'Repair verified' : 'Verification failed', 'runtime observation', plan.result, plan.result.committed ? 'verified' : '')); }
  } else graph.append(graphNode('Waiting for approved evidence', 'coordinator', state.assessment));
  const checks = $('checks'); checks.replaceChildren();
  for (const c of state.checks) { const row = el('div', undefined, `check ${c.passed ? '' : 'failed'}`); row.append(el('span', c.name), el('span', c.passed ? '✓ PASS' : '× FAIL')); checks.append(row); }
  const activity = $('activity'); activity.replaceChildren();
  for (const e of state.events.slice(0, 20)) activity.append(el('div', `r${e.revision} · ${e.actor} · ${e.kind.replaceAll('_', ' ')}`, 'event'));
  const people = $('members'); people.replaceChildren();
  for (const m of state.members) {
    const row = el('div', undefined, 'person'); const name = el('div', m.name); name.append(el('small', m.role));
    row.append(el('span', m.name.split(' ').map(n => n[0]).join(''), 'avatar'), name);
    if (state.role === 'operations' && m.user !== auth.user) row.append(button('Revoke', () => {
      if (confirm(`Remove ${m.name} from this room? Their active disclosures will be withdrawn and pending plans will be invalidated.`)) act('revoke', {user: m.user}, 'Room access revoked. Their active disclosures were withdrawn.');
    }, 'quiet'));
    people.append(row);
  }
}
$('user').onchange = () => { const custom = $('user').value === 'custom'; $('custom-login').hidden = !custom; $('password').value = custom ? '' : `${$('user').value}-demo`; };
$('login-form').onsubmit = async event => {
  event.preventDefault(); $('login-error').textContent = '';
  try {
    await api('/api/login', {user: $('user').value === 'custom' ? $('custom-user').value : $('user').value, password: $('password').value});
    auth = await api('/api/me'); generation++;
    $('login-view').hidden = true; $('workspace').hidden = false; notice(''); await refresh(true);
  } catch (e) { $('login-error').textContent = e.message; }
};
$('logout').onclick = async () => { try { await api('/api/logout', {}); } finally { clearSession(); } };
$('analyze').onclick = () => act('analyze', {}, 'Private agent finished. Review the exact proposed statement before sharing.');
$('coordinate').onclick = () => act('coordinate', {}, 'The team agent proposed a repair using only approved shared evidence.');
$('message-form').onsubmit = async event => { event.preventDefault(); const result = await act('message', {text: $('message').value}, 'Note shared with the room.'); if (result) $('message').value = ''; };
async function boot() {
  try { auth = await api('/api/me'); $('login-view').hidden = true; $('workspace').hidden = false; await refresh(true); } catch { clearSession(); }
  setInterval(() => { if (!busy && !document.hidden) refresh(); }, 2000);
}
boot();
