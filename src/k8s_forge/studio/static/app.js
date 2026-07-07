const $ = (id) => document.getElementById(id);
const consoleBox = $('console');
function log(line) { consoleBox.textContent += line + '\n'; consoleBox.scrollTop = consoleBox.scrollHeight; }
async function json(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.error) { throw new Error(data.error || response.statusText); }
  return data;
}
async function text(url) { const response = await fetch(url); return response.text(); }

async function loadScaffoldDefaults() {
  const defaults = await json('/api/scaffold/defaults');
  $('scaffold-app-name').value = defaults.app_name || '';
  $('scaffold-namespace').value = defaults.namespace || '';
  $('scaffold-image').value = defaults.image || '';
  $('scaffold-workload-type').value = defaults.workload_type || 'job';
  $('scaffold-startup-command').value = defaults.startup_command || '';
  $('scaffold-container-port').value = defaults.container_port || '';
  $('scaffold-service-enabled').checked = Boolean(defaults.service_enabled);
  $('scaffold-restart-policy').value = defaults.restart_policy || 'OnFailure';
  $('scaffold-schedule').value = defaults.schedule || '';
  $('scaffold-persistence').checked = Boolean(defaults.persistence_required);
  log(`[scaffold] ${defaults.message || 'review required'}`);
}
function scaffoldPayload() {
  const port = $('scaffold-container-port').value;
  return {
    app_name: $('scaffold-app-name').value,
    namespace: $('scaffold-namespace').value,
    image: $('scaffold-image').value,
    workload_type: $('scaffold-workload-type').value,
    startup_command: $('scaffold-startup-command').value,
    container_port: port ? Number(port) : null,
    service_enabled: $('scaffold-service-enabled').checked,
    restart_policy: $('scaffold-restart-policy').value,
    schedule: $('scaffold-schedule').value,
    persistence_required: $('scaffold-persistence').checked,
  };
}

async function refresh() {
  const state = await json('/api/state');
  $('state').textContent = JSON.stringify(state, null, 2);
  $('deploy').disabled = !state.deploy_allowed;
  $('warnings').textContent = await text('/api/discovery/warnings');
  $('report').textContent = await text('/api/discovery/report');
  $('app-yaml').value = await text('/api/app-yaml');
  if (state.state.last_explain) $('explain-output').textContent = state.state.last_explain;
}
async function post(path, body = {}) {
  log(`[studio] POST ${path}`);
  const result = await json(path, { method: 'POST', body: JSON.stringify(body) });
  await refresh();
  return result;
}
$('select-repo').onclick = () => post('/api/repo/local', { path: $('repo-path').value }).catch((e) => log(`[error] ${e.message}`));
$('clone-repo').onclick = () => post('/api/repo/clone', { url: $('repo-url').value }).catch((e) => log(`[error] ${e.message}`));
$('discover').onclick = () => post('/api/discover').catch((e) => log(`[error] ${e.message}`));
$('load-scaffold-defaults').onclick = () => loadScaffoldDefaults().catch((e) => log(`[error] ${e.message}`));
$('create-scaffold').onclick = () => post('/api/scaffold/app-yaml', scaffoldPayload()).catch((e) => log(`[error] ${e.message}`));
$('dockerfile-proposal').onclick = async () => { try { $('dockerfile-text').value = await text('/api/dockerfile/proposal'); } catch (e) { log(`[error] ${e.message}`); } };
$('write-dockerfile').onclick = () => { if (confirm('Write Dockerfile to the selected repository?')) post('/api/dockerfile/write', { confirm: true, overwrite: false, content: $('dockerfile-text').value }).catch((e) => log(`[error] ${e.message}`)); };
$('check').onclick = () => post('/api/check').catch((e) => log(`[error] ${e.message}`));
$('explain').onclick = async () => { try { const r = await post('/api/explain'); $('explain-output').textContent = r.explain || ''; } catch (e) { log(`[error] ${e.message}`); } };
$('save-yaml').onclick = () => post('/api/app-yaml', { content: $('app-yaml').value }).catch((e) => log(`[error] ${e.message}`));
$('render').onclick = () => post('/api/render').catch((e) => log(`[error] ${e.message}`));
$('docker-build').onclick = () => post('/api/docker/build').catch((e) => log(`[error] ${e.message}`));
$('kind-load').onclick = () => { const image = prompt('Image to load into kind'); if (image) post('/api/kind/load', { image }).catch((e) => log(`[error] ${e.message}`)); };
$('dry-run').onclick = () => post('/api/dry-run').catch((e) => log(`[error] ${e.message}`));
$('deploy').onclick = () => { if (confirm('Run kubectl apply now?')) post('/api/deploy', { confirm: true }).catch((e) => log(`[error] ${e.message}`)); };
$('status').onclick = () => post('/api/status').catch((e) => log(`[error] ${e.message}`));
const ws = new WebSocket(`ws://${location.host}/ws/jobs`);
ws.onmessage = (event) => { const data = JSON.parse(event.data); log(JSON.stringify(data)); };
refresh().catch((e) => log(`[error] ${e.message}`));
