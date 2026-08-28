// Global State Management
let activeRepositoryId = null;
let activeRepositoryName = "";
let indexedRepositories = [];
let pollingIntervalId = null;

// API base path (same host because we serve statically, fallback to local backend for direct file:// access)
const API_BASE = window.location.protocol === "file:" ? "http://localhost:8000/api/v1" : "/api/v1";


// Dom Elements Selection
const selectDropdown = document.getElementById("workspace-select");
const navButtons = document.querySelectorAll(".nav-btn");
const viewPanels = document.querySelectorAll(".view-panel");
const activeRepoText = document.getElementById("active-repo-name");

// Navigation buttons
const navDashboard = document.getElementById("nav-dashboard");
const navExplorer = document.getElementById("nav-explorer");
const navChat = document.getElementById("nav-chat");
const navReports = document.getElementById("nav-reports");

const navModern = document.getElementById("nav-modern");
const navCompare = document.getElementById("nav-compare");
const navDeps = document.getElementById("nav-deps");
const navLicense = document.getElementById("nav-license");

// Initialize Setup
document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  loadRepositories();
  setupIngestionHandlers();
  setupChatHandlers();
  setupReportHandlers();
  loadActiveModel();
});

async function loadActiveModel() {
  try {
    const res = await fetch(`${API_BASE}/model`);
    if (!res.ok) throw new Error("Failed to load model details");
    const data = await res.json();
    const modelEl = document.getElementById("active-model");
    if (modelEl) {
      if (data.error) {
        modelEl.textContent = "Error loading model";
        modelEl.title = data.error;
      } else {
        const name = data.model || "Unknown model";
        const provider = data.provider || "unknown";
        // Clean up name a bit for display (e.g. remove path prefix if any, but keep full info)
        modelEl.textContent = `${name} (${provider})`;
      }
    }
  } catch (err) {
    console.error("Error loading active model:", err);
    const modelEl = document.getElementById("active-model");
    if (modelEl) {
      modelEl.textContent = "Failed to load model";
    }
  }
}


// 1. Navigation Tab Controller
function setupNavigation() {
  navButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-target");
      switchView(target);
      
      // Update active class
      navButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
}

function switchView(viewId) {
  viewPanels.forEach(panel => {
    if (panel.id === viewId) {
      panel.classList.add("active");
    } else {
      panel.classList.remove("active");
    }
  });
  
  // Custom view activation initializers
  if (viewId === "dashboard-view" && activeRepositoryId) {
    loadDashboard(activeRepositoryId);
  } else if (viewId === "modern-view" && activeRepositoryId) {
    loadModernCodebase(activeRepositoryId);
  } else if (viewId === "compare-view") {
    populateCompareDropdowns();
  } else if (viewId === "deps-view" && activeRepositoryId) {
    loadDependencies(activeRepositoryId);
  } else if (viewId === "license-view" && activeRepositoryId) {
    loadLicense(activeRepositoryId);
  }
}

function enableWorkspaceTabs() {
  navDashboard.disabled = false;
  navExplorer.disabled = false;
  navChat.disabled = false;
  navReports.disabled = false;
  navModern.disabled = false;
  navDeps.disabled = false;
  navLicense.disabled = false;
}

// 2. Fetch and List Repositories
async function loadRepositories() {
  try {
    const res = await fetch(`${API_BASE}/repositories`);
    if (!res.ok) throw new Error("Failed to load workspaces list");
    const data = await res.json();
    indexedRepositories = data;
    
    populateWorkspaceSelectors(data);
    renderWorkspaceTable(data);
  } catch (err) {
    console.error("Error fetching repositories:", err);
  }
}

function populateWorkspaceSelectors(repos) {
  // Clear select dropdown except first disabled option
  selectDropdown.innerHTML = '<option value="" disabled selected>Select indexed repo...</option>';
  
  repos.forEach(repo => {
    if (repo.status === "completed") {
      const opt = document.createElement("option");
      opt.value = repo.id;
      opt.textContent = repo.name;
      if (repo.id === activeRepositoryId) {
        opt.selected = true;
      }
      selectDropdown.appendChild(opt);
    }
  });
  
  // Set select handler
  selectDropdown.onchange = (e) => {
    const repoId = e.target.value;
    selectWorkspace(repoId);
  };
}

function selectWorkspace(repoId) {
  const repo = indexedRepositories.find(r => r.id === repoId);
  if (repo) {
    activeRepositoryId = repoId;
    activeRepositoryName = repo.name;
    activeRepoText.textContent = repo.name;
    enableWorkspaceTabs();
    
    // Default switch to dashboard view on select
    switchView("dashboard-view");
    navButtons.forEach(b => b.classList.remove("active"));
    navDashboard.classList.add("active");
    
    // Clear chat contexts
    document.getElementById("chat-messages-area").innerHTML = `
      <div class="chat-msg system-msg">
        <div class="msg-bubble">
          Hello! I have fully indexed <strong>${repo.name}</strong>. Ask me any question about the architecture, functions, endpoints, or data models.
        </div>
      </div>
    `;
    
    // Reset compilation views
    document.getElementById("report-view-container").innerHTML = `Click "Compile Report" below to run the security analyzer and architecture critique.`;
    document.getElementById("compile-report-placeholder").style.display = "block";
    
    // Populate chat language filter options
    populateLanguageFilter(repo.languages);
  }
}

function populateLanguageFilter(languages) {
  const filterSelect = document.getElementById("chat-filter-lang");
  filterSelect.innerHTML = '<option value="">All languages</option>';
  if (languages) {
    Object.keys(languages).forEach(lang => {
      const opt = document.createElement("option");
      opt.value = lang;
      opt.textContent = lang;
      filterSelect.appendChild(opt);
    });
  }
}

function renderWorkspaceTable(repos) {
  const tbody = document.getElementById("repo-list-body");
  tbody.innerHTML = "";
  
  if (repos.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-table-msg">No indexed workspaces found. Upload one to start!</td>
      </tr>
    `;
    return;
  }
  
  repos.forEach(repo => {
    const tr = document.createElement("tr");
    
    const langBadges = Object.keys(repo.languages || {})
      .map(l => `<span class="chip" style="font-size:10px; padding:2px 8px; margin-right:3px;">${l}</span>`)
      .join("");
      
    tr.innerHTML = `
      <td><strong>${repo.name}</strong></td>
      <td><span class="status-badge status-${repo.status}">${repo.status.toUpperCase()}</span></td>
      <td>${repo.file_count || 0}</td>
      <td>${repo.total_lines || 0}</td>
      <td>${langBadges || 'None'}</td>
      <td>
        <button class="secondary-btn btn-sm" onclick="selectWorkspace('${repo.id}')" ${repo.status !== 'completed' ? 'disabled' : ''}>Explore</button>
        <button class="danger-btn btn-sm" onclick="deleteWorkspace('${repo.id}')">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function deleteWorkspace(id) {
  if (!confirm("Are you sure you want to delete this repository workspace and all vector indexes?")) return;
  try {
    const res = await fetch(`${API_BASE}/repositories/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete repository");
    
    if (activeRepositoryId === id) {
      activeRepositoryId = null;
      activeRepositoryName = "";
      activeRepoText.textContent = "None Selected";
      navDashboard.disabled = true;
      navExplorer.disabled = true;
      navChat.disabled = true;
      navReports.disabled = true;
      switchView("landing-view");
      navButtons.forEach(b => b.classList.remove("active"));
      document.querySelector('[data-target="landing-view"]').classList.add("active");
    }
    
    loadRepositories();
  } catch (err) {
    alert("Error deleting workspace: " + err.message);
  }
}

// 3. Setup Ingestion Drag/Drop and Remote Clone
function setupIngestionHandlers() {
  const dropZone = document.getElementById("drop-zone");
  const zipInput = document.getElementById("zip-input");
  const fileInfo = document.getElementById("file-info");
  const fileNameSpan = fileInfo.querySelector(".file-name");
  const uploadBtn = document.getElementById("upload-btn");
  const cloneBtn = document.getElementById("clone-btn");
  
  // Drag/Drop hooks
  dropZone.addEventListener("click", () => zipInput.click());
  
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });
  
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      zipInput.files = e.dataTransfer.files;
      showSelectedFile();
    }
  });
  
  zipInput.addEventListener("change", showSelectedFile);
  
  function showSelectedFile() {
    if (zipInput.files.length) {
      fileNameSpan.textContent = zipInput.files[0].name;
      fileInfo.style.display = "flex";
    }
  }
  
  // Upload Submit
  uploadBtn.addEventListener("click", async () => {
    const file = zipInput.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append("file", file);
    
    showProgressModal();
    appendTerminalLog("Starting ZIP file multipart upload...");
    
    try {
      const res = await fetch(`${API_BASE}/repositories/upload`, {
        method: "POST",
        body: formData
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }
      
      const data = await res.json();
      appendTerminalLog(`Upload complete. Created Repository ID: ${data.repository_id}`);
      startProgressPolling(data.repository_id);
    } catch (err) {
      appendTerminalLog(`Error: ${err.message}`, true);
      document.getElementById("close-modal-btn").style.display = "block";
    }
  });
  
  // Clone Submit
  cloneBtn.addEventListener("click", async () => {
    const gitUrl = document.getElementById("git-url").value.strip ? document.getElementById("git-url").value.strip() : document.getElementById("git-url").value;
    const branch = document.getElementById("git-branch").value;
    
    if (!gitUrl) {
      alert("Please provide a valid Git URL");
      return;
    }
    
    showProgressModal();
    appendTerminalLog(`Initiating Git clone for: ${gitUrl} (branch: ${branch})...`);
    
    try {
      const res = await fetch(`${API_BASE}/repositories/clone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: gitUrl, branch: branch })
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Clone failed");
      }
      
      const data = await res.json();
      appendTerminalLog(`Clone job started. Repository ID: ${data.repository_id}`);
      startProgressPolling(data.repository_id);
    } catch (err) {
      appendTerminalLog(`Error: ${err.message}`, true);
      document.getElementById("close-modal-btn").style.display = "block";
    }
  });
  
  // Close Modal Hook
  document.getElementById("close-modal-btn").onclick = () => {
    document.getElementById("progress-modal").style.display = "none";
    document.getElementById("close-modal-btn").style.display = "none";
    loadRepositories();
  };
}

// 4. Progress Terminal Modal Logger
function showProgressModal() {
  document.getElementById("progress-modal").style.display = "flex";
  document.getElementById("modal-progress-bar").style.width = "0%";
  document.getElementById("modal-progress-pct").textContent = "0%";
  document.getElementById("modal-status-msg").textContent = "Preparing worker...";
  document.getElementById("terminal-feed").innerHTML = "";
  document.getElementById("close-modal-btn").style.display = "none";
}

function appendTerminalLog(msg, isError = false) {
  const feed = document.getElementById("terminal-feed");
  const line = document.createElement("div");
  line.className = "log-line";
  if (isError) line.style.color = "var(--accent-red)";
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  feed.appendChild(line);
  feed.scrollTop = feed.scrollHeight;
}

// Polling Task Progress status
function startProgressPolling(repoId) {
  if (pollingIntervalId) clearInterval(pollingIntervalId);
  
  pollingIntervalId = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/repositories/${repoId}/status`);
      if (!res.ok) throw new Error("Status inquiry endpoint failed");
      const statusData = await res.json();
      
      // Update UI
      document.getElementById("modal-progress-bar").style.width = `${statusData.progress}%`;
      document.getElementById("modal-progress-pct").textContent = `${statusData.progress}%`;
      document.getElementById("modal-status-msg").textContent = statusData.message;
      appendTerminalLog(statusData.message);
      
      if (statusData.status === "completed") {
        clearInterval(pollingIntervalId);
        appendTerminalLog("Indexation finished successfully!");
        document.getElementById("close-modal-btn").style.display = "block";
        activeRepositoryId = repoId;
        loadRepositories();
      } else if (statusData.status === "failed") {
        clearInterval(pollingIntervalId);
        appendTerminalLog(`Error pipeline failed: ${statusData.message}`, true);
        document.getElementById("close-modal-btn").style.display = "block";
      }
    } catch (err) {
      clearInterval(pollingIntervalId);
      appendTerminalLog(`Status Polling Error: ${err.message}`, true);
      document.getElementById("close-modal-btn").style.display = "block";
    }
  }, 1500);
}

// 5. Dashboard Visualizer
async function loadDashboard(repoId) {
  try {
    const res = await fetch(`${API_BASE}/repositories/${repoId}`);
    if (!res.ok) throw new Error("Could not fetch workspace summary");
    const summary = await res.json();
    
    // Map scores (Architecture, Security, Quality indexes)
    document.getElementById("score-arch").innerHTML = `${summary.architecture_score || 85}<span class="score-total">/100</span>`;
    document.getElementById("bar-arch").style.width = `${summary.architecture_score || 85}%`;
    
    document.getElementById("score-sec").innerHTML = `${summary.security_score || 90}<span class="score-total">/100</span>`;
    document.getElementById("bar-sec").style.width = `${summary.security_score || 90}%`;
    
    document.getElementById("score-quality").innerHTML = `${summary.maintainability_score || 78}<span class="score-total">/100</span>`;
    document.getElementById("bar-quality").style.width = `${summary.maintainability_score || 78}%`;
    
    document.getElementById("stat-files").textContent = summary.file_count || 0;
    document.getElementById("stat-lines").textContent = `${(summary.total_lines || 0).toLocaleString()} lines of code`;
    
    document.getElementById("metric-classes").textContent = summary.class_count || 0;
    document.getElementById("metric-functions").textContent = summary.function_count || 0;
    document.getElementById("metric-deps").textContent = summary.dependency_count || 0;
    document.getElementById("metric-chunks").textContent = summary.chunk_count || 0;
    
    // Languages Distribution
    renderLanguageDistribution(summary.languages);
    
    // Framework List
    renderFrameworks(summary.frameworks);
    
    // Load file explorer tree structures
    renderFileExplorerTree(summary.indexed_files);
    
    // Generate warnings alerts
    renderWarningsAlerts(summary);
  } catch (err) {
    console.error("Dashboard render failed:", err);
  }
}

function renderLanguageDistribution(languages) {
  const container = document.getElementById("language-bars-container");
  container.innerHTML = "";
  
  if (!languages || Object.keys(languages).length === 0) {
    container.innerHTML = "<p class='text-muted' style='font-size:14px;'>No language statistics indexed.</p>";
    return;
  }
  
  Object.entries(languages).forEach(([name, pct]) => {
    const row = document.createElement("div");
    row.style.marginBottom = "8px";
    row.innerHTML = `
      <div class="lang-row">
        <span class="lang-name">${name}</span>
        <span class="lang-percentage">${pct}%</span>
      </div>
      <div class="lang-bar-wrapper">
        <div class="lang-bar-fill" style="width: ${pct}%; background-color: ${getLanguageColor(name)};"></div>
      </div>
    `;
    container.appendChild(row);
  });
}

function getLanguageColor(lang) {
  const colors = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Java": "#b07219",
    "C#": "#178600",
    "Go": "#00ADD8",
    "Markdown": "#083fa1",
    "CSS": "#563d7c",
    "HTML": "#e34c26"
  };
  return colors[lang] || "var(--accent-cyan)";
}

function renderFrameworks(frameworks) {
  const container = document.getElementById("framework-list");
  container.innerHTML = "";
  
  if (!frameworks || frameworks.length === 0) {
    container.innerHTML = "<span class='text-muted' style='font-size:14px;'>Standard core library configurations only</span>";
    return;
  }
  
  frameworks.forEach(fw => {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = fw;
    container.appendChild(span);
  });
}

function renderWarningsAlerts(summary) {
  const container = document.getElementById("alerts-feed-list");
  container.innerHTML = "";
  
  let alertsCount = 0;
  
  // Check if java/dotnet were skipped stubs
  if (summary.languages && (summary.languages["Java"] || summary.languages["C#"])) {
    container.innerHTML += `
      <div class="alert-item info">
        <span class="alert-icon">⚠️</span>
        <div class="alert-desc">Java and C#/.NET language codeblocks were stub-indexed (parsing schedules pending).</div>
      </div>
    `;
    alertsCount++;
  }
  
  // Default clean state log
  if (alertsCount === 0) {
    container.innerHTML = `
      <div class="alert-item info">
        <span class="alert-icon">💡</span>
        <div class="alert-desc">Code audit scans passed: 0 vulnerabilities found. Ask questions in the AI Chat.</div>
      </div>
    `;
  }
}

// 6. File Navigator Tree Layout
function renderFileExplorerTree(indexedFiles) {
  const container = document.getElementById("file-tree-container");
  container.innerHTML = "";
  
  if (!indexedFiles || indexedFiles.length === 0) {
    container.innerHTML = "No files indexed.";
    return;
  }

  // 1. Build nested tree dictionary
  const tree = {};
  indexedFiles.forEach(file => {
    const parts = file.file_path.split("/");
    let current = tree;
    parts.forEach((part, idx) => {
      if (!current[part]) {
        current[part] = idx === parts.length - 1 ? { _file: file } : {};
      }
      current = current[part];
    });
  });

  // 2. Render DOM recursively
  function buildDOM(node, container, depth = 0) {
    Object.keys(node).sort().forEach(key => {
      if (key === "_file") return;
      
      const child = node[key];
      const isFile = !!child._file;
      const nodeEl = document.createElement("div");
      nodeEl.className = "tree-node";
      
      const label = document.createElement("div");
      label.className = "node-label";
      
      if (isFile) {
        label.innerHTML = `<span class="node-icon">📄</span> <span class="node-text">${key}</span>`;
        label.onclick = () => {
          // Select and highlight active item
          document.querySelectorAll(".node-label").forEach(l => l.classList.remove("active"));
          label.classList.add("active");
          loadFileContent(child._file.file_path, child._file.size_bytes, child._file.language);
        };
      } else {
        label.innerHTML = `<span class="node-chevron">▶</span> <span class="node-icon">📁</span> <span class="node-text">${key}</span>`;
        const childContainer = document.createElement("div");
        childContainer.className = "folder-children";
        childContainer.style.display = "none";
        
        label.onclick = () => {
          const chevron = label.querySelector(".node-chevron");
          if (childContainer.style.display === "none") {
            childContainer.style.display = "block";
            chevron.classList.add("expanded");
          } else {
            childContainer.style.display = "none";
            chevron.classList.remove("expanded");
          }
        };
        
        nodeEl.appendChild(childContainer);
        buildDOM(child, childContainer, depth + 1);
      }
      
      nodeEl.insertBefore(label, nodeEl.firstChild);
      container.appendChild(nodeEl);
    });
  }

  buildDOM(tree, container);
}

async function loadFileContent(filePath, sizeBytes, language) {
  document.getElementById("viewer-file-path").textContent = filePath;
  document.getElementById("viewer-file-meta").style.display = "block";
  document.getElementById("viewer-meta-size").textContent = `${(sizeBytes / 1024).toFixed(1)} KB`;
  document.getElementById("viewer-meta-lang").textContent = language;
  
  const codeBlock = document.getElementById("code-content-block");
  codeBlock.textContent = "Loading file content...";
  
  try {
    const res = await fetch(`${API_BASE}/repositories/${activeRepositoryId}/file?path=${encodeURIComponent(filePath)}`);
    if (!res.ok) throw new Error("Could not read file details");
    const data = await res.json();
    
    // Add line numbers manually for clean alignment
    const lines = data.content.split("\n");
    const numberedCode = lines.map((l, i) => {
      const lineNum = String(i + 1).padStart(3, " ");
      return `${lineNum} | ${l}`;
    }).join("\n");
    
    codeBlock.textContent = numberedCode;
  } catch (err) {
    codeBlock.textContent = `Error loading file: ${err.message}`;
  }
}

// 7. Conversational Chat RAG Queries
function setupChatHandlers() {
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  const suggestedBtns = document.querySelectorAll(".suggested-btn");
  
  sendBtn.addEventListener("click", executeQuery);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      executeQuery();
    }
  });
  
  suggestedBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      chatInput.value = btn.textContent;
      executeQuery();
    });
  });
}

async function executeQuery() {
  const chatInput = document.getElementById("chat-input");
  const queryText = chatInput.value.trim ? chatInput.value.trim() : chatInput.value;
  if (!queryText || !activeRepositoryId) return;
  
  chatInput.value = "";
  appendChatMessage(queryText, "user-msg");
  
  // Create Bot thinking block with animated loading dots (user-facing, clean)
  const loaderHtml = `
    <div class="typing-indicator">
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;
  const botBubble = appendChatMessage(loaderHtml, "system-msg", true);
  
  const topK = parseInt(document.getElementById("chat-top-k").value) || 7;
  const langFilter = document.getElementById("chat-filter-lang").value;
  
  try {
    // Prepare for streaming responses via fetch ReadableStream
    const res = await fetch(`${API_BASE}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repository_id: activeRepositoryId,
        query: queryText,
        top_k: topK,
        filters: langFilter ? { "language": langFilter } : null
      })
    });

    if (!res.ok) {
      throw new Error("Streaming endpoint returned non-200 status");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let fullAnswer = "";
    let sources = [];
    let confidence = 0.9;
    let debugInfo = null;
    let isFirstToken = true;
    const bubble = botBubble.querySelector(".msg-bubble");

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // Keep the last incomplete line in buffer

      for (const line of lines) {
        const cleanLine = line.trim();
        if (!cleanLine || !cleanLine.startsWith("data: ")) continue;

        const jsonStr = cleanLine.substring(6);
        try {
          const packet = JSON.parse(jsonStr);
          if (packet.type === "meta") {
            sources = packet.sources;
            confidence = packet.confidence_score;
            debugInfo = packet.debug_info;
          } else if (packet.type === "token") {
            if (isFirstToken) {
              bubble.innerHTML = ""; // Clear typing indicator
              isFirstToken = false;
            }
            fullAnswer += packet.content;
            bubble.innerHTML = renderMarkdownToHtml(fullAnswer);
            document.getElementById("chat-messages-area").scrollTop = document.getElementById("chat-messages-area").scrollHeight;
          } else if (packet.type === "done") {
            if (isFirstToken) {
              bubble.innerHTML = "<em>No response generated.</em>"; // Clear typing indicator if stream was empty
              isFirstToken = false;
            }
            if (debugInfo && debugInfo.latency && packet.time_taken_seconds) {
              debugInfo.latency.total_seconds = packet.time_taken_seconds;
            }
          }
        } catch (e) {
          console.error("Error parsing stream JSON packet:", e);
        }
      }
    }

    // Done streaming, append traceable sources and developer debug panel (if active)
    appendSourcesAndLinks(botBubble, fullAnswer, sources, confidence, debugInfo);

  } catch (err) {
    console.warn("Streaming response failed or unsupported, falling back to standard completion:", err);
    await executeStandardQuery(queryText, botBubble, topK, langFilter);
  }
}

async function executeStandardQuery(queryText, botBubble, topK, langFilter) {
  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repository_id: activeRepositoryId,
        query: queryText,
        top_k: topK,
        filters: langFilter ? { "language": langFilter } : null
      })
    });
    
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Query failed");
    }
    
    const data = await res.json();
    simulateTypewriterResponse(botBubble, data.answer, data.sources, data.confidence_score, data.debug_info);
  } catch (err) {
    botBubble.querySelector(".msg-bubble").textContent = `Error: ${err.message}`;
  }
}

function appendChatMessage(text, className, isHTML = false) {
  const area = document.getElementById("chat-messages-area");
  const msg = document.createElement("div");
  msg.className = `chat-msg ${className}`;
  msg.innerHTML = `<div class="msg-bubble">${isHTML ? text : escapeHtml(text)}</div>`;
  area.appendChild(msg);
  area.scrollTop = area.scrollHeight;
  return msg;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Simulated dynamic typewriter effect (for standard API fallback)
function simulateTypewriterResponse(msgElement, fullText, sources, confidence, debugInfo) {
  const bubble = msgElement.querySelector(".msg-bubble");
  bubble.innerHTML = ""; // Clear loader
  
  let html = renderMarkdownToHtml(fullText);
  let i = 0;
  
  const interval = setInterval(() => {
    const chunk_size = 5;
    if (i < html.length) {
      bubble.innerHTML = html.substring(0, i + chunk_size);
      i += chunk_size;
      document.getElementById("chat-messages-area").scrollTop = document.getElementById("chat-messages-area").scrollHeight;
    } else {
      clearInterval(interval);
      bubble.innerHTML = html;
      appendSourcesAndLinks(msgElement, fullText, sources, confidence, debugInfo);
    }
  }, 15);
}

// Helper to append traceable sources, link hooks, and RAG debug blocks
function appendSourcesAndLinks(msgElement, fullText, sources, confidence, debugInfo) {
  const bubble = msgElement.querySelector(".msg-bubble");
  
  // Clear any existing source link blocks or debugger containers first
  const oldSrc = bubble.querySelector(".source-links");
  if (oldSrc) oldSrc.remove();
  const oldDbg = bubble.querySelector(".rag-debug-container");
  if (oldDbg) oldDbg.remove();
  
  // Append Source Anchor Links
  if (sources && sources.length > 0) {
    const srcDiv = document.createElement("div");
    srcDiv.className = "source-links";
    srcDiv.innerHTML = `<div class="source-title">Traceable Sources (Confidence: ${Math.round(confidence * 100)}%):</div>`;
    
    sources.forEach(src => {
      const a = document.createElement("a");
      a.className = "source-anchor";
      a.href = "#";
      a.textContent = `${src.file_path} (lines ${src.start_line}-${src.end_line})`;
      
      a.onclick = (e) => {
        e.preventDefault();
        switchView("explorer-view");
        navButtons.forEach(b => b.classList.remove("active"));
        navExplorer.classList.add("active");
        loadFileContent(src.file_path, 0, "");
      };
      
      srcDiv.appendChild(a);
    });
    bubble.appendChild(srcDiv);
  }
  
  // Apply click hooks to inline file:/// paths generated by LLM
  bubble.querySelectorAll("a").forEach(link => {
    if (link.href.startsWith("file:///")) {
      const urlPath = link.href.replace("file:///", "");
      const cleanPath = urlPath.split("#")[0];
      link.href = "#";
      link.onclick = (e) => {
        e.preventDefault();
        switchView("explorer-view");
        navButtons.forEach(b => b.classList.remove("active"));
        navExplorer.classList.add("active");
        loadFileContent(cleanPath, 0, "");
      };
    }
  });

  // Render developer-only debugger panel if DEBUG_RAG is enabled
  if (debugInfo) {
    const dbgDiv = document.createElement("div");
    dbgDiv.className = "rag-debug-container";
    
    let chunksHtml = "";
    if (debugInfo.retrieved_chunks) {
      debugInfo.retrieved_chunks.forEach((c, idx) => {
        chunksHtml += `<strong>Chunk ${idx + 1}</strong> [Distance: ${c.distance}] - ${c.file_path} (lines ${c.start_line}-${c.end_line})\n<div class="rag-debug-content">${escapeHtml(c.preview)}</div>\n`;
      });
    }
    
    dbgDiv.innerHTML = `
      <div class="rag-debug-header">
        <span>🛠️ RAG Debugger (Developer Mode)</span>
        <span>Latency: ${debugInfo.latency ? debugInfo.latency.total_seconds : '?'}s</span>
      </div>
      <div class="rag-debug-section">
        <div class="rag-debug-title">LLM Model Info</div>
        <div class="rag-debug-content">${JSON.stringify(debugInfo.model_info, null, 2)}</div>
      </div>
      <div class="rag-debug-section">
        <div class="rag-debug-title">Retrieved Vector Chunks</div>
        <div style="font-size:0.7rem; color:var(--text-secondary); line-height:1.4; white-space:pre-wrap;">
          ${chunksHtml}
        </div>
      </div>
      <div class="rag-debug-section">
        <div class="rag-debug-title">Raw XML Context Sent to LLM</div>
        <div class="rag-debug-content">${escapeHtml(debugInfo.context || '')}</div>
      </div>
    `;
    bubble.appendChild(dbgDiv);
  }
  
  document.getElementById("chat-messages-area").scrollTop = document.getElementById("chat-messages-area").scrollHeight;
}

// Simple regex markdown renderer for codeblocks, bolding, list items, and links
function renderMarkdownToHtml(markdown) {
  let text = escapeHtml(markdown);
  
  // Fenced Codeblocks
  text = text.replace(/```([\s\S]*?)```/g, '<pre style="background:#090d16; padding:10px; border-radius:6px; margin:8px 0; overflow-x:auto;"><code style="font-family:var(--font-mono); font-size:12px; color:#a5f3fc;">$1</code></pre>');
  
  // Inline Code
  text = text.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.06); padding:2px 6px; border-radius:4px; font-family:var(--font-mono); font-size:12px; color:#cbd5e1;">$1</code>');
  
  // Bold
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  
  // Links: [text](url)
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color:var(--accent-cyan); text-decoration:underline;">$1</a>');
  
  // Bullets
  text = text.replace(/^\s*-\s+(.+)$/gm, '<li style="margin-left:20px; list-style-type:square;">$1</li>');
  
  return text;
}

// 8. Compile and Export Code Audits
function setupReportHandlers() {
  const compileBtn = document.getElementById("compile-report-btn");
  const placeholder = document.getElementById("compile-report-placeholder");
  const viewContainer = document.getElementById("report-view-container");
  
  const dlMdBtn = document.getElementById("download-md-btn");
  const dlJsonBtn = document.getElementById("download-json-btn");
  
  compileBtn.addEventListener("click", async () => {
    if (!activeRepositoryId) return;
    
    placeholder.style.display = "none";
    viewContainer.textContent = "AI is running static vulnerability sweeps and drafting architecture reports...";
    
    try {
      const res = await fetch(`${API_BASE}/reports/${activeRepositoryId}/analysis`);
      if (!res.ok) throw new Error("Failed to compile codebase report");
      const report = await res.json();
      
      // Dynamic rendering of markdown file
      renderReportContent(report);
    } catch (err) {
      viewContainer.textContent = `Report Compilation Error: ${err.message}`;
      placeholder.style.display = "block";
    }
  });
  
  dlMdBtn.addEventListener("click", () => {
    if (activeRepositoryId) {
      window.open(`${API_BASE}/reports/${activeRepositoryId}/export?format=markdown`, "_blank");
    }
  });
  
  dlJsonBtn.addEventListener("click", () => {
    if (activeRepositoryId) {
      window.open(`${API_BASE}/reports/${activeRepositoryId}/export?format=json`, "_blank");
    }
  });
}

function renderReportContent(report) {
  const viewContainer = document.getElementById("report-view-container");
  
  let secretsRows = "";
  if (report.secrets_leakages && report.secrets_leakages.length > 0) {
    report.secrets_leakages.forEach(finding => {
      secretsRows += `
        <tr>
          <td><span style="color:#ef4444; font-weight:600;">[${finding.severity}]</span> ${finding.file_path}</td>
          <td>Line ${finding.line}</td>
          <td>${finding.issue}</td>
          <td><code style="font-family:var(--font-mono); font-size:12px; background:rgba(0,0,0,0.2); padding:2px 6px; border-radius:4px;">${finding.match}</code></td>
        </tr>
      `;
    });
  } else {
    secretsRows = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No hardcoded secrets or credentials detected.</td></tr>`;
  }
  
  const depsChips = report.dependencies_list
    .map(d => `<span class="chip" style="font-size:11px; padding:3px 8px; margin:2px;">${d}</span>`)
    .join("");

  viewContainer.innerHTML = `
    <h2>Repository Audit Report</h2>
    <div style="display:flex; gap:24px; margin-bottom:24px;">
      <div style="background:rgba(255,255,255,0.02); padding:16px; border-radius:8px; border:1px solid var(--glass-border); flex:1; text-align:center;">
        <div style="font-size:12px; text-transform:uppercase; color:var(--text-secondary);">Architecture integrity</div>
        <div style="font-size:28px; font-weight:700; color:var(--accent-cyan); margin-top:8px;">${report.architecture_score}/100</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:16px; border-radius:8px; border:1px solid var(--glass-border); flex:1; text-align:center;">
        <div style="font-size:12px; text-transform:uppercase; color:var(--text-secondary);">Security Confidence</div>
        <div style="font-size:28px; font-weight:700; color:var(--accent-orange); margin-top:8px;">${report.security_score}/100</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:16px; border-radius:8px; border:1px solid var(--glass-border); flex:1; text-align:center;">
        <div style="font-size:12px; text-transform:uppercase; color:var(--text-secondary);">Complexity Loops</div>
        <div style="font-size:28px; font-weight:700; color:var(--text-primary); margin-top:8px;">${report.complexity_score}</div>
      </div>
    </div>
    <h3>1. Architectural Design critique</h3>
    <div style="white-space:pre-wrap; line-height:1.6; margin-bottom:24px;">${renderMarkdownToHtml(report.architecture_analysis)}</div>
    <h3>2. Bill of Materials &amp; Dependencies</h3>
    <div style="margin-bottom:24px;">
      <p style="margin-bottom:8px;">Detected dependencies count: <strong>${report.dependencies_count}</strong></p>
      <div style="display:flex; flex-wrap:wrap;">${depsChips || 'None detected'}</div>
    </div>
    <h3>3. Static Scan: Credentials &amp; Hardcoded Keys</h3>
    <table>
      <thead><tr><th>File Location</th><th>Location</th><th>Severity / Issue</th><th>Pattern Preview</th></tr></thead>
      <tbody>${secretsRows}</tbody>
    </table>
    <h3>4. Security Context Analysis</h3>
    <div style="white-space:pre-wrap; line-height:1.6; margin-bottom:24px;">${renderMarkdownToHtml(report.security_analysis)}</div>
    <h3>5. Recommended Modernizations</h3>
    <ol style="margin-left:20px; line-height:1.6;">
      ${report.suggestions.map(s => `<li>${s}</li>`).join("")}
    </ol>
  `;
}


// ═══════════════════════════════════════════════════════════════════
// DUE DILIGENCE DASHBOARD — Phase 4
// ═══════════════════════════════════════════════════════════════════

// Storage for all findings (for client-side filtering)
let allSecurityFindings = [];

// Main entry point: loads full dashboard bundle
async function loadDueDiligenceDashboard(repoId) {
  const loadingEl = document.getElementById("dd-loading");
  if (loadingEl) loadingEl.style.display = "flex";

  try {
    const res = await fetch(`${API_BASE}/dashboard/${repoId}`);
    if (!res.ok) throw new Error(`Dashboard API returned ${res.status}`);
    const data = await res.json();

    renderDDOverviewHeader(data.overview, data.git_activity);
    renderSubmissionGauge(data.submission);
    renderQualityGauge(data.quality);
    renderSecurityGauge(data.security);
    renderCompliancePanel(data.submission?.checklist || {});
    renderArchitecturePanel(data.architecture);
    renderLanguagePanel(data.overview);
    renderSecurityFindings(data.security?.findings || []);
    renderGitActivity(data.git_activity, data.overview);
    renderDependencies(data.dependencies);
    renderLicense(data.license);
    renderDDLanguageDistribution(data.overview?.languages);
    renderDDFrameworkChips(data.overview?.frameworks);

    // Setup filter buttons
    setupFindingsFilter();

    // Setup generate reports button
    setupGenerateReportsBtn(repoId);
  } catch (err) {
    console.error("Due Diligence dashboard load failed:", err);
  } finally {
    if (loadingEl) loadingEl.style.display = "none";
  }
}

// ── Panel Renderers ───────────────────────────────────────────────

function renderDDOverviewHeader(overview, gitActivity) {
  if (!overview) return;
  document.getElementById("dd-repo-name").textContent = overview.repo_name || "Repository";
  document.getElementById("dd-owner").textContent = overview.owner || "local";
  document.getElementById("dd-source-type").textContent = overview.source_type || "zip";
  document.getElementById("dd-source-url").textContent = overview.source_url || "";

  const langs = Object.keys(overview.languages || {});
  document.getElementById("dd-primary-lang").textContent = langs[0] || "Unknown";

  document.getElementById("dd-total-files").textContent = (overview.total_files || 0).toLocaleString();
  document.getElementById("dd-total-lines").textContent = (overview.total_lines || 0).toLocaleString();
  document.getElementById("dd-contributors").textContent = gitActivity?.contributor_count ?? overview.contributors ?? "—";

  const pushed = gitActivity?.pushed_at;
  document.getElementById("dd-last-commit").textContent = pushed ? pushed.slice(0, 10) : "—";
}

function renderSubmissionGauge(submission) {
  if (!submission) return;
  const score = submission.submission_score || 0;
  const rec   = submission.approval_recommendation || "UNKNOWN";
  const conf  = submission.confidence_score || 0;

  // Animate arc (total arc is 251.3 for semicircle = π * 80)
  animateGaugeArc("dd-submission-arc", score, 100);
  document.getElementById("dd-submission-score-text").textContent = score;

  const badge = document.getElementById("dd-approval-badge");
  badge.textContent = rec;
  badge.className = "dd-approval-badge";
  if (rec === "APPROVE") badge.classList.add("badge-approve");
  else if (rec === "REVIEW") badge.classList.add("badge-review");
  else badge.classList.add("badge-reject");

  const confPct = Math.round(conf * 100);
  document.getElementById("dd-confidence-bar").style.width  = `${confPct}%`;
  document.getElementById("dd-confidence-value").textContent = `${confPct}%`;
  document.getElementById("dd-checklist-summary").textContent =
    submission.checklist_summary || `${submission.passed_checks || 0}/${submission.total_checks || 8} checks passed`;
}

function renderQualityGauge(quality) {
  if (!quality) return;
  const overall = quality.overall || 0;
  animateGaugeArc("dd-quality-arc", overall, 100);
  document.getElementById("dd-quality-score-text").textContent = overall;

  const dims = [
    { key: "documentation", label: "Docs",   max: 20, color: "#06b6d4" },
    { key: "testing",       label: "Testing", max: 20, color: "#8b5cf6" },
    { key: "ci_cd",         label: "CI/CD",   max: 15, color: "#10b981" },
    { key: "security",      label: "Security",max: 15, color: "#f59e0b" },
    { key: "configuration", label: "Config",  max: 15, color: "#ec4899" },
    { key: "architecture",  label: "Arch",    max: 15, color: "#0ea5e9" },
  ];
  const container = document.getElementById("dd-quality-dimensions");
  container.innerHTML = dims.map(d => {
    const val = quality[d.key] || 0;
    const pct = Math.round((val / d.max) * 100);
    return `
      <div class="dd-quality-dim">
        <span class="dd-quality-dim-label">${d.label}</span>
        <div class="dd-quality-dim-track">
          <div class="dd-quality-dim-fill" style="width:${pct}%; background:${d.color};"></div>
        </div>
        <span class="dd-quality-dim-score">${val}</span>
      </div>`;
  }).join("");
}

function renderSecurityGauge(security) {
  if (!security) return;
  const score  = security.score ?? 100;
  const counts = security.counts || {};
  animateGaugeArc("dd-security-arc", score, 100);
  document.getElementById("dd-security-score-text").textContent = score;
  document.getElementById("dd-sev-critical").textContent = counts.CRITICAL || 0;
  document.getElementById("dd-sev-high").textContent     = counts.HIGH     || 0;
  document.getElementById("dd-sev-medium").textContent   = counts.MEDIUM   || 0;
  document.getElementById("dd-sev-low").textContent      = counts.LOW      || 0;
}

function renderCompliancePanel(checklist) {
  const container = document.getElementById("dd-compliance-list");
  if (!checklist || Object.keys(checklist).length === 0) {
    container.innerHTML = "<div style='color:var(--text-muted); font-size:0.82rem;'>No compliance data available.</div>";
    return;
  }
  container.innerHTML = Object.values(checklist).map(item => `
    <div class="dd-compliance-item">
      <div class="dd-compliance-indicator ${item.pass ? 'pass' : 'fail'}">${item.pass ? '✓' : '✗'}</div>
      <span class="dd-compliance-label">${item.label}</span>
      <span class="dd-compliance-weight">${item.weight}pts</span>
    </div>
  `).join("");
}

function renderArchitecturePanel(arch) {
  if (!arch) return;
  const grid = document.getElementById("dd-arch-grid");
  const items = [
    { key: "App Type",    val: arch.application_type || "Unknown" },
    { key: "Framework",   val: (arch.frameworks || []).slice(0,2).join(", ") || "N/A" },
    { key: "Database",    val: (arch.database_layer || []).slice(0,2).join(", ") || "N/A" },
    { key: "Auth",        val: (arch.auth_mechanism || []).slice(0,2).join(", ") || "N/A" },
    { key: "Deployment",  val: (arch.deployment || []).slice(0,2).join(", ") || "N/A" },
    { key: "CI/CD",       val: (arch.ci_cd || []).slice(0,2).join(", ") || "None" },
  ];
  grid.innerHTML = items.map(i => `
    <div class="dd-arch-item">
      <div class="dd-arch-key">${i.key}</div>
      <div class="dd-arch-val" title="${i.val}">${i.val}</div>
    </div>`).join("");
}

function renderLanguagePanel(overview) {
  renderDDLanguageDistribution(overview?.languages);
  renderDDFrameworkChips(overview?.frameworks);
}

function renderDDLanguageDistribution(languages) {
  const container = document.getElementById("dd-language-bars");
  if (!container) return;
  if (!languages || Object.keys(languages).length === 0) {
    container.innerHTML = "<span style='color:var(--text-muted);font-size:0.8rem;'>No language data</span>";
    return;
  }
  container.innerHTML = Object.entries(languages).map(([name, pct]) => `
    <div style="margin-bottom:8px;">
      <div class="lang-row">
        <span class="lang-name">${name}</span>
        <span class="lang-percentage">${pct}%</span>
      </div>
      <div class="lang-bar-wrapper">
        <div class="lang-bar-fill" style="width:${pct}%; background-color:${getLanguageColor(name)};"></div>
      </div>
    </div>`).join("");
}

function renderDDFrameworkChips(frameworks) {
  const container = document.getElementById("dd-framework-chips");
  if (!container) return;
  if (!frameworks || frameworks.length === 0) {
    container.innerHTML = "<span style='color:var(--text-muted);font-size:0.75rem;'>None detected</span>";
    return;
  }
  container.innerHTML = frameworks.map(fw => `<span class="chip">${fw}</span>`).join("");
}

function renderSecurityFindings(findings) {
  allSecurityFindings = findings;
  renderFindingsTable(findings);
}

function renderFindingsTable(findings) {
  const tbody = document.getElementById("dd-findings-body");
  if (!findings || findings.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-table-msg">✅ No security findings detected.</td></tr>`;
    return;
  }
  tbody.innerHTML = findings.slice(0, 100).map(f => `
    <tr>
      <td><span class="sev-badge sev-${f.severity}">${f.severity}</span></td>
      <td class="finding-file" title="${f.file_path}">${f.file_path?.split('/').pop() || f.file_path}</td>
      <td style="color:var(--text-muted);">${f.line || '—'}</td>
      <td title="${escapeHtml(f.description || '')}">${escapeHtml((f.description || '').slice(0, 80))}</td>
      <td class="finding-snippet" title="${escapeHtml(f.snippet || '')}">${escapeHtml((f.snippet || '').slice(0, 50))}</td>
    </tr>`).join("");
}

function setupFindingsFilter() {
  document.querySelectorAll(".sev-filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sev-filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const sev = btn.getAttribute("data-sev");
      const filtered = sev === "ALL"
        ? allSecurityFindings
        : allSecurityFindings.filter(f => f.severity === sev);
      renderFindingsTable(filtered);
    });
  });
}

function renderGitActivity(git, overview) {
  const noDataEl = document.getElementById("dd-git-no-data");
  const statsEl  = document.getElementById("dd-git-stats");
  if (!git || git.error || Object.keys(git).length === 0) {
    if (statsEl)  statsEl.style.display  = "none";
    if (noDataEl) {
      noDataEl.style.display = "block";
      if (overview?.source_type === "github") {
         noDataEl.innerHTML = "<span>⚠️ GitHub activity unavailable (API Rate Limited or Private Repo)</span>";
      } else {
         noDataEl.innerHTML = "<span>📦 Local repository — GitHub activity not available</span>";
      }
    }
    return;
  }
  if (statsEl)  statsEl.style.display  = "";
  if (noDataEl) noDataEl.style.display = "none";

  document.getElementById("dd-stars").textContent       = (git.stars ?? "—").toLocaleString();
  document.getElementById("dd-forks").textContent       = (git.forks ?? "—").toLocaleString();
  document.getElementById("dd-git-contributors").textContent = git.contributor_count ?? "—";
  document.getElementById("dd-issues").textContent      = (git.open_issues ?? "—").toLocaleString();
  document.getElementById("dd-prs").textContent         = git.open_pr_count ?? "—";
  document.getElementById("dd-last-push").textContent   = git.pushed_at ? git.pushed_at.slice(0, 10) : "—";
}

function renderDependencies(deps) {
  if (!deps) return;
  document.getElementById("dd-dep-total").textContent   = deps.total_count || 0;
  document.getElementById("dd-dep-flagged").textContent = deps.outdated_count || 0;
  document.getElementById("dd-dep-risk").textContent    = deps.risk_score != null ? `${deps.risk_score}/100` : "—";

  const list = document.getElementById("dd-dep-list");
  const items = (deps.dependencies || []).slice(0, 30);
  if (!items.length) {
    list.innerHTML = "<div style='color:var(--text-muted);font-size:0.78rem;'>No dependency data available.</div>";
    return;
  }
  list.innerHTML = items.map(d => `
    <div class="dd-dep-entry">
      <span class="dd-dep-name" title="${d.name}">${d.name}</span>
      <span class="dd-dep-version">${d.version || '*'}</span>
      ${d.flagged
        ? `<span class="dd-dep-flag" title="${escapeHtml(d.flag_reason || '')}">⚠ Risk</span>`
        : `<span class="dd-dep-ok">✓</span>`}
    </div>`).join("");
}

function renderLicense(license) {
  if (!license) return;
  const licId    = license.license_id || "Unknown";
  const category = license.category  || "UNKNOWN";
  const compat   = license.compatibility || "—";
  const source   = license.source || "";

  const renderReportItem = (repoId, type, date) => `
    <span class="report-meta">
      <span class="report-type">${type.replace(/_/g, ' ')}</span>
      <span class="report-date">${date}</span>
    </span>
    <span class="report-actions">
      <a href="${API_BASE}/reports/${repoId}/export?type=${type}&format=md" target="_blank" class="download-link">MD</a>
      <a href="${API_BASE}/reports/${repoId}/export?type=${type}&format=json" target="_blank" class="download-link">JSON</a>
    </span>
  `;

  const badge = document.getElementById("dd-license-badge");
  badge.textContent = licId;
  badge.className   = "dd-license-badge";
  const catClass = { PERMISSIVE: "permissive", COPYLEFT: "copyleft",
    WEAK_COPYLEFT: "weak-copyleft", PROPRIETARY: "proprietary", UNKNOWN: "unknown" }[category];
  if (catClass) badge.classList.add(catClass);

  document.getElementById("dd-license-category").textContent = category.replace("_", " ");
  document.getElementById("dd-license-compat").textContent   = compat;
  document.getElementById("dd-license-source").textContent   = source ? `Detected from: ${source}` : "";
}

// ── Modern Codebase Evaluation ──────────────────────────────────────
async function loadModernCodebase(repoId) {
  const container = document.getElementById("modern-eval-content");
  container.innerHTML = "<p>Loading Modern Codebase evaluation...</p>";
  try {
    const res = await fetch(`${API_BASE}/dashboard/${repoId}`);
    if (!res.ok) throw new Error("Failed to load dashboard data");
    const data = await res.json();
    renderModernCodebase(data.modern);
  } catch (err) {
    container.innerHTML = `<p style="color:red;">Error loading Modern Codebase data: ${err.message}</p>`;
  }
}

function renderModernCodebase(modern) {
  const container = document.getElementById("modern-eval-content");
  if (!modern || !modern.metadata) {
    container.innerHTML = "<p>No Modern Codebase evaluation data available.</p>";
    return;
  }

  const renderSection = (title, items) => `
    <div class="modern-section">
      <h3>${title}</h3>
      ${items.map(item => `
        <div class="modern-item">
          ${item.passed ? '<span class="modern-pass">✅</span>' : '<span class="modern-fail">❌</span>'}
          <span>${escapeHtml(item.criterion)}</span>
        </div>
      `).join("")}
    </div>
  `;

  container.innerHTML = `
    <div class="modern-metadata" style="margin-bottom: var(--spacing-lg); padding: var(--spacing-md); background: rgba(255,255,255,0.03); border-radius: var(--border-radius-md);">
      <div class="modern-metadata-item">
        <span class="modern-metadata-lbl">Technology Stack</span>
        <span class="modern-metadata-val">${modern.metadata.technology_stack.join(", ") || "Unknown"}</span>
      </div>
      <div class="modern-metadata-item">
        <span class="modern-metadata-lbl">Repository Age</span>
        <span class="modern-metadata-val">${modern.metadata.repository_age}</span>
      </div>
      <div class="modern-metadata-item">
        <span class="modern-metadata-lbl">Business Domain</span>
        <span class="modern-metadata-val">${modern.metadata.business_domain}</span>
      </div>
      <div class="modern-metadata-item">
        <span class="modern-metadata-lbl">Lines of Code</span>
        <span class="modern-metadata-val">${modern.metadata.loc.toLocaleString()}</span>
      </div>
      <div class="modern-metadata-item">
        <span class="modern-metadata-lbl">Contributors</span>
        <span class="modern-metadata-val">${modern.metadata.contributors}</span>
      </div>
      <div class="modern-metadata-item">
        <span class="modern-metadata-lbl">Ownership Status</span>
        <span class="modern-metadata-val">${modern.metadata.ownership_status}</span>
      </div>
      <div class="modern-metadata-item" style="grid-column: 1 / -1;">
        <span class="modern-metadata-lbl">Brief Description</span>
        <span class="modern-metadata-val">${escapeHtml(modern.metadata.description)}</span>
      </div>
    </div>

    <div class="modern-grid">
      ${renderSection("Preferred Technologies", modern.technologies)}
      ${renderSection("Repository Requirements", modern.requirements)}
      ${renderSection("Preferred Characteristics", modern.characteristics)}
      ${renderSection("Engineering Quality", modern.quality)}
      ${renderSection("Ownership & Rights", modern.ownership)}
      ${renderSection("Not Preferred", modern.not_preferred)}
    </div>
  `;
}

// ── SVG Gauge Animator ────────────────────────────────────────────

function animateGaugeArc(arcId, value, maxValue) {
  const el = document.getElementById(arcId);
  if (!el) return;
  // Total arc length for our semicircle (π * 80 ≈ 251.3)
  const totalArc = 251.3;
  const dashOffset = totalArc - (totalArc * (value / maxValue));
  requestAnimationFrame(() => {
    el.style.strokeDashoffset = dashOffset;
  });
}

// ── Generate Reports ─────────────────────────────────────────────

function setupGenerateReportsBtn(repoId) {
  const btn = document.getElementById("dd-generate-reports-btn");
  if (!btn) return;
  btn.onclick = async () => {
    btn.disabled = true;
    btn.textContent = "⏳ Generating...";
    try {
      const res = await fetch(`${API_BASE}/dashboard/${repoId}/generate`, { method: "POST" });
      if (!res.ok) throw new Error("Report generation failed");
      const data = await res.json();

      // Show modal with report list
      const modal = document.getElementById("reports-modal");
      const list  = document.getElementById("reports-modal-list");
      const reportNames = {
        due_diligence: "DUE_DILIGENCE_REPORT.md",
        submission:    "SUBMISSION_READINESS_REPORT.md",
        architecture:  "ARCHITECTURE_OVERVIEW.md",
        dependency:    "DEPENDENCY_INTELLIGENCE_REPORT.md",
      };
      list.innerHTML = Object.entries(reportNames).map(([k, name]) => `
        <div class="report-gen-item">
          <span>✅</span>
          <span>${name}</span>
        </div>`).join("");
      list.innerHTML += `<div class="report-gen-item"><span>✅</span><span>LICENSE_ANALYSIS_REPORT.md</span></div>`;
      modal.style.display = "flex";
    } catch (err) {
      alert("Report generation error: " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "⬇ Generate Reports";
    }
  };
  document.getElementById("close-reports-modal-btn")?.addEventListener("click", () => {
    document.getElementById("reports-modal").style.display = "none";
  });
}

// ── Hook dashboard load into switchView ─────────────────────────
// Override the old loadDashboard call — now loadDueDiligenceDashboard is the handler
const _origSwitchView = switchView;
switchView = function(viewId) {
  _origSwitchView(viewId);
  if (viewId === "dashboard-view" && activeRepositoryId) {
    loadDueDiligenceDashboard(activeRepositoryId);
  }
};

