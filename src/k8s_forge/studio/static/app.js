const $ = (id) => document.getElementById(id);
const consoleBox = $('console');
let lastState = null;
let pollingTimer = null;
let pollingEnabled = false;
let seenJobStatuses = new Map();
let websocketReady = false;
let kindClusters = [];
let preferredKindCluster = "";
let activeActions = new Set();

function normalizeMultiline(value) {
  return String(value || '').replace(/\\n/g, '\n');
}

function log(line) {
  consoleBox.textContent += normalizeMultiline(line) + '\n';
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

async function json(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.error) {
    const error = new Error(data.error || response.statusText);
    error.nextAction = data.next_action || '';
    throw error;
  }
  return data;
}

async function text(url) {
  const response = await fetch(url);
  return response.text();
}

function logError(error) {
  log(`[error] ${error.message}`);
  if (error.nextAction) log(`[NEXT] ${error.nextAction}`);
  showResult('[FAILED] Action failed', [`error: ${error.message}`, error.nextAction ? `next: ${error.nextAction}` : 'next: review the error and retry'], 'failed');
}

function hasAppYaml(snapshot) {
  return Boolean(snapshot.state.app_yaml_path);
}

function showStreamingWarning() {
  const warning = $('streaming-warning');
  warning.hidden = false;
  warning.textContent = 'Live job streaming unavailable. Falling back to polling.';
  log('[warning] Live job streaming unavailable. Falling back to polling.');
}

function showResult(title, lines = [], status = 'info', key = '') {
  const resultKey = key || title;
  let card = Array.from(document.querySelectorAll('[data-result-key]')).find(
    (element) => element.dataset.resultKey === resultKey,
  );
  if (!card) {
    card = document.createElement('article');
    card.dataset.resultKey = resultKey;
    $('action-results').prepend(card);
  }
  card.className = `result-card ${status}`;
  card.innerHTML = '';
  const heading = document.createElement('h3');
  heading.textContent = title;
  const details = document.createElement('pre');
  details.textContent = lines.filter(Boolean).map(normalizeMultiline).join('\n');
  card.appendChild(heading);
  card.appendChild(details);
}

function commandLine(job) {
  return job && Array.isArray(job.command) ? job.command.join(' ') : '';
}

function jobOk(job) {
  return job && job.status === 'succeeded';
}

function actionButtonId(path) {
  return {
    '/api/check': 'check',
    '/api/explain': 'explain',
    '/api/render': 'render',
    '/api/docker/build': 'docker-build',
    '/api/kind/load': 'kind-load',
    '/api/dry-run': 'dry-run',
    '/api/deploy': 'deploy',
    '/api/deploy/job/redeploy': 'job-redeploy',
    '/api/status': 'status',
    '/api/logs': 'read-logs',
  }[path] || '';
}

function actionResultKey(path) {
  return {
    '/api/check': 'check',
    '/api/explain': 'explain',
    '/api/render': 'render',
    '/api/docker/build': 'docker-build',
    '/api/kind/load': 'kind-load',
    '/api/dry-run': 'dry-run',
    '/api/deploy': 'deploy',
    '/api/deploy/job/redeploy': 'job-redeploy',
    '/api/status': 'status',
    '/api/logs': 'logs',
  }[path] || path;
}

function setActionRunning(path, running) {
  if (running) activeActions.add(path);
  else activeActions.delete(path);
  const button = $(actionButtonId(path));
  if (button) button.disabled = running || button.disabled;
}

function anyActionRunning() {
  return activeActions.size > 0;
}

function promptRedeployConfirmation() {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    const dialog = document.createElement('div');
    dialog.className = 'confirm-dialog';
    const title = document.createElement('h3');
    title.textContent = 'Delete existing Job and redeploy';
    const instruction = document.createElement('p');
    instruction.textContent = 'Type exactly:';
    const phrase = document.createElement('pre');
    phrase.textContent = 'DELETE JOB AND REDEPLOY';
    const input = document.createElement('input');
    input.placeholder = 'DELETE JOB AND REDEPLOY';
    input.autocomplete = 'off';
    const actions = document.createElement('div');
    actions.className = 'confirm-actions';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = 'Cancel';
    const submit = document.createElement('button');
    submit.type = 'button';
    submit.textContent = 'Confirm delete and redeploy';
    actions.appendChild(cancel);
    actions.appendChild(submit);
    dialog.appendChild(title);
    dialog.appendChild(instruction);
    dialog.appendChild(phrase);
    dialog.appendChild(input);
    dialog.appendChild(actions);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    input.focus();

    function close(value) {
      overlay.remove();
      resolve(value);
    }

    cancel.onclick = () => close('');
    submit.onclick = () => close(input.value);
    input.onkeydown = (event) => {
      if (event.key === 'Enter') close(input.value);
      if (event.key === 'Escape') close('');
    };
  });
}

function renderStateSnapshot(snapshot) {
  const clone = JSON.parse(JSON.stringify(snapshot));
  if (clone.state && clone.state.last_explain) {
    clone.state.last_explain = '[see Explain panel]';
  }
  return JSON.stringify(clone, null, 2);
}

function setText(id, value) {
  $(id).textContent = normalizeMultiline(value || '');
}

function appContext(snapshot) {
  return (snapshot && snapshot.app_context) || {};
}

function generatedK8sDir(snapshot) {
  return (snapshot && snapshot.paths && snapshot.paths.generated_k8s_dir)
    || (snapshot && snapshot.state && snapshot.state.generated_k8s_dir)
    || '<generated-k8s-dir>';
}

function appName(snapshot) {
  const context = appContext(snapshot);
  return context.name || 'app-name';
}

function namespaceName(snapshot) {
  const context = appContext(snapshot);
  return context.namespace || appName(snapshot);
}

function workloadType(snapshot) {
  const context = appContext(snapshot);
  return context.workload_type || 'deployment';
}

function localImage(snapshot) {
  const context = appContext(snapshot);
  return context.image || `${appName(snapshot)}:dev`;
}

function productionRegistry() {
  return $('prod-registry') ? $('prod-registry').value.trim() : '';
}

function releaseTag() {
  return $('prod-release-tag') && $('prod-release-tag').value.trim()
    ? $('prod-release-tag').value.trim()
    : '<release-tag>';
}

function productionContext() {
  return $('prod-context') && $('prod-context').value.trim()
    ? $('prod-context').value.trim()
    : '<production-context>';
}

function productionImage(snapshot) {
  const registry = productionRegistry() || '<registry>';
  return `${registry}/${appName(snapshot)}:${releaseTag()}`;
}

function memoStatus(label, detail, status, next = '') {
  return { label, detail, status, next };
}

function renderReadinessMemo(snapshot) {
  const state = snapshot.state || {};
  const deployBlocked = state.deploy_status !== 'succeeded' && Boolean(state.deploy_blocked_reason);
  const steps = [
    memoStatus('Select repository', 'Select a local repository or clone one, then verify it is the expected source.', state.repo_path ? 'done' : 'ready'),
    memoStatus('Discover repository', 'Identify application type, Docker, Python/FastAPI/CLI, CI, storage and warning signals.', state.discovery_dir ? 'done' : (state.repo_path ? 'ready' : 'not started')),
    memoStatus('Choose workload type', 'deployment = web/API, worker = long-running process, job = one-shot task, cronjob = scheduled task.', state.app_yaml_path ? 'done' : (state.needs_scaffold ? 'blocked' : 'ready'), state.needs_scaffold ? 'Create an assisted scaffold.' : ''),
    memoStatus('Create or review app.yaml', 'Review app.name, namespace, image, command, args, restartPolicy, service.enabled and ingress.enabled.', state.app_yaml_path ? 'done' : 'blocked', state.app_yaml_path ? '' : 'Create app.yaml before Check.'),
    memoStatus('Run Check', 'Validate the k8s-forge configuration and fix blocking errors.', ['checked', 'explained', 'manifests_rendered', 'dry_run_ok', 'deploy_blocked', 'deployed'].includes(state.state) ? 'done' : (state.app_yaml_path ? 'ready' : 'blocked')),
    memoStatus('Run Explain', 'Read generated risks for ports, secrets, storage, security, Linux/container compatibility, probes and resources.', state.last_explain ? 'done' : (state.app_yaml_path ? 'ready' : 'blocked')),
    memoStatus('Render manifests', `Generate Kubernetes manifests and review ${generatedK8sDir(snapshot)} before deployment.`, state.generated_k8s_dir ? 'done' : (state.app_yaml_path ? 'ready' : 'blocked')),
    memoStatus('Build Docker image', 'Build the image, verify the tag, and ensure the Dockerfile uses a non-root user.', state.docker_build_ok ? 'done' : (state.generated_k8s_dir ? 'ready' : 'blocked')),
    memoStatus('Load image into Kind', `Select the correct local Kind cluster${preferredKindCluster ? `, currently ${preferredKindCluster}` : ''}.`, state.kind_load_ok ? 'done' : (preferredKindCluster && state.docker_build_ok ? 'ready' : 'blocked'), state.kind_load_ok ? '' : (preferredKindCluster ? '' : 'Select or create a Kind cluster.')),
    memoStatus('Dry-run', 'Run kubectl apply --dry-run=client. No real deploy before dry-run succeeds.', state.dry_run_ok ? 'done' : (state.generated_k8s_dir ? 'ready' : 'blocked')),
    memoStatus('Deploy to local lab', 'Deploy only to a local/lab cluster with explicit confirmation. Existing Jobs require confirmed delete before redeploy.', state.deploy_status === 'cancelled' ? 'cancelled' : (deployBlocked || state.deploy_status === 'blocked_existing_job' ? 'blocked' : (state.deploy_status === 'succeeded' ? 'done' : (snapshot.deploy_allowed ? 'ready' : 'blocked'))), deployBlocked ? state.deploy_blocked_next_action : (snapshot.deploy_allowed ? 'Confirm Deploy.' : snapshot.deploy_reason)),
    memoStatus('Verify status', `Run kubectl get all -n ${namespaceName(snapshot)} and inspect pods, jobs, services and events.`, state.status_ok ? 'done' : (state.deploy_status === 'succeeded' ? 'ready' : 'not started')),
    memoStatus('Read logs', 'Read Pod or Job logs and confirm the application starts correctly.', state.logs_ok ? 'done' : (state.deploy_status === 'succeeded' ? 'ready' : 'not started'), state.logs_ok ? 'Review logs and production handoff checklist' : ''),
  ];
  const list = $('readiness-memo');
  list.innerHTML = '';
  for (const step of steps) {
    const item = document.createElement('li');
    const statusClass = step.status.replace(/ /g, '-');
    item.className = `memo-step ${statusClass}`;
    const title = document.createElement('div');
    title.innerHTML = `<span class="memo-status">[${step.status}]</span> ${step.label}`;
    const detail = document.createElement('p');
    detail.textContent = step.detail;
    item.appendChild(title);
    item.appendChild(detail);
    if (step.next) {
      const next = document.createElement('p');
      next.textContent = `[next] ${step.next}`;
      item.appendChild(next);
    }
    list.appendChild(item);
  }
}

function productionStep(title, status, why, commands, expected, warning = '') {
  return { title, status, why, commands, expected, warning };
}

function renderProductionChecklist(snapshot) {
  const app = appName(snapshot);
  const ns = namespaceName(snapshot);
  const workload = workloadType(snapshot);
  const generated = generatedK8sDir(snapshot);
  const local = localImage(snapshot);
  const prod = productionImage(snapshot);
  const dnsName = `<dns-name>`;
  const podName = `<pod-name>`;
  const serviceAccount = `<service-account>`;
  const previous = `<previous-generated-k8s-dir>`;
  const notWeb = workload === 'job' || workload === 'cronjob';
  const steps = [
    productionStep('Push image to registry', 'manual', 'A local image is not enough for production; the cluster must pull from a registry.', [`docker images | grep ${app}`, `docker tag ${local} ${prod}`, `docker push ${prod}`], 'The image exists in the registry and the cluster can pull it.', `Do not use ${app}:dev in production.`),
    productionStep('Use immutable image tag', 'manual', 'Avoid mutable tags such as latest or dev.', ['git rev-parse --short HEAD', `docker tag ${local} <registry>/${app}:$(git rev-parse --short HEAD)`, `grep -R "image:" ${generated}`], `The manifest references ${prod} or a git SHA tag, not ${app}:dev or ${app}:latest.`),
    productionStep('Scan image vulnerabilities', 'manual', 'Block critical vulnerabilities before production.', [`trivy image ${prod}`, `trivy image \\\n  --severity HIGH,CRITICAL \\\n  --exit-code 1 \\\n  ${prod}`, `grype ${prod}`], 'No unaccepted CRITICAL vulnerability remains and the report is stored in CI/CD artifacts.'),
    productionStep('Generate SBOM', 'manual', 'Produce the software inventory for the image.', [`syft ${prod} \\\n  -o cyclonedx-json > sbom-${app}.json`, `trivy image \\\n  --format cyclonedx \\\n  --output sbom-${app}.json \\\n  ${prod}`], 'An SBOM file is generated and archived with the release.'),
    productionStep('Check secrets handling', 'manual', 'Verify no secret is stored in clear text in Git, app.yaml, ConfigMap or manifests.', ['gitleaks detect --source . --verbose', 'grep -RniE "password|passwd|secret|token|api_key|apikey|private_key" .', `grep -RniE "password|passwd|secret|token|api_key|apikey|private_key" ${generated}`, `kubectl get secrets -n ${ns}`], 'No clear-text secret; use Kubernetes Secret, External Secrets, Vault, Sealed Secrets or equivalent.'),
    productionStep('Review RBAC', 'manual', 'Limit Kubernetes permissions.', [`kubectl get serviceaccount -n ${ns}`, `kubectl get role,rolebinding -n ${ns}`, `kubectl get clusterrolebinding | grep ${ns}`, `kubectl auth can-i --list -n ${ns}`, `kubectl auth can-i --list \\\n  -n ${ns} \\\n  --as=system:serviceaccount:${ns}:${serviceAccount}`], 'No abusive default ServiceAccount, no cluster-admin, minimal permissions.'),
    productionStep('Review NetworkPolicy', 'manual', 'Limit network ingress and egress.', [`kubectl get networkpolicy -n ${ns}`, `kubectl describe networkpolicy -n ${ns}`], 'NetworkPolicy exists where applicable and ingress/egress flows are documented.', 'No NetworkPolicy found. Review whether this workload should be isolated.'),
    productionStep('Validate resources', 'manual', 'Verify CPU/RAM requests and limits.', [`grep -Rni "resources:" ${generated}`, `kubectl top pods -n ${ns}`, `kubectl describe pod -n ${ns} ${podName}`], 'Requests and limits are defined; no OOMKill; values match real usage.'),
    productionStep('Validate probes', notWeb ? 'not applicable' : 'manual', 'Verify long-running applications expose useful health probes.', [`grep -RniE "readinessProbe|livenessProbe|startupProbe" ${generated}`, `kubectl describe pod -n ${ns} ${podName}`], notWeb ? `${workload}: probes are often not applicable; review backoff/history settings instead.` : 'Deployment has readinessProbe and livenessProbe where appropriate.'),
    productionStep('Validate storage / PVC / backups', 'manual', 'Avoid data loss.', [`grep -RniE "persistentVolumeClaim|volumeMounts|emptyDir|hostPath" ${generated}`, `kubectl get pvc -n ${ns}`, 'kubectl get pv'], 'No critical data is only written inside the container; PVC and backup/restore are documented if needed.'),
    productionStep('Validate ingress / DNS / TLS', notWeb ? 'not applicable' : 'manual', 'Validate network exposure for web/API workloads.', [`kubectl get svc -n ${ns}`, `kubectl get ingress -n ${ns}`, `kubectl describe ingress -n ${ns}`, `nslookup ${dnsName}`, `curl -I https://${dnsName}`], notWeb ? 'Not applicable unless the job exposes a service.' : 'DNS resolves, TLS is active, certificate is valid, HTTPS redirection is reviewed.'),
    productionStep('Validate monitoring / logging', 'manual', 'Ensure the application is observable.', [`kubectl logs -n ${ns} ${podName}`, `kubectl get events -n ${ns} --sort-by=.lastTimestamp`, `kubectl top pods -n ${ns}`, `kubectl get servicemonitor -n ${ns}`], 'Logs are readable, errors visible, metrics and alerts reviewed outside Studio.'),
    productionStep('Define rollback plan', 'manual', 'Know how to revert before production.', [`kubectl rollout history deployment/${app} -n ${ns}`, `kubectl rollout undo deployment/${app} -n ${ns}`, `kubectl delete job ${app} -n ${ns}`, `kubectl apply -f ${previous}`], 'Previous version and image are known; rollback procedure is documented.'),
    productionStep('Confirm target Kubernetes context', 'manual', 'Avoid deploying to the wrong cluster.', ['kubectl config current-context', 'kubectl cluster-info', `kubectl get namespace ${ns}`], `Context ${productionContext()} and namespace ${ns} are explicitly validated.`, 'If the context contains prod, production or live, human approval is required.'),
    productionStep('Human approval before production', 'manual', 'Block production without human review.', ['git status --short', 'git log --oneline -5', `kubectl diff -f ${generated}`, `kubectl apply --dry-run=server -f ${generated}`], 'Diff reviewed, server dry-run OK, explicit approval, rollback plan known.'),
  ];
  const root = $('production-checklist');
  root.innerHTML = '';
  for (const step of steps) {
    const details = document.createElement('details');
    details.className = 'production-step';
    const summary = document.createElement('summary');
    summary.textContent = `${step.title} [${step.status}]`;
    details.appendChild(summary);
    const why = document.createElement('p');
    why.textContent = `Why: ${step.why}`;
    details.appendChild(why);
    for (const command of step.commands) {
      const row = document.createElement('div');
      row.className = 'production-command';
      const pre = document.createElement('pre');
      pre.textContent = normalizeMultiline(command);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'copy-command';
      button.textContent = 'Copy command';
      button.dataset.command = command;
      row.appendChild(pre);
      row.appendChild(button);
      details.appendChild(row);
    }
    const expected = document.createElement('p');
    expected.textContent = `Expected result: ${step.expected}`;
    details.appendChild(expected);
    if (step.warning) {
      const warning = document.createElement('p');
      warning.textContent = `Warning: ${step.warning}`;
      details.appendChild(warning);
    }
    root.appendChild(details);
  }
}

function renderActionResult(path, result) {
  const job = result.job || {};
  const status = jobOk(job) ? 'ok' : 'failed';
  const key = actionResultKey(path);
  if (path === '/api/docker/build') {
    showResult(
      jobOk(job) ? '[OK] Docker image built' : '[FAILED] Docker build failed',
      [
        `image: ${result.image || 'review-required'}`,
        `command: ${commandLine(job)}`,
        `next: ${jobOk(job) ? 'Load image into kind' : 'Review Docker build output'}`,
      ],
      status,
      key,
    );
  } else if (path === '/api/kind/load') {
    showResult(
      jobOk(job) ? '[OK] Image loaded into kind' : '[FAILED] Kind image load failed',
      [
        `image: ${result.image || 'review-required'}`,
        jobOk(job) ? `cluster: ${result.cluster || preferredKindCluster || 'review-required'}` : `cluster attempted: ${result.cluster || preferredKindCluster || 'review-required'}`,
        result.reason ? `reason: ${result.reason}` : '',
        `command: ${commandLine(job)}`,
        `next: ${jobOk(job) ? 'Run dry-run' : 'Select an existing Kind cluster or create one'}`,
      ],
      status,
      key,
    );
  } else if (path === '/api/dry-run') {
    showResult(
      jobOk(job) ? '[OK] Kubernetes dry-run succeeded' : '[FAILED] Kubernetes dry-run failed',
      [
        `command: ${commandLine(job)}`,
        `next: ${jobOk(job) ? 'Deploy' : 'Review manifests and rerun dry-run'}`,
      ],
      status,
      key,
    );
  } else if (path === '/api/deploy') {
    if (result.deploy_status === 'blocked_existing_job') {
      showResult(
        '[BLOCKED] Existing Job must be deleted before redeploy',
        [
          `job: ${result.job_name || appName(lastState)}`,
          `namespace: ${result.namespace || namespaceName(lastState)}`,
          'reason: Kubernetes Job spec.template is immutable',
          'next: Delete existing Job and redeploy',
        ],
        'failed',
        key,
      );
    } else {
      showResult(
        result.deploy_status === 'succeeded' ? '[OK] Deploy completed' : '[FAILED] Deploy failed',
        [
          result.deploy_status === 'succeeded' ? `namespace: ${result.namespace || namespaceName(lastState)}` : '',
          result.deploy_status === 'succeeded' ? `manifests: ${result.manifests_dir || generatedK8sDir(lastState)}` : '',
          `command: ${result.command || commandLine(job)}`,
          result.reason ? `reason: ${result.reason}` : '',
          `next: ${result.next_action || (result.deploy_status === 'succeeded' ? 'Run Status, then read logs.' : 'Delete existing Job and redeploy, or delete the Job manually.')}`,
        ],
        result.deploy_status === 'succeeded' ? 'ok' : 'failed',
        key,
      );
    }
  } else if (path === '/api/deploy/job/redeploy') {
    if (result.deploy_status === 'succeeded') {
      showResult(
        '[DONE] Existing Job deleted',
        [`command: ${result.delete_command || commandLine(result.delete_job)}`],
        'ok',
        'job-redeploy-delete',
      );
      showResult(
        '[DONE] Manifests applied',
        [`command: ${result.apply_command || commandLine(job)}`],
        'ok',
        'job-redeploy-apply',
      );
    }
    showResult(
      result.deploy_status === 'succeeded' ? '[OK] Deploy completed' : '[FAILED] Delete existing Job and redeploy failed',
      [
        `job: ${result.job_name || appName(lastState)}`,
        `namespace: ${result.namespace || namespaceName(lastState)}`,
        `delete command: ${result.delete_command || commandLine(result.delete_job)}`,
        `apply command: ${result.apply_command || commandLine(job)}`,
        result.reason ? `reason: ${result.reason}` : '',
        `next: ${result.next_action || (result.deploy_status === 'succeeded' ? 'Run Status, then read logs.' : 'Review delete/apply output')}`,
      ],
      result.deploy_status === 'succeeded' ? 'ok' : 'failed',
      result.deploy_status === 'succeeded' ? 'deploy' : key,
    );
  } else if (path === '/api/scaffold/app-yaml') {
    showResult('[OK] app.yaml created', [`path: ${result.path}`, 'next: Run Check'], 'ok', key);
  } else if (path === '/api/check') {
    showResult('[OK] Check completed', ['next: Run Explain or Render'], 'ok', key);
  } else if (path === '/api/explain') {
    showResult('[OK] Explain completed', ['next: Review explanation, then Render'], 'ok', key);
  } else if (path === '/api/render') {
    showResult(
      '[OK] Manifests rendered',
      [
        `generated_k8s_dir: ${result.output_dir || 'review-required'}`,
        'next: Run Dry-run',
      ],
      'ok',
      key,
    );
  } else if (path === '/api/logs') {
    if (result.logs !== undefined) {
      $('logs-output').textContent = normalizeMultiline(result.logs || '');
    }
    showResult(
      jobOk(job) ? '[OK] Logs loaded' : '[FAILED] Logs failed',
      [
        `workload: ${result.workload_type || workloadType(lastState)}`,
        `namespace: ${result.namespace || namespaceName(lastState)}`,
        `command: ${result.command || commandLine(job)}`,
        result.reason ? `reason: ${result.reason}` : '',
        `next: ${result.next_action || (jobOk(job) ? 'Review logs and production handoff checklist' : 'Run Status and inspect pod/job state.')}`,
      ],
      status,
      key,
    );
  } else if (path === '/api/status') {
    showResult(
      jobOk(job) ? '[OK] Status completed' : '[FAILED] Status failed',
      [`command: ${commandLine(job)}`, `next: ${jobOk(job) ? 'Read logs.' : 'Review Kubernetes status output'}`],
      status,
      key,
    );
  }
}

function setActionState(snapshot) {
  const appYamlReady = hasAppYaml(snapshot);
  const manifestsReady = Boolean(snapshot.state.generated_k8s_dir);
  const dockerfileExists = Boolean(snapshot.dockerfile && snapshot.dockerfile.exists);

  const running = anyActionRunning();
  $('check').disabled = running || !appYamlReady;
  $('explain').disabled = running || !appYamlReady;
  $('save-yaml').disabled = running || !appYamlReady;
  $('render').disabled = running || !appYamlReady;
  $('dry-run').disabled = running || !appYamlReady || !manifestsReady;
  $('deploy').disabled = running || !snapshot.deploy_allowed || Boolean(snapshot.state.deploy_blocked_reason);
  const showJobRedeploy = workloadType(snapshot) === 'job' && snapshot.state.deploy_status === 'blocked_existing_job';
  $('job-redeploy').hidden = !showJobRedeploy;
  $('job-redeploy').disabled = running || !showJobRedeploy;
  $('docker-build').disabled = running || !appYamlReady || !dockerfileExists;
  $('kind-load').disabled = running || !appYamlReady || !preferredKindCluster;
  $('status').disabled = running || !appYamlReady;
  const logsReady = snapshot.state.deploy_status === 'succeeded' && appYamlReady && Boolean(appContext(snapshot).name) && Boolean(appContext(snapshot).namespace) && Boolean(appContext(snapshot).workload_type);
  $('read-logs').disabled = running || !logsReady;
  $('refresh-logs').disabled = running || !logsReady;

  if (snapshot.paths) {
    $('studio-output-path').value = snapshot.paths.studio_output_dir || '';
    $('generated-discovery-path').textContent = snapshot.paths.generated_discovery_dir || '';
    $('generated-k8s-path').textContent = snapshot.paths.generated_k8s_dir || '';
  }

  const clusterText = preferredKindCluster
    ? `Kind cluster: ${preferredKindCluster}`
    : 'No kind cluster found';
  $('kind-cluster-status').textContent = clusterText;
  $('kind-cluster').value = preferredKindCluster;

  const deployStatus = snapshot.state.deploy_blocked_reason
    ? `Deploy blocked: ${snapshot.state.deploy_blocked_reason}. Next: ${snapshot.state.deploy_blocked_next_action}`
    : (snapshot.deploy_allowed ? 'Deploy allowed after dry-run and confirmation.' : `Deploy locked: ${snapshot.deploy_reason}`);
  $('deploy-status').textContent = deployStatus;

  $('scaffold-required').hidden = !snapshot.state.needs_scaffold;
  $('scaffold').classList.toggle('attention', Boolean(snapshot.state.needs_scaffold));
  $('current-state').textContent = snapshot.current_state || snapshot.state.state;
  $('next-action').textContent = snapshot.next_action || 'Run Discover.';

  $('dockerfile-status').textContent = dockerfileExists
    ? `Existing Dockerfile detected: ${snapshot.dockerfile.path}`
    : 'No Dockerfile detected. Review a proposal before writing one.';
  $('dockerfile-proposal').textContent = dockerfileExists ? 'Use existing Dockerfile' : 'Dockerfile proposal';
  $('write-dockerfile').disabled = dockerfileExists;
  $('overwrite-dockerfile').disabled = !dockerfileExists;
}

async function loadScaffoldDefaults(announce = true) {
  const defaults = await json('/api/scaffold/defaults');
  $('scaffold-app-name').value = defaults.app_name || '';
  $('scaffold-namespace').value = defaults.namespace || '';
  $('scaffold-image').value = defaults.image || '';
  $('scaffold-workload-type').value = defaults.workload_type || 'job';
  $('scaffold-startup-command').value = defaults.startup_command || '';
  $('scaffold-container-port').value = defaults.container_port || '';
  $('scaffold-service-enabled').checked = Boolean(defaults.service_enabled);
  $('scaffold-ingress-enabled').checked = Boolean(defaults.ingress_enabled);
  $('scaffold-restart-policy').value = defaults.restart_policy || 'OnFailure';
  $('scaffold-schedule').value = defaults.schedule || '';
  $('scaffold-persistence').checked = Boolean(defaults.persistence_required);
  if (announce) log(`[scaffold] ${defaults.message || 'review required'}`);
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
  const snapshot = await json('/api/state');
  lastState = snapshot;
  $('state').textContent = renderStateSnapshot(snapshot);
  setText('warnings', await text('/api/discovery/warnings'));
  setText('report', await text('/api/discovery/report'));
  $('app-yaml').value = await text('/api/app-yaml');
  if (snapshot.state.last_explain) setText('explain-output', snapshot.state.last_explain);
  if (snapshot.state.last_logs) setText('logs-output', snapshot.state.last_logs);
  setActionState(snapshot);
  if (snapshot.state.needs_scaffold && !$('scaffold-app-name').value) {
    await loadScaffoldDefaults(false);
  }
  renderReadinessMemo(snapshot);
  renderProductionChecklist(snapshot);
}

async function loadKindClusters() {
  try {
    const payload = await json('/api/kind/clusters');
    kindClusters = payload.clusters || [];
    preferredKindCluster = payload.preferred || '';
    const select = $('kind-cluster');
    select.innerHTML = '';
    for (const cluster of kindClusters) {
      const option = document.createElement('option');
      option.value = cluster;
      option.textContent = cluster;
      select.appendChild(option);
    }
    if (preferredKindCluster) {
      select.value = preferredKindCluster;
    }
    $('kind-load').disabled = !hasAppYaml(lastState || { state: {} }) || !preferredKindCluster;
    $('kind-cluster-status').textContent = preferredKindCluster
      ? `Kind cluster: ${preferredKindCluster}`
      : 'No kind cluster found';
  } catch (error) {
    preferredKindCluster = '';
    kindClusters = [];
    $('kind-cluster').innerHTML = '';
    $('kind-cluster-status').textContent = 'No kind cluster found';
    $('kind-load').disabled = true;
    logError(error);
  }
}

async function pollJobs() {
  const payload = await json('/api/jobs');
  let running = false;
  for (const job of payload.jobs || []) {
    const previous = seenJobStatuses.get(job.id);
    if (previous !== job.status) {
      log(`[job] ${job.type} ${job.status}`);
      seenJobStatuses.set(job.id, job.status);
    }
    if (job.status === 'queued' || job.status === 'running') running = true;
  }
  await refresh();
  if (!running && pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

function ensurePolling() {
  pollingEnabled = true;
  if (!pollingTimer) {
    pollingTimer = setInterval(() => pollJobs().catch(logError), 1500);
  }
}

async function post(path, body = {}) {
  if (activeActions.has(path)) {
    log(`[studio] ${path} already running; duplicate click ignored.`);
    return {};
  }
  setActionRunning(path, true);
  if (lastState) setActionState(lastState);
  try {
    log(`[studio] POST ${path}`);
    const result = await json(path, { method: 'POST', body: JSON.stringify(body) });
    if (result.message) log(result.message);
    if (result.next_action) log(result.next_action);
    renderActionResult(path, result);
    await refresh();
    if (pollingEnabled || !websocketReady) ensurePolling();
    return result;
  } finally {
    setActionRunning(path, false);
    if (lastState) setActionState(lastState);
  }
}

$('select-repo').onclick = () => post('/api/repo/local', { path: $('repo-path').value }).catch(logError);
$('clone-repo').onclick = () => post('/api/repo/clone', { url: $('repo-url').value }).catch(logError);
$('discover').onclick = () => post('/api/discover').catch(logError);
$('load-scaffold-defaults').onclick = () => loadScaffoldDefaults().catch(logError);
$('create-scaffold').onclick = () => post('/api/scaffold/app-yaml', scaffoldPayload()).catch(logError);
$('dockerfile-proposal').onclick = async () => {
  try {
    if (lastState && lastState.dockerfile && lastState.dockerfile.exists) {
      log(`[dockerfile] Using existing Dockerfile: ${lastState.dockerfile.path}`);
      return;
    }
    $('dockerfile-text').value = await text('/api/dockerfile/proposal');
    log('[dockerfile] Proposal loaded. Review before writing.');
  } catch (e) {
    logError(e);
  }
};
$('write-dockerfile').onclick = () => {
  if (confirm('Write Dockerfile to the selected repository?')) {
    post('/api/dockerfile/write', { confirm: true, overwrite: false, content: $('dockerfile-text').value }).catch(logError);
  }
};
$('overwrite-dockerfile').onclick = () => {
  const confirmation = prompt('Type OVERWRITE DOCKERFILE to replace the existing Dockerfile');
  if (confirmation === 'OVERWRITE DOCKERFILE') {
    post('/api/dockerfile/write', {
      confirm: true,
      overwrite: true,
      overwrite_confirmation: confirmation,
      content: $('dockerfile-text').value,
    }).catch(logError);
  } else {
    log('[dockerfile] Overwrite cancelled. Existing Dockerfile kept.');
  }
};
$('check').onclick = () => post('/api/check').catch(logError);
$('explain').onclick = async () => {
  try {
    const r = await post('/api/explain');
    if (r.explain !== undefined) {
      $('explain-output').textContent = normalizeMultiline(r.explain || '');
    }
  } catch (e) {
    logError(e);
  }
};
$('save-yaml').onclick = () => post('/api/app-yaml', { content: $('app-yaml').value }).catch(logError);
$('render').onclick = () => post('/api/render').catch(logError);
$('docker-build').onclick = () => post('/api/docker/build').catch(logError);
$('refresh-kind-clusters').onclick = () => loadKindClusters().catch(logError);
$('copy-output-path').onclick = () => {
  const value = $('studio-output-path').value;
  if (navigator.clipboard && value) {
    navigator.clipboard.writeText(value).then(() => log('[paths] Studio output path copied')).catch(logError);
  } else {
    log(`[paths] ${value}`);
  }
};
$('kind-cluster').onchange = () => { preferredKindCluster = $('kind-cluster').value; };
$('kind-load').onclick = () => {
  const image = prompt('Image to load into kind');
  const cluster = $('kind-cluster').value || preferredKindCluster;
  if (image && cluster) post('/api/kind/load', { image, cluster }).catch(logError);
  if (image && !cluster) logError(new Error('No kind cluster found'));
};
$('dry-run').onclick = () => post('/api/dry-run').catch(logError);
$('deploy').onclick = () => {
  if (confirm('Run kubectl apply now?')) post('/api/deploy', { confirm: true }).catch(logError);
};
$('job-redeploy').onclick = async () => {
  const confirmation = await promptRedeployConfirmation();
  if (confirmation === 'DELETE JOB AND REDEPLOY') {
    const job = appName(lastState);
    const ns = namespaceName(lastState);
    const manifests = generatedK8sDir(lastState);
    showResult(
      '[RUNNING] Deleting existing Job',
      [`command: kubectl delete job ${job} -n ${ns} --ignore-not-found`],
      'info',
      'job-redeploy-delete',
    );
    showResult(
      '[RUNNING] Applying manifests',
      [`command: kubectl apply -f ${manifests}`],
      'info',
      'job-redeploy-apply',
    );
    post('/api/deploy/job/redeploy', { confirmation }).catch(logError);
  } else {
    showResult(
      '[CANCELLED] Delete existing Job and redeploy cancelled',
      [
        `job: ${appName(lastState)}`,
        `namespace: ${namespaceName(lastState)}`,
        'expected confirmation: DELETE JOB AND REDEPLOY',
        'next: Existing Job is still present. Confirm delete-and-redeploy or delete it manually.',
      ],
      'failed',
      'job-redeploy',
    );
    log('[deploy] Confirmation text did not match. No Job was deleted.');
  }
};
$('status').onclick = () => post('/api/status').catch(logError);
$('read-logs').onclick = () => post('/api/logs').catch(logError);
$('refresh-logs').onclick = () => post('/api/logs').catch(logError);

document.addEventListener('click', (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement) || !target.classList.contains('copy-command')) return;
  const command = target.dataset.command || '';
  if (navigator.clipboard && command) {
    navigator.clipboard.writeText(command).then(() => log('[production] Command copied')).catch(logError);
  } else if (command) {
    log(`[production command] ${command}`);
  }
});

for (const id of ['prod-registry', 'prod-release-tag', 'prod-context']) {
  const element = $(id);
  if (element) element.oninput = () => { if (lastState) renderProductionChecklist(lastState); };
}

try {
  const ws = new WebSocket(`ws://${location.host}/ws/jobs`);
  ws.onopen = () => {
    websocketReady = true;
    $('streaming-warning').hidden = true;
  };
  ws.onerror = () => {
    if (!websocketReady) showStreamingWarning();
    ensurePolling();
  };
  ws.onclose = () => {
    if (!websocketReady) showStreamingWarning();
    ensurePolling();
  };
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event === 'job_log' && data.line) {
      log(`[${data.stream || 'job'}] ${data.line}`);
    } else if (data.event && data.event.startsWith('job_')) {
      log(`[job technical] ${data.event} ${data.job_id || ''}`.trim());
    } else {
      log(JSON.stringify(data, null, 2));
    }
  };
} catch (error) {
  showStreamingWarning();
  ensurePolling();
}

refresh().then(() => loadKindClusters()).catch(logError);
