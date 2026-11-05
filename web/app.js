'use strict';
const $ = id => document.getElementById(id);
let auth = null, state = null, privateState = null, activeRoom = null;
let busy = false, polling = false, generation = 0, rooms = [], knowledgeRevision = null;
const drafts = new Map();
const labels = {affected_segment: 'Customer impact', repair: 'Technical diagnosis', rollback_safe: 'Deployment constraints'};
const roleFacts = {support: 'affected_segment', engineering: 'repair', operations: 'rollback_safe'};
const roleNames = {support: 'Support', engineering: 'Engineering', operations: 'Operations', viewer: 'Observer'};
const actions = {disable_fast_checkout: 'Disable fast checkout', rollback: 'Roll back the release', restart: 'Restart checkout'};
const eventNames = {opened: 'Opened the team chat', disclosed: 'Shared approved evidence', withdrawn: 'Withdrew a statement', planned: 'Proposed a repair', verified: 'Verified and applied the repair', verification_failed: 'Repair failed verification', delegated: 'Requested evidence', message: 'Added a team note', member_revoked: 'Removed a member', member_added: 'Added a member', knowledge_updated: 'Updated company knowledge', abstained: 'Requested further review'};
function el(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
function button(text, fn, cls = 'secondary') { const b = el('button', text, cls); b.type = 'button'; b.onclick = fn; return b; }
function notice(text, error = false) { $('notice').textContent = text; $('notice').className = error ? 'error' : ''; }
function nameOf(user) { return state?.members.find(m => m.user === user)?.name || user; }
function healthy() { return state?.checks.every(c => c.passed); }
function endpoint(op) { return `/api/rooms/${encodeURIComponent(activeRoom)}/${op}`; }
async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 110000);
  const options = {credentials: 'same-origin', cache: 'no-store', headers: {}, signal: controller.signal};
  if (auth) options.headers['X-Expected-User'] = auth.user;
  if (body !== undefined) { options.method = 'POST'; options.headers = {...options.headers, 'Content-Type': 'application/json', 'X-CSRF-Token': auth?.csrf || ''}; options.body = JSON.stringify(body); }
  try {
    const response = await fetch(path, options);
    const result = await response.json();
    if (!response.ok) { const error = new Error(result.error || 'The request could not be completed.'); error.status = response.status; throw error; }
    return result;
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('The request timed out. Refresh the team chat before retrying; it may still finish on the server.');
    if (e instanceof TypeError) throw new Error('Cannot reach the workspace. Check that the local server is running. Your unsaved edits remain in this tab.');
    throw e;
  } finally { clearTimeout(timeout); }
}
function clearViews() {
  for (const id of ['private-chat-messages', 'private-requests', 'private-documents', 'proposals', 'claims', 'messages', 'graph', 'activity', 'members', 'plan', 'node-detail', 'requirements', 'checks']) $(id).replaceChildren();
  $('node-detail').hidden = true;
}
function clearSession() {
  generation++; auth = state = privateState = activeRoom = null; rooms = []; drafts.clear(); busy = false;
  clearViews();
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
  for (const id of ['private-chat-input', 'note-body', 'note-title', 'knowledge-body', 'message', 'new-name', 'new-goal', 'password']) $(id).value = '';
  $('workspace').hidden = true; $('login-view').hidden = false;
}
function renderRooms() {
  const select = $('room-select');
  if (JSON.stringify(rooms.map(r => [r.id, r.name])) !== select.dataset.rooms) {
    select.replaceChildren(...rooms.map(r => { const o = el('option', r.name); o.value = r.id; return o; }));
    select.dataset.rooms = JSON.stringify(rooms.map(r => [r.id, r.name]));
  }
  select.value = activeRoom || ''; select.disabled = busy;
}
async function selectRoom(id) {
  if (busy || id === activeRoom) return;
  generation++; activeRoom = id; state = privateState = null; clearViews();
  $('message').value = ''; $('private-chat-input').value = ''; notice(''); $('room-title').textContent = 'Opening team chat…';
  $('next-action').disabled = true;
  await refresh();
}
async function refresh(force = false) {
  if (!auth || polling) return;
  polling = true; const epoch = generation;
  try {
    const identity = await api('/api/me');
    if (epoch !== generation) return;
    if (identity.user !== auth.user || identity.csrf !== auth.csrf) { clearSession(); $('login-error').textContent = 'Your browser session changed. Sign in again to continue.'; return; }
    const result = await api('/api/rooms');
    if (epoch !== generation) return;
    rooms = result.rooms;
    if (!rooms.length) { clearSession(); $('login-error').textContent = 'You have no active team chats. Contact your workspace administrator.'; return; }
    if (!rooms.some(r => r.id === activeRoom)) { activeRoom = rooms[0].id; state = privateState = null; clearViews(); }
    const selected = activeRoom;
    const [next, priv] = await Promise.all([api(endpoint('state')), api(endpoint('private'))]);
    if (epoch !== generation || selected !== activeRoom) return;
    const sharedChanged = force || JSON.stringify(next) !== JSON.stringify(state);
    const privateChanged = force || JSON.stringify(priv) !== JSON.stringify(privateState);
    state = next; privateState = priv; renderRooms();
    if (sharedChanged) { renderShared(); renderPrivate(); }
    if (privateChanged) renderPrivate();
    renderNext();
    $('connection').textContent = '● Up to date'; $('connection').className = 'connected';
  } catch (e) {
    if (epoch !== generation) return;
    if (e.status === 401) { clearSession(); $('login-error').textContent = e.message; }
    else if (e.status === 403) { activeRoom = null; state = privateState = null; clearViews(); notice('Your access to this team chat changed. Checking available team chats…', true); }
    else { $('connection').textContent = '○ Connection interrupted'; $('connection').className = 'disconnected'; notice(e.message, true); }
  } finally { polling = false; }
}
function setBusy(value) {
  busy = value; $('workspace').setAttribute('aria-busy', String(value));
  document.querySelectorAll('#workspace button:not(#logout), #room-select').forEach(b => b.disabled = value);
  document.querySelectorAll('dialog button[type="submit"]').forEach(b => b.disabled = value);
}
const progressText = {'private-chat': 'Your private agent is replying. Nothing is being shared.', 'team-chat': 'The team agent is coordinating the next step…', analyze: 'Your private agent is reviewing your notes. Nothing is being shared.', coordinate: 'The team agent is investigating candidate repairs in the sandbox…', execute: 'Checking permissions, testing the repair, and applying it if verification passes…'};
async function act(op, body = {}, success = '', errorTarget = null) {
  if (busy) return;
  const epoch = generation;
  setBusy(true); notice(progressText[op] || 'Saving…');
  if (errorTarget) $(errorTarget).textContent = '';
  try {
    const result = await api(op === 'create-room' ? '/api/rooms' : endpoint(op), body);
    if (epoch !== generation) return;
    notice(result.status === 'needs_evidence' ? 'The team still needs evidence. Check the next step for your role.' :
      result.status === 'abstained' ? 'The agent could not support a repair. Review the evidence and try again.' :
      result.committed === false ? 'This repair failed verification. The previous configuration is unchanged.' :
      op === 'analyze' && !result.proposal_ids.length ? 'No supported statement was found. Add concrete observations relevant to your role, then review again.' : success || 'Saved.');
    return result;
  } catch (e) {
    if (epoch !== generation) return;
    notice(e.message, true);
    if (errorTarget) $(errorTarget).textContent = e.message;
    if (e.status === 401) { clearSession(); $('login-error').textContent = e.message; }
  } finally {
    if (epoch === generation) {
      setBusy(false);
      if (state && privateState) { renderShared(); renderPrivate(); renderNext(); }
      await refresh(true);
    }
  }
}
function openNote() { $('note-error').textContent = ''; $('note-dialog').showModal(); $('note-title').focus(); }
function renderPrivate() {
  $('private-chat-form').hidden = state.role === 'viewer';
  $('private-chat-messages').replaceChildren(...(privateState.messages || []).map(m => {
    const box = el('div', undefined, 'message'); box.append(el('strong', m.speaker === 'you' ? 'You · private' : 'Your private agent'), el('p', m.text)); return box;
  }));
  const latestRequest = state.events.find(e => e.kind === 'delegated');
  const requested = (latestRequest?.payload.requests || []).filter(r => r.role === state.role && state.assessment.missing.includes(r.key));
  $('private-requests').replaceChildren(el('strong', requested.length ? 'Request from the team agent' : 'Your private workspace'),
    el('p', requested.length ? requested.map(r => `Please help establish: ${r.label}. Discuss the evidence privately, then approve a statement for the team.`).join(' ') : 'Discuss your evidence here. Your replies and your agent’s responses stay private.'));

  const docs = $('private-documents'); docs.replaceChildren();
  for (const doc of privateState.documents) {
    const key = `${activeRoom}:${doc.id}`;
    const draft = drafts.get(key);
    const box = el('details', undefined, 'doc'); box.open = Boolean(draft);
    box.append(el('summary', doc.title), el('p', `Private note · revision ${doc.version}`, 'hint'));
    const textarea = el('textarea'); textarea.value = draft?.body ?? doc.body; textarea.setAttribute('aria-label', `Edit ${doc.title}`);
    textarea.maxLength = 16000;
    const unsaved = el('p', draft ? 'Unsaved changes in this tab' : 'Visible only to you', 'hint');
    textarea.oninput = () => { drafts.set(key, {body: textarea.value, version: draft?.version ?? doc.version}); unsaved.textContent = 'Unsaved changes in this tab'; };
    const save = button('Save changes', async () => {
      const edit = drafts.get(key);
      if (!edit) return;
      const result = await act('document', {document_id: doc.id, body: edit.body, version: edit.version}, 'Private note updated. Earlier statements from this note need a new review.');
      if (result) { drafts.delete(key); renderPrivate(); renderNext(); }
    });
    const discard = button('Discard draft', () => { drafts.delete(key); renderPrivate(); }, 'quiet');
    box.append(textarea, unsaved, save, discard); docs.append(box);
  }
  if (!privateState.documents.length) docs.append(el('p', state.role === 'viewer' ? 'Observers can follow shared work. They do not contribute private evidence.' : 'Start with a note: an observation, customer report, or diagnostic result. It will be visible only to you.', 'empty-state'));
  $('add-note').hidden = state.role === 'viewer';
  $('analyze').disabled = state.role === 'viewer' || busy || !privateState.documents.length;
  $('private-mode').textContent = state.providers.private.startsWith('live') ? 'Reviewing sends your saved notes to the configured AI provider. Proposed statements remain private until you share them.' : 'Reference mode reads explicit FACT lines from sample notes. Enable a live model to interpret natural language.';
  const proposals = $('proposals'); proposals.replaceChildren();
  const current = privateState.proposals.filter(p => !p.stale);
  if (current.length) proposals.append(el('h3', 'Statements to review'));
  for (const p of current) {
    const box = el('article', undefined, 'proposal');
    box.append(el('span', p.released ? 'SHARED' : p.disclosure_id ? 'WITHDRAWN · CAN BE SHARED AGAIN' : 'READY FOR YOUR REVIEW', 'eyebrow'),
      el('p', p.statement, 'exact'), el('p', `Based on “${p.source_title}”`, 'hint'));
    if (!p.released) {
      box.append(el('p', 'Sharing reveals this exact statement and your identity to everyone in this team chat. Your source note stays private.', 'hint'));
      const share = button(p.disclosure_id ? 'Share this statement again' : 'Share this statement', () => act('disclose', {proposal_id: p.id}, 'Statement shared. Your original note remains private.'));
      share.disabled = busy; box.append(share);
    }
    proposals.append(box);
  }
  const outdated = privateState.proposals.filter(p => p.stale);
  if (outdated.length) {
    const history = el('details', undefined, 'activity'); history.append(el('summary', `${outdated.length} statement${outdated.length === 1 ? '' : 's'} need a new review`));
    history.append(el('p', 'These statements came from older notes and cannot be shared. Review your current evidence to propose updated statements.', 'hint'));
    outdated.forEach(p => history.append(el('p', p.statement, 'muted'))); proposals.append(history);
  }
}
function renderNext() {
  if (!state || !privateState) return;
  const plan = state.plans[0], key = roleFacts[state.role];
  const mine = privateState.proposals.some(p => !p.stale && !p.released);
  let title, description, label, fn;
  if (healthy()) { title = 'The repair is verified'; description = 'All checkout checks pass. The decision history preserves the evidence and approvals behind this result.'; label = 'See verification'; fn = () => $('checks').scrollIntoView({behavior: 'smooth', block: 'center'}); }
  else if (state.role === 'viewer') { title = 'Follow the team chat'; description = 'You can read the shared evidence, decisions, and results. Contributors control their own disclosures.'; label = 'See shared evidence'; fn = () => $('claims').scrollIntoView({behavior: 'smooth'}); }
  else if (!privateState.documents.length) { title = 'Talk to your private agent'; description = `Your team needs ${labels[key].toLowerCase()}. Add what you know; nothing is shared automatically.`; label = 'Start privately'; fn = () => $('private-chat-input').focus(); }
  else if (mine) { title = 'Choose what your team can see'; description = 'Your agent has proposed statements. Review their accuracy and share only what belongs in the team chat.'; label = 'Review statements'; fn = () => $('proposals').scrollIntoView({behavior: 'smooth', block: 'center'}); }
  else if (state.assessment.missing.includes(key)) { title = 'Review your private evidence'; description = `Help the team understand ${labels[key].toLowerCase()}. Your agent will propose a statement for your approval.`; label = 'Review my evidence'; fn = () => $('analyze').click(); }
  else if (state.assessment.conflicts.length) { title = 'Resolve conflicting statements'; description = 'Some shared statements disagree. Their owners should review the source notes and withdraw or update the conflicting evidence.'; label = 'Review shared evidence'; fn = () => $('claims').scrollIntoView({behavior: 'smooth'}); }
  else if (state.assessment.missing.length) { title = 'Your contribution is shared'; description = `Waiting for ${state.assessment.missing.map(k => labels[k].toLowerCase()).join(' and ')}. You can keep investigating or leave a team note.`; label = 'Add a team note'; fn = () => $('message').focus(); }
  else if (plan && plan.status === 'proposed' && !plan.stale) { title = state.role === 'operations' ? 'Review the proposed repair' : 'Waiting for operations approval'; description = 'The team agent compared candidate repairs. Operations can approve the specific action after reviewing its checks.'; label = 'Review repair'; fn = () => $('plan').scrollIntoView({behavior: 'smooth', block: 'center'}); }
  else { title = plan?.stale ? 'Update the plan with current evidence' : 'The team is ready to investigate'; description = 'The required perspectives are shared. Ask the team agent to compare candidate repairs and propose a verified action.'; label = 'Find a repair'; fn = () => $('coordinate').click(); }
  $('next-title').textContent = title; $('next-description').textContent = description;
  $('next-action').textContent = label; $('next-action').onclick = fn; $('next-action').disabled = busy;
  const step = healthy() ? 4 : plan && !plan.stale ? 3 : state.assessment.missing.length || state.assessment.conflicts.length ? 1 : 2;
  $('progress').replaceChildren(...['Gather evidence', 'Share & align', 'Review a repair', 'Verify the outcome'].map((label, i) => el('li', `${i < step - 1 || healthy() ? '✓' : i + 1}  ${label}`, i < step ? 'complete' : '')));
}
function graphNode(title, type, record) {
  const b = button('', () => {
    const detail = $('node-detail'); detail.hidden = false; detail.replaceChildren(el('strong', title), el('p', type));
    if (record.owner) detail.append(el('p', `Shared by ${nameOf(record.owner)} after explicit approval.`));
    if (record.dependencies) detail.append(el('p', `Based on ${record.dependencies.length} approved statements. The runtime checks these dependencies again before execution.`));
    if (record.checks) record.checks.forEach(c => detail.append(el('p', `${c.passed ? '✓' : '×'} ${c.name}: ${c.actual}`)));
    if (record.runbook) detail.append(el('p', record.runbook));
    const technical = el('details'); technical.append(el('summary', 'Technical record'), el('pre', JSON.stringify(record, null, 2))); detail.append(technical);
  }, 'graph-node');
  b.append(el('small', type), el('span', title)); return b;
}
function renderShared() {
  $('room-title').textContent = state.name; $('room-goal').textContent = state.goal;
  $('revision').textContent = `· revision ${state.revision}`;
  $('identity').textContent = `${auth.name} · ${roleNames[state.role]}`;
  $('new-room').hidden = state.role === 'viewer'; $('edit-knowledge').hidden = state.role !== 'operations';
  const recovered = healthy();
  $('agent-title').textContent = recovered ? 'The repair passed every check.' : 'Let’s find a repair the team can trust.';
  $('agent-summary').textContent = recovered ? 'The approved repair was verified in the checkout sandbox. Its evidence and execution record are available below.' : state.assessment.conflicts.length ? 'The shared evidence conflicts. Resolve those statements before planning a repair.' : state.assessment.missing.length ? 'I can use the company runbook and the statements you share. I’m waiting for the team’s remaining perspectives.' : 'The required evidence is available. I can compare candidate repairs in the sandbox for your review.';
  $('health').textContent = recovered ? '● Verified in sandbox' : '● Team chat open'; $('health').className = recovered ? 'health good' : 'health';
  $('mode').textContent = `Private workers: ${state.providers.private}. Shared coordinator: ${state.providers.shared}.`;
  $('runbook').textContent = state.runbook;
  $('requirements').replaceChildren(...Object.entries(labels).map(([key, label]) => {
    const ready = !state.assessment.missing.includes(key) && !state.assessment.conflicts.includes(key);
    return el('span', `${ready ? '✓' : '○'} ${label}`, `requirement ${ready ? 'ready' : ''}`);
  }));
  const claims = $('claims'); claims.replaceChildren();
  if (!state.claims.length) claims.append(el('p', 'No evidence has been shared yet. Each contributor decides what crosses from their private workspace.', 'empty-state'));
  for (const c of state.claims) {
    const box = el('div', undefined, 'claim');
    if (c.owner === auth.user) box.append(button('Withdraw', () => {
      if (confirm('Withdraw this statement from future planning? It remains in shared history. You can share it again later.')) act('withdraw', {disclosure_id: c.id}, 'Statement withdrawn. Pending plans must be reconsidered.');
    }, 'quiet'));
    box.append(el('strong', c.statement), el('small', `Shared by ${nameOf(c.owner)} · explicitly approved`)); claims.append(box);
  }
  if (state.assessment.conflicts.length) claims.append(el('p', `Review conflicting evidence: ${state.assessment.conflicts.map(k => labels[k]).join(', ')}.`, 'form-error'));
  $('coordinate').disabled = state.role === 'viewer' || busy || recovered || Boolean(state.assessment.missing.length || state.assessment.conflicts.length);
  $('coordinate').textContent = recovered ? 'Repair verified' : 'Find a repair ↗'; $('message-form').hidden = state.role === 'viewer';
  const plan = state.plans[0], area = $('plan'); area.replaceChildren();
  if (plan) {
    const box = el('article', undefined, `plan-card ${plan.stale ? 'stale' : ''}`);
    const status = plan.stale ? 'EVIDENCE CHANGED · UPDATE NEEDED' : {proposed: 'READY FOR OPERATIONS REVIEW', executed: 'VERIFIED AND APPLIED', failed: 'VERIFICATION FAILED'}[plan.status];
    box.append(el('span', status, 'eyebrow'), el('h3', actions[plan.action] || plan.action), el('p', `Based on ${plan.evidence.length} approved statements.`));
    const event = state.events.find(e => e.kind === 'planned' && e.payload.id === plan.id);
    const receipt = el('details', undefined, 'context-receipt');
    receipt.append(el('summary', 'Inspect what the shared agent received'));
    receipt.append(el('p', 'Application context passed to the shared provider for this plan. Adapter instructions and subsequent tool messages are separate. This is not hidden model reasoning.'));
    if (event?.payload.shared_context) {
      receipt.append(el('pre', JSON.stringify(event.payload.shared_context, null, 2)));
      receipt.append(el('p', 'Private notes and pending proposals are excluded by context construction. Provider credentials are sent separately as authentication headers. Information deliberately entered into shared fields is shared.'));
    } else receipt.append(el('p', 'No context receipt was recorded for this older plan. Create a new plan in an open team chat to inspect its input.'));
    box.append(receipt);
    if (event?.payload.comparisons) {
      box.append(el('h3', 'Candidate repair checks'));
      for (const comparison of event.payload.comparisons) {
        const row = el('div', undefined, `check ${comparison.passed ? '' : 'failed'}`);
        row.append(el('span', actions[comparison.action]), el('span', comparison.passed ? '✓ Passes' : '× Fails')); box.append(row);
      }
    }
    if (plan.stale) box.append(el('p', 'The evidence or shared context changed after this plan was created. Find a new repair before approving execution.'));
    else if (plan.status === 'proposed') {
      box.append(el('p', state.role === 'operations' ? 'Approving runs this repair in the checkout sandbox. It takes effect only if all checks pass.' : 'An operations member must approve this specific repair.'));
      if (state.role === 'operations') { const b = button('Approve & apply in sandbox', () => act('execute', {plan_id: plan.id}, 'Repair verified and applied. All checkout checks pass.'), 'primary'); b.disabled = busy; box.append(b); }
    } else box.append(el('p', plan.result?.committed ? 'The repair passed verification and was applied to the sandbox.' : 'The repair failed verification. Review the evidence; no configuration change was applied.'));
    area.append(box);
  }
  const messages = $('messages'); messages.replaceChildren();
  for (const e of state.events.filter(e => ['message', 'delegated', 'planned', 'abstained'].includes(e.kind)).slice(0, 16).reverse()) {
    const text = e.kind === 'message' ? e.payload.text : e.kind === 'delegated' ?
      `I’m requesting private contributions: ${(e.payload.requests || []).map(r => `${roleNames[r.role]} — ${r.label}`).join('; ') || 'resolve conflicting approved statements'}. Each owner decides what to share.` :
      e.kind === 'planned' ? 'I compared the approved evidence and prepared a repair for operations to review.' : 'I could not support a repair from the current evidence.';
    const n = el('div', undefined, 'message'); n.append(el('small', e.kind === 'message' ? nameOf(e.actor) : 'Team agent'), el('span', text)); messages.append(n);
  }
  const plannedEvent = plan && state.events.find(e => e.kind === 'planned' && e.payload.id === plan.id);
  const graph = $('graph'); graph.replaceChildren(graphNode('Company knowledge', plan ? 'Context at planning' : 'Shared context',
    {runbook: plan ? plannedEvent?.payload.company_knowledge ?? 'Historical context unavailable in this recent activity window.' : state.runbook}));
  const dependencies = plan ? state.events.filter(e => e.kind === 'disclosed' && plan.evidence.includes(e.payload.id)) : [];
  const graphClaims = plan ? [...new Map(dependencies.map(e => [e.payload.id, {...e.payload, owner: e.actor}])).values()] : state.claims;
  for (const c of graphClaims) graph.append(graphNode(c.statement, `Approved by ${nameOf(c.owner)}`, c));
  if (plan && graphClaims.length < plan.evidence.length) graph.append(el('p', 'Some evidence predates this recent activity window. The full record remains in the workspace database.', 'muted'));
  graph.append(el('div', '↓', 'graph-arrow'));
  if (plan) {
    graph.append(graphNode(actions[plan.action], plan.stale ? 'Plan needs review' : 'Shared decision', {id: plan.id, revision: plan.revision, dependencies: plan.evidence}));
    if (plan.result) { graph.append(el('div', '↓', 'graph-arrow')); graph.append(graphNode(plan.result.committed ? 'Repair verified' : 'Verification failed', 'Observed result', plan.result)); }
  } else graph.append(graphNode('Gathering approved evidence', 'Team chat', state.assessment));
  $('checks').replaceChildren(...state.checks.map(c => { const row = el('div', undefined, `check ${c.passed ? '' : 'failed'}`); row.append(el('span', c.name), el('span', c.passed ? '✓ Passing' : '× Failing')); return row; }));
  $('activity').replaceChildren(...state.events.slice(0, 30).map(e => el('div', `${nameOf(e.actor)} · ${eventNames[e.kind] || e.kind} · ${new Date(e.created * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`, 'event')));
  const people = $('members'); people.replaceChildren();
  for (const m of state.members) {
    const row = el('div', undefined, 'person'), name = el('div', m.name); name.append(el('small', roleNames[m.role]));
    row.append(el('span', m.name.split(' ').map(n => n[0]).join(''), 'avatar'), name);
    if (state.role === 'operations' && m.user !== auth.user) row.append(button('Remove', () => {
      if (confirm(`Remove ${m.name} from this team chat? Their active disclosures will be withdrawn and pending plans invalidated. They may retain information already delivered.`)) act('revoke', {user: m.user}, 'Access removed and active disclosures withdrawn.');
    }, 'quiet'));
    people.append(row);
  }
}
for (const [user, role] of [['maya', 'Support'], ['eli', 'Engineering'], ['noor', 'Operations'], ['alex', 'Observer']]) {
  $('sample-accounts').append(button(`${user} · ${role}`, () => { $('username').value = user; $('password').value = `${user}-demo`; $('login-error').textContent = ''; }, 'secondary'));
}
$('login-form').onsubmit = async event => {
  event.preventDefault(); $('login-error').textContent = '';
  const submit = $('login-form').querySelector('button'); submit.disabled = true;
  try {
    await api('/api/login', {user: $('username').value.trim(), password: $('password').value});
    auth = await api('/api/me'); generation++; activeRoom = null;
    $('password').value = ''; $('login-view').hidden = true; $('workspace').hidden = false; notice(''); await refresh(true);
  } catch (e) { $('login-error').textContent = e.message; }
  finally { submit.disabled = false; }
};
$('logout').onclick = async () => { try { await api('/api/logout', {}); clearSession(); } catch (e) { notice(`Sign-out was not confirmed. ${e.message}`, true); } };
$('room-select').onchange = () => selectRoom($('room-select').value);
$('add-note').onclick = openNote;
$('analyze').onclick = () => act('analyze', {}, 'Your evidence is reviewed. Choose which statements to share.');
$('coordinate').onclick = () => act('coordinate', {}, 'A repair is ready for operations to review.');
$('message-form').onsubmit = async event => { event.preventDefault(); const result = await act('team-chat', {text: $('message').value}, 'The team agent responded.'); if (result) $('message').value = ''; };
$('private-chat-form').onsubmit = async event => {
  event.preventDefault();
  const result = await act('private-chat', {text: $('private-chat-input').value}, 'Your private agent replied.');
  if (result) {
    $('private-chat-input').value = '';
    await act('analyze', {}, 'Private response ready. Review proposed statements below; nothing has been shared.');
  }
};
$('note-form').onsubmit = async event => {
  event.preventDefault(); const result = await act('add-document', {title: $('note-title').value, body: $('note-body').value}, 'Private note saved. Review it with your agent when you are ready.', 'note-error');
  if (result) { $('note-dialog').close(); $('note-form').reset(); }
};
$('new-room').onclick = () => {
  $('room-error').textContent = ''; $('room-members').replaceChildren();
  for (const m of state.members) {
    const label = el('label', undefined, 'member-choice'), input = el('input'); input.type = 'checkbox'; input.value = m.user; input.checked = true; input.disabled = m.user === auth.user;
    label.append(input, el('span', `${m.name} · ${roleNames[m.role]}`)); $('room-members').append(label);
  }
  $('room-dialog').showModal(); $('new-name').focus();
};
$('room-form').onsubmit = async event => {
  event.preventDefault(); const result = await act('create-room', {source_room: activeRoom, name: $('new-name').value, goal: $('new-goal').value, members: [...$('room-members').querySelectorAll('input:checked')].map(n => n.value)}, 'Team chat created. Each person starts with a private evidence workspace.', 'room-error');
  if (result) { $('room-dialog').close(); $('room-form').reset(); await selectRoom(result.id); }
};
$('edit-knowledge').onclick = () => { knowledgeRevision = state.revision; $('knowledge-body').value = state.runbook; $('knowledge-error').textContent = ''; $('knowledge-dialog').showModal(); };
$('knowledge-form').onsubmit = async event => {
  event.preventDefault(); const result = await act('knowledge', {runbook: $('knowledge-body').value, revision: knowledgeRevision}, 'Shared knowledge updated. Pending plans need a fresh review.', 'knowledge-error');
  if (result) $('knowledge-dialog').close();
};
for (const b of document.querySelectorAll('[data-close]')) b.onclick = () => $(b.dataset.close).close();
window.addEventListener('beforeunload', event => { if (drafts.size || $('note-body').value) { event.preventDefault(); event.returnValue = ''; } });
async function boot() {
  try { auth = await api('/api/me'); $('login-view').hidden = true; $('workspace').hidden = false; await refresh(true); } catch { clearSession(); }
  setInterval(() => { if (!busy && !document.hidden) refresh(); }, 2500);
}
boot();
