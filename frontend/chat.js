const API_BASE = "http://localhost:8000";

const steps = ["Describe", "Refine", "Validate", "Generate"];
const stepper = document.getElementById("stepper");
const chatHistory = document.getElementById("chatHistory");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const resetChatBtn = document.getElementById("resetChatBtn");
const typingIndicator = document.getElementById("typingIndicator");
const validationPanel = document.getElementById("validationPanel");
const validationMessage = document.getElementById("validationMessage");
const archSummary = document.getElementById("archSummary");
const terraformCode = document.getElementById("terraformCode");
const copyBtn = document.getElementById("copyBtn");
const downloadBtn = document.getElementById("downloadBtn");
const deployBtn = document.getElementById("deployBtn");
const deployStatus = document.getElementById("deployStatus");
const deployLogs = document.getElementById("deployLogs");
const deployPanel = document.getElementById("deployPanel");
const deployStatusContainer = document.getElementById("deployStatusContainer");
const deployHelp = document.getElementById("deployHelp");

let isThinking = false;
let currentTerraform = "";

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

function addMessage(role, content) {
  const msgDiv = document.createElement("div");
  msgDiv.className = `msg ${role === "user" ? "msg-user" : "msg-assistant"}`;
  msgDiv.textContent = content;
  chatHistory.appendChild(msgDiv);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || isThinking) return;

  addMessage("user", text);
  chatInput.value = "";
  
  isThinking = true;
  typingIndicator.classList.remove("hidden");
  sendBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/chat/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: "default" }),
    });

    if (!res.ok) throw new Error("Failed to communicate with the assistant.");

    const data = await res.json();
    addMessage("assistant", data.message);
    
    updateUI(data);
  } catch (error) {
    addMessage("assistant", "Sorry, I encountered an error: " + error.message);
  } finally {
    isThinking = false;
    typingIndicator.classList.add("hidden");
    sendBtn.disabled = false;
  }
}

function updateUI(data) {
  // Update Architecture Summary
  archSummary.textContent = JSON.stringify(data.architecture, null, 2);
  
  // Update Validation Status
  validationPanel.classList.remove("hidden");
  if (data.validation.ready) {
    validationMessage.innerHTML = `<span class="text-emerald-600 font-bold">✓ Architecture is valid.</span>`;
    renderStepper(3);
    deployPanel.classList.remove("opacity-50");
    deployHelp.classList.add("hidden");
  } else {
    validationMessage.innerHTML = `<span class="text-amber-600 font-bold">⚠ More information needed:</span><ul class="list-disc ml-5 mt-1 text-xs">${data.validation.missing.map(m => `<li>${m}</li>`).join('')}</ul>`;
    renderStepper(1);
    deployPanel.classList.add("opacity-50");
    deployHelp.classList.remove("hidden");
  }

  // Update Code
  if (data.terraform) {
    currentTerraform = data.terraform;
    terraformCode.textContent = data.terraform;
    hljs.highlightElement(terraformCode);
    copyBtn.disabled = false;
    downloadBtn.disabled = false;
    deployBtn.disabled = false;
  }
}

async function resetChat() {
  if (!confirm("Are you sure you want to reset the conversation?")) return;
  
  try {
    await fetch(`${API_BASE}/api/chat/reset`, { method: "POST" });
    chatHistory.innerHTML = `<div class="msg msg-assistant">Session reset. How can I help you today?</div>`;
    archSummary.textContent = "{}";
    validationPanel.classList.add("hidden");
    terraformCode.textContent = "# Describe your network to generate code...";
    currentTerraform = "";
    copyBtn.disabled = true;
    downloadBtn.disabled = true;
    deployBtn.disabled = true;
    deployPanel.classList.add("opacity-50");
    renderStepper(0);
  } catch (error) {
    alert("Failed to reset chat: " + error.message);
  }
}

// Copy/Download Logic
copyBtn.addEventListener("click", () => {
  navigator.clipboard.writeText(currentTerraform);
  copyBtn.textContent = "Copied!";
  setTimeout(() => copyBtn.textContent = "Copy", 2000);
});

downloadBtn.addEventListener("click", () => {
  const blob = new Blob([currentTerraform], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "main.tf"; a.click();
});

// Event Listeners
sendBtn.addEventListener("click", sendMessage);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
resetChatBtn.addEventListener("click", resetChat);

// Initialize
renderStepper(0);
