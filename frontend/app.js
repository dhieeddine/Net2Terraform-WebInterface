const API_BASE = "http://localhost:8000";

const steps = ["Upload", "YOLO detection", "LLM generation", "Download"];
const badgeColors = {
  router: "bg-purple-100 text-purple-800 border-purple-300",
  switch: "bg-green-100 text-green-800 border-green-300",
  pc: "bg-amber-100 text-amber-800 border-amber-300",
  server: "bg-red-100 text-red-800 border-red-300",
  firewall: "bg-yellow-100 text-yellow-800 border-yellow-300",
};

const stepper = document.getElementById("stepper");
const fileInput = document.getElementById("fileInput");
const dropZone = document.getElementById("dropZone");
const analyzeBtn = document.getElementById("analyzeBtn");
const progressPanel = document.getElementById("progressPanel");
const progressBar = document.getElementById("progressBar");
const progressValue = document.getElementById("progressValue");
const statusText = document.getElementById("statusText");
const badgeContainer = document.getElementById("badgeContainer");
const inputPreview = document.getElementById("inputPreview");
const annotatedPreview = document.getElementById("annotatedPreview");
const imageModal = document.getElementById("imageModal");
const imageModalContent = document.getElementById("imageModalContent");
const imageModalClose = document.getElementById("imageModalClose");
const terraformCode = document.getElementById("terraformCode");
const generateTerraformBtn = document.getElementById("generateTerraformBtn");
const copyBtn = document.getElementById("copyBtn");
const downloadBtn = document.getElementById("downloadBtn");
const validationPanel = document.getElementById("validationPanel");
const validationDetections = document.getElementById("validationDetections");
const validationLinks = document.getElementById("validationLinks");
const deployBtn = document.getElementById("deployBtn");
const destroyBtn = document.getElementById("destroyBtn");
const deployStatus = document.getElementById("deployStatus");
const deployJobId = document.getElementById("deployJobId");
const deployLogs = document.getElementById("deployLogs");
const resourceInfo = document.getElementById("resourceInfo");
const ocrNamesContainer = document.getElementById("ocrNamesContainer");
const regenerateTerraformBtn = document.getElementById("regenerateTerraformBtn");

let selectedFile = null;
let terraformOutput = "";
let lastDetections = [];
let lastLinks = [];
let lastOcrNames = {};
let currentDeployJobId = null;
let monitorTimer = null;

const terminalStatuses = new Set(["deployed", "failed", "destroyed"]);

function clearMonitor() {
  if (monitorTimer) {
    clearInterval(monitorTimer);
    monitorTimer = null;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function resetDeploymentUi() {
  clearMonitor();
  currentDeployJobId = null;
  deployJobId.textContent = "-";
  deployStatus.textContent = "Idle";
  deployLogs.textContent = "Waiting for deployment...";
  resourceInfo.textContent = "No resource information yet.";
  destroyBtn.disabled = true;
}

function renderState(statePayload) {
  const resources = statePayload?.state?.resources;
  if (!Array.isArray(resources) || !resources.length) {
    resourceInfo.textContent = "No resources discovered yet.";
    return;
  }

  const rows = resources
    .map(
      (resource) => `
      <tr>
        <td>${escapeHtml(resource.type || "-")}</td>
        <td>${escapeHtml(resource.name || "-")}</td>
        <td>${escapeHtml(resource.id || "-")}</td>
        <td>${escapeHtml(resource.public_ip || resource.private_ip || "-")}</td>
        <td>${escapeHtml(resource.state || "-")}</td>
      </tr>
    `,
    )
    .join("");

  resourceInfo.innerHTML = `
    <div class="overflow-auto">
      <table class="state-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Name</th>
            <th>ID</th>
            <th>IP</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

async function pollDeployment(jobId) {
  const [statusRes, logsRes, stateRes] = await Promise.all([
    fetch(`${API_BASE}/api/deploy/${jobId}`),
    fetch(`${API_BASE}/api/deploy/${jobId}/logs?tail=300`),
    fetch(`${API_BASE}/api/deploy/${jobId}/state`),
  ]);

  if (!statusRes.ok) {
    throw new Error("Failed to fetch deployment status.");
  }

  const statusData = await statusRes.json();
  const logsData = logsRes.ok ? await logsRes.json() : { logs: [] };
  const stateData = stateRes.ok ? await stateRes.json() : {};

  const status = statusData.status || "unknown";
  deployStatus.textContent = statusData.error ? `${status} - ${statusData.error}` : status;

  const logs = Array.isArray(logsData.logs) ? logsData.logs : [];
  deployLogs.textContent = logs.length ? logs.join("") : "No logs yet.";
  deployLogs.scrollTop = deployLogs.scrollHeight;

  renderState(stateData);

  destroyBtn.disabled = !["deployed", "applying", "initializing"].includes(status);

  if (terminalStatuses.has(status)) {
    clearMonitor();
  }
}

async function startMonitor(jobId) {
  clearMonitor();
  await pollDeployment(jobId);
  monitorTimer = setInterval(async () => {
    try {
      await pollDeployment(jobId);
    } catch (error) {
      deployStatus.textContent = `monitor_error - ${error.message}`;
      clearMonitor();
    }
  }, 2500);
}

async function startDeployment() {
  if (!terraformOutput) {
    alert("Generate Terraform first before deployment.");
    return;
  }

  deployBtn.disabled = true;
  deployStatus.textContent = "starting";
  deployLogs.textContent = "Submitting deploy job...";
  resourceInfo.textContent = "Collecting resource information...";

  try {
    const res = await fetch(`${API_BASE}/api/deploy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ terraform_code: terraformOutput }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Deployment request failed.");
    }

    const data = await res.json();
    currentDeployJobId = data.job_id;
    deployJobId.textContent = currentDeployJobId;

    await startMonitor(currentDeployJobId);
  } catch (error) {
    deployStatus.textContent = `failed_to_start - ${error.message}`;
    deployLogs.textContent = error.message;
  } finally {
    deployBtn.disabled = false;
  }
}

async function destroyDeployment() {
  if (!currentDeployJobId) {
    return;
  }

  destroyBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/api/deploy/${currentDeployJobId}/destroy`, {
      method: "POST",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Destroy request failed.");
    }
    deployStatus.textContent = "destroying";
    await startMonitor(currentDeployJobId);
  } catch (error) {
    deployStatus.textContent = `destroy_error - ${error.message}`;
  }
}

function renderStepper(activeIndex = 0) {
  stepper.innerHTML = "";
  steps.forEach((step, index) => {
    const el = document.createElement("div");
    el.className = `step ${index === activeIndex ? "active" : ""}`;
    el.innerHTML = `
      <div class="flex items-center gap-3">
        <span class="dot">${index + 1}</span>
        <span class="text-sm font-medium text-slate-700">${step}</span>
      </div>
    `;
    stepper.appendChild(el);
  });
}

function setProgress(percent, text) {
  progressBar.style.width = `${percent}%`;
  progressValue.textContent = `${Math.round(percent)}%`;
  statusText.textContent = text;
}

function setImagePreview(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    inputPreview.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function setFile(file) {
  if (!file) {
    return;
  }
  if (!["image/png", "image/jpeg", "image/jpg"].includes(file.type)) {
    alert("Only PNG and JPG are supported.");
    return;
  }
  selectedFile = file;
  analyzeBtn.disabled = false;
  generateTerraformBtn.disabled = true;
  setImagePreview(file);
  annotatedPreview.removeAttribute("src");
  terraformCode.textContent = "";
  terraformOutput = "";
  copyBtn.disabled = true;
  downloadBtn.disabled = true;
  badgeContainer.innerHTML = "";
  validationPanel.classList.add("hidden");
  lastDetections = [];
  lastLinks = [];
  lastOcrNames = {};
  renderOcrNames(lastOcrNames);
  regenerateTerraformBtn.disabled = true;
  resetDeploymentUi();
  renderStepper(0);
}

function renderOcrNames(ocrNames) {
  const entries = Object.entries(ocrNames || {});
  if (!entries.length) {
    ocrNamesContainer.textContent = "No OCR names detected yet.";
    return;
  }

  const rows = entries
    .map(
      ([nodeId, nodeName]) => `
        <div class="grid grid-cols-1 gap-2 rounded-lg border border-slate-200 bg-white p-2 sm:grid-cols-2">
          <label class="text-xs font-semibold uppercase tracking-wide text-slate-500">${escapeHtml(nodeId)}</label>
          <input
            data-ocr-node-id="${escapeHtml(nodeId)}"
            type="text"
            value="${escapeHtml(nodeName)}"
            class="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-800"
          />
        </div>
      `,
    )
    .join("");

  ocrNamesContainer.innerHTML = rows;
}

function collectOcrOverrides() {
  const overrides = {};
  const inputs = ocrNamesContainer.querySelectorAll("input[data-ocr-node-id]");
  inputs.forEach((input) => {
    const nodeId = input.getAttribute("data-ocr-node-id");
    const value = input.value.trim();
    if (nodeId && value) {
      overrides[nodeId] = value;
    }
  });
  return overrides;
}

async function analyzeImage(ocrOverrides = null) {
  if (!selectedFile) {
    return;
  }

  analyzeBtn.disabled = true;
  generateTerraformBtn.disabled = true;
  progressPanel.classList.remove("hidden");
  renderStepper(1);
  setProgress(5, "Running YOLO + OCR...");

  let current = 5;
  const timer = setInterval(() => {
    current = Math.min(current + 4, 88);
    const status = current < 45 ? "Running YOLO..." : "Running OCR...";
    setProgress(current, status);
  }, 350);

  try {
    const form = new FormData();
    form.append("file", selectedFile);

    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      body: form,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Analyze request failed.");
    }

    const data = await res.json();
    clearInterval(timer);
    setProgress(100, "Analysis completed");
    renderStepper(1);

    const detections = Array.isArray(data.detections) ? data.detections : [];
    const links = Array.isArray(data.links) ? data.links : [];
    
    lastDetections = detections;
    lastLinks = links;
    lastOcrNames = data.ocr_names && typeof data.ocr_names === "object" ? data.ocr_names : {};
    
    renderDetections(detections);
    renderValidation(detections, links);
    renderOcrNames(lastOcrNames);
    regenerateTerraformBtn.disabled = false;
    generateTerraformBtn.disabled = false;

    if (data.annotated_image) {
      annotatedPreview.src = `data:image/png;base64,${data.annotated_image}`;
    }

    terraformOutput = "";
    terraformCode.textContent = "";
    copyBtn.disabled = true;
    downloadBtn.disabled = true;
    deployBtn.disabled = true;
  } catch (error) {
    clearInterval(timer);
    setProgress(0, `Error: ${error.message}`);
    renderStepper(0);
    alert(error.message);
  } finally {
    analyzeBtn.disabled = false;
  }
}

async function generateTerraform(useEditedNames = false) {
  if (!selectedFile) {
    alert("Upload and analyze an image first.");
    return;
  }

  if (!lastDetections.length) {
    alert("Run Analyze Topology first.");
    return;
  }

  const overrides = useEditedNames ? collectOcrOverrides() : {};

  generateTerraformBtn.disabled = true;
  regenerateTerraformBtn.disabled = true;
  setProgress(8, "Calling LLM for Terraform generation...");
  progressPanel.classList.remove("hidden");
  renderStepper(2);

  try {
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("yolo_hints", JSON.stringify(lastDetections));
    form.append("topology_links", JSON.stringify(lastLinks));
    form.append("detected_ocr_names", JSON.stringify(lastOcrNames));
    form.append("ocr_name_overrides", JSON.stringify(overrides));

    const res = await fetch(`${API_BASE}/api/generate-terraform`, {
      method: "POST",
      body: form,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Terraform generation failed.");
    }

    const data = await res.json();
    terraformOutput = data.terraform || "";
    if (data.ocr_names && typeof data.ocr_names === "object") {
      lastOcrNames = data.ocr_names;
      renderOcrNames(lastOcrNames);
    }

    terraformCode.textContent = terraformOutput;
    hljs.highlightElement(terraformCode);
    copyBtn.disabled = terraformOutput.length === 0;
    downloadBtn.disabled = terraformOutput.length === 0;
    deployBtn.disabled = terraformOutput.length === 0;

    setProgress(100, "Terraform generation completed");
    renderStepper(3);
  } catch (error) {
    setProgress(0, `Error: ${error.message}`);
    renderStepper(1);
    alert(error.message);
  } finally {
    generateTerraformBtn.disabled = false;
    regenerateTerraformBtn.disabled = false;
  }
}

async function regenerateWithEditedNames() {
  await generateTerraform(true);
}

function renderDetections(detections) {
  badgeContainer.innerHTML = "";

  if (!detections.length) {
    badgeContainer.innerHTML = '<span class="text-slate-500">No components detected.</span>';
    return;
  }

  detections.forEach((detection) => {
    const normalized = String(detection).toLowerCase();
    const colorClass = badgeColors[normalized] || "bg-slate-100 text-slate-700 border-slate-300";
    const badge = document.createElement("span");
    badge.className = `rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${colorClass}`;
    badge.textContent = normalized;
    badgeContainer.appendChild(badge);
  });
}

function renderValidation(detections, links) {
  // Render detected components
  if (!detections.length) {
    validationDetections.innerHTML = '<span class="text-slate-500 text-sm">No components detected.</span>';
  } else {
    validationDetections.innerHTML = detections.map(d => `<span class="rounded-full bg-white border border-slate-300 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-700">${d}</span>`).join('');
  }
  
  // Render detected links
  if (!links.length) {
    validationLinks.innerHTML = '<span class="text-slate-500 text-sm">No connections detected.</span>';
  } else {
    validationLinks.innerHTML = links.map(link => `<div class="flex items-center gap-2 text-sm"><span class="font-mono text-slate-700 bg-slate-100 px-2 py-1 rounded">${link.from}</span><span class="text-slate-400">↔</span><span class="font-mono text-slate-700 bg-slate-100 px-2 py-1 rounded">${link.to}</span></div>`).join('');
  }
  
  validationPanel.classList.remove("hidden");
}

function closeImageModal() {
  imageModal.classList.add("hidden");
  imageModal.setAttribute("aria-hidden", "true");
  imageModalContent.removeAttribute("src");
}

function openImageModal(imageSrc) {
  if (!imageSrc) {
    return;
  }
  imageModalContent.src = imageSrc;
  imageModal.classList.remove("hidden");
  imageModal.setAttribute("aria-hidden", "false");
}

copyBtn.addEventListener("click", async () => {
  if (!terraformOutput) {
    return;
  }
  await navigator.clipboard.writeText(terraformOutput);
  copyBtn.textContent = "Copied";
  setTimeout(() => {
    copyBtn.textContent = "Copy";
  }, 1400);
});

downloadBtn.addEventListener("click", () => {
  if (!terraformOutput) {
    return;
  }
  const blob = new Blob([terraformOutput], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "main.tf";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

deployBtn.addEventListener("click", startDeployment);
destroyBtn.addEventListener("click", destroyDeployment);
regenerateTerraformBtn.addEventListener("click", regenerateWithEditedNames);
generateTerraformBtn.addEventListener("click", () => generateTerraform(false));

fileInput.addEventListener("change", (event) => {
  const file = event.target.files && event.target.files[0];
  setFile(file);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    event.stopPropagation();
    dropZone.classList.add("border-sky-600", "bg-sky-100");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    event.stopPropagation();
    dropZone.classList.remove("border-sky-600", "bg-sky-100");
  });
});

dropZone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files && event.dataTransfer.files[0];
  setFile(file);
});

annotatedPreview.addEventListener("click", () => {
  openImageModal(annotatedPreview.getAttribute("src"));
});

imageModalClose.addEventListener("click", closeImageModal);

imageModal.addEventListener("click", (event) => {
  if (event.target === imageModal) {
    closeImageModal();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !imageModal.classList.contains("hidden")) {
    closeImageModal();
  }
});

analyzeBtn.addEventListener("click", () => analyzeImage());

renderStepper(0);
setProgress(0, "Waiting...");
resetDeploymentUi();
deployBtn.disabled = true;
generateTerraformBtn.disabled = true;
renderOcrNames({});
