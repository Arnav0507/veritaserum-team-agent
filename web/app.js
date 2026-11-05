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
  for (const id of ['private-requests', 'private-documents', 'proposals', 'claims', 'messages', 'graph', 'activity', 'members', 'plan', 'node-detail', 'requirements', 'checks']) $(id).replaceChildren();
  $('node-detail').hidden = true;
}
function clearSession() {
  generation++; auth = state = privateState = activeRoom = null; rooms = []; drafts.clear(); busy = false;
  clearViews();
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
  for (const id of ['note-body', 'note-title', 'knowledge-body', 'message', 'new-name', 'new-goal', 'password']) $(id).value = '';
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
  $('message').value = ''; notice(''); $('room-title').textContent = 'Opening team chat…';
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
    const [next, priv, conversation] = await Promise.all([api(endpoint('state')), api(endpoint('private')), api(endpoint('conversation'))]);
    priv.conversation = conversation;
    if (epoch !== generation || selected !== activeRoom) return;
    const sharedChanged = force || JSON.stringify(next) !== JSON.stringify(state);
    const privateChanged = force || JSON.stringify(priv) !== JSON.stringify(privateState);
    state = next; privateState = priv; renderRooms();
    if (sharedChanged) { renderShared(); renderPrivate(); }
    if (privateChanged) renderPrivate();

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
  document.querySelectorAll('#workspace button:not(#logout), #room-select, #audience, #message').forEach(b => b.disabled = value);
  document.querySelectorAll('dialog button[type="submit"]').forEach(b => b.disabled = value);
}
const progressText = {turn: 'Veritaserum is responding within the selected audience…', 'private-chat': 'Your private agent is replying. Nothing is being shared.', 'team-chat': 'The team agent is coordinating the next step…', analyze: 'Veritaserum is reviewing your private evidence. Nothing is being shared.', coordinate: 'The team agent is investigating candidate repairs in the sandbox…', execute: 'Checking permissions, testing the repair, and applying it if verification passes…'};
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
      if (state && privateState) { renderShared(); renderPrivate(); }
      await refresh(true);
    }
  }
}
function openNote() { $('note-error').textContent = ''; $('note-dialog').showModal(); $('note-title').focus(); }
function renderConversation() {
  if (!privateState) return;
  $('messages').replaceChildren(...(privateState.conversation?.turns || []).map(turn => {
    const box = el('article', undefined, `message turn-${turn.audience}`);
    box.append(el('strong', turn.speaker === 'agent' ? 'Veritaserum' : nameOf(turn.speaker)),
      el('small', turn.audience === 'private' ? 'Only you · private' : 'Everyone · team'), el('p', turn.text));
    return box;
  }));
}
function renderPrivate() {
  renderConversation();
  const latestRequest = state.events.find(e => e.kind === 'delegated');
  const requested = (latestRequest?.payload.requests || []).filter(r => r.role === state.role && state.assessment.missing.includes(r.key));
  $('private-requests').hidden = !requested.length;
  $('private-requests').replaceChildren(el('strong', requested.length ? 'Request from the team agent' : 'Your private workspace'),
    el('p', requested.length ? requested.map(r => `Requested: ${r.label}.`).join(' ') : 'Discuss your evidence here. Your replies and your agent’s responses stay private.'));

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
      if (result) { drafts.delete(key); renderPrivate(); }
    });
    const discard = button('Discard draft', () => { drafts.delete(key); renderPrivate(); }, 'quiet');
    box.append(textarea, unsaved, save, discard); docs.append(box);
  }
  if (!privateState.documents.length) docs.append(el('p', state.role === 'viewer' ? 'Observers can follow shared work. They do not contribute private evidence.' : 'No private evidence yet.', 'empty-state'));
  $('add-note').hidden = state.role === 'viewer';
  $('analyze').disabled = state.role === 'viewer' || busy || !privateState.documents.length;
  $('private-mode').textContent = state.providers.private.startsWith('live') ? 'Analyzed by your configured AI provider. Sharing requires approval.' : 'Reference mode reads explicit FACT lines from sample notes. Enable a live model to interpret natural language.';
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
  $('health').textContent = recovered ? '● Verified in sandbox' : '● Team chat open'; $('health').className = recovered ? 'health good' : 'health';
  $('mode').textContent = `Private workers: ${state.providers.private}. Shared coordinator: ${state.providers.shared}.`;
  $('runbook').textContent = state.runbook;
  $('requirements').replaceChildren(...Object.entries(labels).map(([key, label]) => {
    const ready = !state.assessment.missing.includes(key) && !state.assessment.conflicts.includes(key);
    return el('span', `${ready ? '✓' : '○'} ${label}`, `requirement ${ready ? 'ready' : ''}`);
  }));
  const claims = $('claims'); claims.replaceChildren();
  if (!state.claims.length) claims.append(el('p', 'No approved contributions yet.', 'empty-state'));
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
  renderConversation();
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
$('audience').onchange = () => {
  // Never carry a private draft into a broader audience implicitly.
  $('message').value = '';
  const privateTurn = $('audience').value === 'private';
  $('send-turn').textContent = privateTurn ? 'Send privately' : 'Send to team';
  $('audience-hint').textContent = privateTurn ? 'Only you see this message and reply. Proposed contributions need your approval before sharing.' : 'This message and the reply are visible to everyone.';
};
$('message-form').onsubmit = async event => {
  event.preventDefault();
  const result = await act('turn', {audience: $('audience').value, text: $('message').value}, 'The agent responded. Private contributions still require your approval.');
  if (result) $('message').value = '';
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
