const state = {
  project: null,
  workflows: [],
  selectedWorkflow: null,
  selectedRun: null,
  runs: [],
  activeTab: "logs",
  theme: "light",
};

const el = (id) => document.getElementById(id);

function showToast(message) {
  const toast = el("toast");
  toast.textContent = message;
  toast.hidden = false;
  setTimeout(() => {
    toast.hidden = true;
  }, 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data.detail ? data.detail : response.statusText;
    throw new Error(detail);
  }
  return data;
}

async function init() {
  initTheme();
  bindEvents();
  await loadRoot();
  connectEvents();
}

function bindEvents() {
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.addEventListener("click", () => setTheme(button.dataset.themeChoice));
  });
  el("refreshButton").addEventListener("click", refresh);
  el("openProjectEditorButton").addEventListener("click", openProjectEditor);
  el("statusButton").addEventListener("click", loadSelectedWorkflowData);
  el("runActionButton").addEventListener("click", runSelectedAction);
  el("openEditorButton").addEventListener("click", openSelectedRunEditor);
  el("stopRunButton").addEventListener("click", stopSelectedRun);
  el("createWorkflowButton").addEventListener("click", () => el("workflowDialog").showModal());
  el("bootstrapButton").addEventListener("click", bootstrapWorkflow);
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      document.querySelectorAll("[data-tab]").forEach((tab) => tab.classList.remove("active"));
      button.classList.add("active");
      loadRunOutput();
    });
  });
}

function initTheme() {
  const stored = localStorage.getItem("solo-theme");
  const theme = stored === "dark" || stored === "light" ? stored : "light";
  setTheme(theme, { persist: false });
}

function setTheme(theme, options = {}) {
  if (theme !== "dark" && theme !== "light") return;
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  if (options.persist !== false) {
    localStorage.setItem("solo-theme", theme);
  }
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    const active = button.dataset.themeChoice === theme;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

async function loadRoot() {
  const bootstrap = window.SOLO_BOOTSTRAP;
  if (bootstrap && bootstrap.project) {
    state.project = bootstrap.project;
    state.workflows = bootstrap.workflows || [];
    state.runs = bootstrap.runs || [];
    renderProject();
    renderWorkflows();
    renderRuns();
    if (state.workflows.length > 0) {
      selectWorkflow(state.workflows[0]);
      return;
    }
  }
  if (!state.project) {
    throw new Error("Missing Jinja2 bootstrap data");
  }
  await refresh();
}

async function refresh() {
  if (!state.project) return;
  const data = await api(`/api/projects/${state.project.id}/refresh`, { method: "POST", body: "{}" });
  state.project = data.project;
  state.workflows = data.workflows || [];
  state.runs = await api("/api/runs");
  renderProject();
  renderWorkflows();
  renderRuns();
  if (state.workflows.length > 0) {
    const keep = state.workflows.find((workflow) => workflow.id === state.selectedWorkflow?.id);
    selectWorkflow(keep || state.workflows[0]);
  } else {
    state.selectedWorkflow = null;
    renderWorkflowDetail();
  }
}

function renderProject() {
  if (!state.project) return;
  el("projectPath").textContent = state.project.rootPath;
  el("branchValue").textContent = state.project.activeBranch || "detached";
  el("defaultBranchValue").textContent = state.project.defaultBranch || "-";
  el("workflowCountValue").textContent = String(state.workflows.length);
  api(`/api/projects/${state.project.id}/git`)
    .then((git) => {
      el("dirtyValue").textContent = git.dirty || "-";
    })
    .catch(() => {
      el("dirtyValue").textContent = "unknown";
    });
}

function renderWorkflows() {
  const list = el("workflowList");
  list.innerHTML = "";
  if (state.workflows.length === 0) {
    list.innerHTML = `<div class="muted">No workflows</div>`;
    return;
  }
  state.workflows.forEach((workflow) => {
    const button = document.createElement("button");
    button.className = "workflow-item";
    if (workflow.id === state.selectedWorkflow?.id) button.classList.add("active");
    button.innerHTML = `
      <strong>${escapeHtml(workflow.title || workflow.id)}</strong>
      <span class="muted">${escapeHtml(workflow.id)} · ${escapeHtml(workflow.scopeType || "global")}</span>
    `;
    button.addEventListener("click", () => selectWorkflow(workflow));
    list.appendChild(button);
  });
}

async function selectWorkflow(workflow) {
  state.selectedWorkflow = workflow;
  state.selectedRun = null;
  renderWorkflows();
  renderWorkflowDetail();
  await loadSelectedWorkflowData();
}

function renderWorkflowDetail() {
  const workflow = state.selectedWorkflow;
  el("workflowTitle").textContent = workflow ? workflow.title : "No workflow selected";
  el("workflowDescription").textContent = workflow ? workflow.description || "" : "";
  el("workflowMeta").textContent = workflow
    ? `${workflow.scopeType || "global"} · ${workflow.definitionPath || ""}`
    : "";

  const actionSelect = el("actionSelect");
  actionSelect.innerHTML = "";
  if (!workflow || !workflow.actions || workflow.actions.length === 0) {
    actionSelect.innerHTML = `<option value="">No actions</option>`;
    return;
  }
  workflow.actions.forEach((action) => {
    const option = document.createElement("option");
    option.value = action.id;
    option.textContent = action.title || action.id;
    actionSelect.appendChild(option);
  });
}

async function loadSelectedWorkflowData() {
  const workflow = state.selectedWorkflow;
  if (!workflow) {
    el("statusOutput").textContent = "";
    el("itemsBody").innerHTML = "";
    return;
  }
  try {
    const [status, items] = await Promise.all([
      api(`/api/workflows/${workflow.id}/status`, { method: "POST", body: "{}" }),
      api(`/api/workflows/${workflow.id}/items`),
    ]);
    el("statusOutput").textContent = JSON.stringify(status, null, 2);
    renderItems(items || []);
  } catch (error) {
    showToast(error.message);
  }
}

function renderItems(items) {
  el("itemCount").textContent = String(items.length);
  const body = el("itemsBody");
  body.innerHTML = "";
  if (items.length === 0) {
    body.innerHTML = `<tr><td colspan="5" class="muted">No work items</td></tr>`;
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><button class="linkish" data-work-item="${escapeAttr(item.externalId)}">${escapeHtml(item.externalId)}</button></td>
      <td>${escapeHtml(item.title)}</td>
      <td>${statusPill(item.status)}</td>
      <td>${escapeHtml(item.scopeType || "")}${item.scopeRef ? ` · ${escapeHtml(item.scopeRef)}` : ""}</td>
      <td>${escapeHtml(item.sourcePath || "")}</td>
    `;
    row.querySelector("[data-work-item]").addEventListener("click", () => {
      el("workItemInput").value = item.externalId;
    });
    body.appendChild(row);
  });
}

async function runSelectedAction() {
  const workflow = state.selectedWorkflow;
  const actionId = el("actionSelect").value;
  if (!workflow || !actionId) return;
  const inputs = parseInputPairs(el("inputPairs").value);
  const body = {
    dryRun: el("dryRunInput").checked,
    inputs,
  };
  const workItemId = el("workItemInput").value.trim();
  if (workItemId) body.workItemId = workItemId;

  try {
    const run = await api(`/api/workflows/${workflow.id}/actions/${actionId}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    state.runs.unshift(run);
    state.selectedRun = run;
    renderRuns();
    await loadRunOutput();
    await loadSelectedWorkflowData();
    showToast(`Run ${run.status}: ${run.id}`);
  } catch (error) {
    showToast(error.message);
  }
}

function renderRuns() {
  const list = el("runList");
  list.innerHTML = "";
  if (state.runs.length === 0) {
    list.innerHTML = `<div class="muted">No runs</div>`;
    return;
  }
  state.runs.forEach((run) => {
    const button = document.createElement("button");
    button.className = "run-item";
    if (run.id === state.selectedRun?.id) button.classList.add("active");
    button.innerHTML = `
      <strong>${escapeHtml(run.actionId)} ${statusPill(run.status)}</strong>
      <span class="muted">${escapeHtml(run.id)} · ${escapeHtml(run.runner)} · ${escapeHtml(run.returnCode ?? "")}</span>
    `;
    button.addEventListener("click", async () => {
      state.selectedRun = run;
      renderRuns();
      await loadRunOutput();
    });
    list.appendChild(button);
  });
}

async function loadRunOutput() {
  const run = state.selectedRun;
  if (!run) {
    el("runOutput").textContent = "";
    return;
  }
  try {
    const output = await api(`/api/runs/${run.id}/${state.activeTab}`);
    el("runOutput").textContent = output || "";
  } catch (error) {
    showToast(error.message);
  }
}

async function openSelectedRunEditor() {
  const run = state.selectedRun;
  if (!run) return;
  try {
    const editor = await api(`/api/runs/${run.id}/open-editor`, { method: "POST", body: "{}" });
    window.open(editor.url, "_blank", "noopener,noreferrer");
  } catch (error) {
    showToast(error.message);
  }
}

async function openProjectEditor() {
  if (!state.project) return;
  try {
    const editor = await api(`/api/projects/${state.project.id}/open-editor`, {
      method: "POST",
      body: "{}",
    });
    window.open(editor.url, "_blank", "noopener,noreferrer");
  } catch (error) {
    showToast(error.message);
  }
}

async function stopSelectedRun() {
  const run = state.selectedRun;
  if (!run) return;
  try {
    const stopped = await api(`/api/runs/${run.id}/stop`, { method: "POST", body: "{}" });
    const index = state.runs.findIndex((item) => item.id === stopped.id);
    if (index >= 0) state.runs[index] = stopped;
    state.selectedRun = stopped;
    renderRuns();
    showToast(`Run ${stopped.status}: ${stopped.id}`);
  } catch (error) {
    showToast(error.message);
  }
}

async function bootstrapWorkflow(event) {
  event.preventDefault();
  const goal = el("workflowGoal").value.trim();
  if (!goal) return;
  try {
    const run = await api(`/api/projects/${state.project.id}/workflows/bootstrap`, {
      method: "POST",
      body: JSON.stringify({
        goal,
        dryRun: el("workflowDryRun").checked,
      }),
    });
    state.runs.unshift(run);
    state.selectedRun = run;
    renderRuns();
    await loadRunOutput();
    el("workflowDialog").close();
    showToast(`Bootstrap ${run.status}: ${run.id}`);
  } catch (error) {
    showToast(error.message);
  }
}

function connectEvents() {
  if (!window.EventSource) return;
  const events = new EventSource("/api/events");
  events.addEventListener("workflow_status_updated", () => loadSelectedWorkflowData());
  events.addEventListener("run_completed", (event) => updateRunFromEvent(event));
  events.addEventListener("run_failed", (event) => updateRunFromEvent(event));
}

function updateRunFromEvent(event) {
  try {
    const parsed = JSON.parse(event.data);
    const run = parsed.payload?.run;
    if (!run) return;
    const index = state.runs.findIndex((item) => item.id === run.id);
    if (index >= 0) state.runs[index] = run;
    if (state.selectedRun?.id === run.id) state.selectedRun = run;
    renderRuns();
    loadRunOutput();
  } catch {
    return;
  }
}

function parseInputPairs(value) {
  const output = {};
  value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach((part) => {
      const index = part.indexOf("=");
      if (index > 0) output[part.slice(0, index).trim()] = part.slice(index + 1).trim();
    });
  return output;
}

function statusPill(status) {
  const safe = escapeHtml(String(status || "unknown"));
  return `<span class="status ${escapeAttr(String(status || "").toLowerCase())}">${safe}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll(" ", "-");
}

init().catch((error) => showToast(error.message));
