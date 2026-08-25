// ImpleGym Frontend Application Logic

let activeSession = null;
let stopwatchInterval = null;
let currentSubmissionId = null;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initCompilers();
  initCategories();
  loadProblems();
  loadHistory();
  initEventListeners();
  checkActiveSession();
});

// Tab Switching
function initTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));

      tab.classList.add("active");
      const targetPane = document.getElementById(`tab-${tab.dataset.tab}`);
      if (targetPane) targetPane.classList.add("active");

      if (tab.dataset.tab === "history") loadHistory();
      if (tab.dataset.tab === "explorer") loadProblems();
    });
  });
}

// Load Compilers from Backend
async function initCompilers() {
  try {
    const res = await fetch("/api/compilers");
    const compilers = await res.json();
    const select = document.getElementById("compiler-select");
    select.innerHTML = "";
    compilers.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.name} (${c.executable})`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("Failed to load compilers:", err);
  }
}

// Load Categories
async function initCategories() {
  try {
    const res = await fetch("/api/categories");
    const categories = await res.json();
    const select = document.getElementById("category-select");
    categories.forEach((cat) => {
      const opt = document.createElement("option");
      opt.value = cat;
      opt.textContent = cat;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("Failed to load categories:", err);
  }
}

let currentProblemPage = 1;
let currentProblemPageSize = 20;
let totalProblemsCount = 0;
let totalProblemPages = 1;

// Load Problem Explorer Table with Pagination
async function loadProblems(page = 1) {
  currentProblemPage = page;
  const search = document.getElementById("search-input").value;
  const category = document.getElementById("category-select").value;
  const maxDiff = document.getElementById("difficulty-slider").value;
  const status = document.getElementById("status-select").value;
  const pageSizeSelect = document.getElementById("page-size-select");
  if (pageSizeSelect) {
    currentProblemPageSize = parseInt(pageSizeSelect.value) || 20;
  }

  const url = new URL("/api/problems", window.location.origin);
  if (search) url.searchParams.append("search", search);
  if (category) url.searchParams.append("category", category);
  url.searchParams.append("max_difficulty", maxDiff);
  url.searchParams.append("solved_status", status);
  url.searchParams.append("page", currentProblemPage);
  url.searchParams.append("page_size", currentProblemPageSize);

  try {
    const res = await fetch(url);
    const data = await res.json();
    totalProblemsCount = data.total;
    totalProblemPages = data.total_pages;
    renderProblemTable(data.items);
    renderPaginationControls(data);
  } catch (err) {
    console.error("Failed to fetch problems:", err);
  }
}

function renderPaginationControls(data) {
  const summaryElem = document.getElementById("pagination-summary");
  const numbersElem = document.getElementById("pagination-numbers");
  const firstBtn = document.getElementById("btn-page-first");
  const prevBtn = document.getElementById("btn-page-prev");
  const nextBtn = document.getElementById("btn-page-next");
  const lastBtn = document.getElementById("btn-page-last");

  if (!summaryElem || !numbersElem) return;

  const start = data.total === 0 ? 0 : (data.page - 1) * data.page_size + 1;
  const end = Math.min(data.page * data.page_size, data.total);
  summaryElem.textContent = `Showing ${start}-${end} of ${data.total} problems`;

  firstBtn.disabled = data.page <= 1;
  prevBtn.disabled = data.page <= 1;
  nextBtn.disabled = data.page >= data.total_pages || data.total_pages === 0;
  lastBtn.disabled = data.page >= data.total_pages || data.total_pages === 0;

  numbersElem.innerHTML = "";
  const totalP = Math.max(1, data.total_pages);
  const curP = data.page;

  // Generate page pills with ellipses
  const pageRange = [];
  for (let i = 1; i <= totalP; i++) {
    if (i === 1 || i === totalP || (i >= curP - 2 && i <= curP + 2)) {
      pageRange.push(i);
    }
  }

  let lastP = 0;
  pageRange.forEach((p) => {
    if (lastP && p - lastP > 1) {
      const ell = document.createElement("span");
      ell.className = "page-pill ellipsis";
      ell.textContent = "...";
      numbersElem.appendChild(ell);
    }
    const btn = document.createElement("button");
    btn.className = `page-pill ${p === curP ? "active" : ""}`;
    btn.textContent = p;
    btn.onclick = () => loadProblems(p);
    numbersElem.appendChild(btn);
    lastP = p;
  });
}

function renderProblemTable(problems) {
  const tbody = document.getElementById("problem-table-body");
  tbody.innerHTML = "";

  if (!problems || problems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No problems found matching criteria.</td></tr>`;
    return;
  }

  problems.forEach((p) => {
    const tr = document.createElement("tr");
    const diffClass = `diff-${p.difficulty}`;
    const targetMin = p.difficulty * 5;
    
    let solveStatusHtml = `<span style="color: var(--text-muted); font-size: 0.85rem;">Unsolved</span>`;
    if (p.is_successful && p.best_time_seconds) {
      solveStatusHtml = `<span style="color: #34d399; font-weight: 700;" title="AC under target time">🏆 Success (${formatDuration(p.best_time_seconds)})</span>`;
    } else if (p.is_solved && p.best_time_seconds) {
      solveStatusHtml = `<span style="color: #fbbf24; font-weight: 600;" title="AC but exceeded ${targetMin}m target">⏱️ AC (${formatDuration(p.best_time_seconds)})</span>`;
    } else if (p.is_solved) {
      solveStatusHtml = `<span style="color: #34d399; font-weight: 700;">✓ AC</span>`;
    }

    tr.innerHTML = `
      <td>
        <select class="diff-select ${diffClass}" onchange="changeProblemDifficulty('${p.slug}', this.value)" title="Click to manually update difficulty">
          ${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
            .map((d) => `<option value="${d}" ${d === p.difficulty ? "selected" : ""}>${d}/10</option>`)
            .join("")}
        </select>
      </td>
      <td><b>${p.title}</b></td>
      <td>${p.category}</td>
      <td><span class="tag-pill" style="color: #38bdf8; font-weight: 600;">🎯 ${targetMin} min</span></td>
      <td>${solveStatusHtml}</td>
      <td>
        <button class="btn btn-primary btn-sm" onclick="startManualSession('${p.slug}')">🎯 Practice</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// Manually Update Problem Difficulty
async function changeProblemDifficulty(slug, newDiff) {
  try {
    const res = await fetch(`/api/problems/${slug}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ difficulty: parseInt(newDiff) }),
    });
    if (!res.ok) throw new Error("Failed to update difficulty");
    const updated = await res.json();
    console.log(`Updated ${slug} difficulty to ${updated.difficulty}`);
  } catch (err) {
    alert("Error updating difficulty: " + err.message);
    loadProblems();
  }
}

// Start Session via Manual Selection
async function startManualSession(slug) {
  try {
    const res = await fetch("/api/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem_slug: slug }),
    });
    if (!res.ok) throw new Error("Failed to start session");
    const session = await res.json();
    setWorkoutSession(session);
  } catch (err) {
    alert("Error starting session: " + err.message);
  }
}

// Check Active Session on Page Load
async function checkActiveSession() {
  try {
    const res = await fetch("/api/session/active");
    const session = await res.json();
    if (session) {
      setWorkoutSession(session);
    }
  } catch (err) {
    console.error("Failed to check active session:", err);
  }
}

// Math Protection & Clean Markdown Renderer
function renderMathMarkdown(rawMarkdown) {
  if (!rawMarkdown) return "";

  let text = rawMarkdown;

  // 1. Known CP parameter macro substitutions
  const paramMap = {
    "T_MAX": "500\\,000",
    "N_MAX": "200\\,000",
    "Q_MAX": "200\\,000",
    "M_MAX": "200\\,000",
    "K_MAX": "200\\,000",
    "LOG_10_A_AND_B_MAX": "37",
    "LOG_10_A_MAX": "18",
    "LOG_10_B_MAX": "18",
    "A_MAX": "10^{18}",
    "B_MAX": "10^{18}",
    "VAL_MAX": "10^9",
    "W_MAX": "10^9",
    "C_MAX": "10^9",
    "X_MAX": "10^9",
  };

  for (const [k, v] of Object.entries(paramMap)) {
    text = text.replaceAll(`@{param.${k}}`, v);
    text = text.replaceAll(`{${k}}`, `{${v}}`);
    text = text.replaceAll(`\\le ${k}`, `\\le ${v}`);
    text = text.replaceAll(`\\leq ${k}`, `\\leq ${v}`);
    text = text.replaceAll(`\\lt ${k}`, `\\lt ${v}`);
    text = text.replaceAll(`< ${k}`, `< ${v}`);
    text = text.replaceAll(`<= ${k}`, `<= ${v}`);
  }

  // 2. Strip Japanese language blocks if present
  text = text.replace(/@\{lang\.ja\}[\s\S]*?(@\{lang\.end\}|$)/gi, "");
  text = text.replace(/@\{lang\.en\}/gi, "");
  text = text.replace(/@\{lang\.end\}/gi, "");

  // 3. Clean Yosupo macro keywords and strip sample section headers
  text = text.replace(/##\s*@?\{?keyword\.statement\}?/gi, "### Problem Statement");
  text = text.replace(/##\s*@?\{?keyword\.constraints\}?/gi, "### Constraints");
  text = text.replace(/##\s*@?\{?keyword\.input\}?/gi, "### Input Format");
  text = text.replace(/##\s*@?\{?keyword\.output\}?/gi, "### Output Format");
  text = text.replace(/##\s*@?\{?keyword\.sample\}?[\s\S]*/gi, "");
  text = text.replace(/##\s*Sample\s*Cases[\s\S]*/gi, "");
  text = text.replace(/###\s*Sample\s*Cases[\s\S]*/gi, "");
  text = text.replace(/##\s*Samples[\s\S]*/gi, "");
  text = text.replace(/###\s*Samples[\s\S]*/gi, "");
  text = text.replace(/@\{example\.[^}]+\}/gi, "");
  text = text.replace(/@\{param\.([^}]+)\}/gi, (m, p) => p.replace(/_/g, "\\_"));
  text = text.replace(/~~~/g, "```");

  // 4. Protect Math expressions from Marked's underscore/asterisk italic parser
  const mathPlaceholders = [];

  // Protect display math: $$...$$
  text = text.replace(/\$\$([\s\S]*?)\$\$/g, (match, formula) => {
    const key = `XKMATHBLOCK${mathPlaceholders.length}X`;
    mathPlaceholders.push({ key, val: `$$${formula}$$` });
    return key;
  });

  // Protect inline math: $...$
  text = text.replace(/\$([^\$\n\r]+?)\$/g, (match, formula) => {
    const key = `XKMAINLINE${mathPlaceholders.length}X`;
    mathPlaceholders.push({ key, val: `$${formula}$` });
    return key;
  });

  // 5. Parse Markdown cleanly
  let html = marked.parse(text);

  // 6. Restore Math expressions
  mathPlaceholders.forEach(({ key, val }) => {
    html = html.replace(new RegExp(key, "g"), val);
  });

  return html;
}

// Set Active Workout Session in UI
function setWorkoutSession(session) {
  activeSession = session;
  switchTab("workout");

  // Populate metadata
  const prob = session.problem;
  document.getElementById("stmt-title").textContent = prob.title;
  document.getElementById("stmt-category").textContent = `${prob.category} (${prob.difficulty}/10)`;
  document.getElementById("current-problem-title").textContent = prob.title;
  document.getElementById("current-problem-diff").textContent = prob.difficulty;
  const diffBadge = document.getElementById("current-problem-diff-badge");
  if (diffBadge) {
    diffBadge.className = `diff-badge diff-${prob.difficulty}`;
  }
  const targetTimeElem = document.getElementById("current-target-time");
  if (targetTimeElem) {
    targetTimeElem.innerHTML = `🎯 Target: <b>${prob.difficulty * 5}m</b>`;
  }

  // Render Markdown + Protected LaTeX
  const stmtBody = document.getElementById("stmt-body");
  stmtBody.innerHTML = renderMathMarkdown(prob.statement);

  if (prob.constraints && !prob.statement.toLowerCase().includes("constraints")) {
    stmtBody.innerHTML += `<div class="constraints-box"><h4>Constraints</h4>${renderMathMarkdown(prob.constraints)}</div>`;
  }

  // Render Sample Cases
  const sampleContainer = document.getElementById("stmt-samples");
  sampleContainer.innerHTML = "";
  if (prob.sample_cases && prob.sample_cases.length > 0) {
    let samplesHtml = `<div class="sample-section"><h4>Sample Cases</h4>`;
    prob.sample_cases.forEach((sc, i) => {
      const cleanInput = (sc.input || "").trim();
      const cleanOutput = (sc.output || "").trim();
      samplesHtml += `
        <div class="sample-box">
          <div class="sample-col">
            <div class="sample-head">
              <span>Sample Input ${i + 1}</span>
              <button class="btn-copy" onclick="navigator.clipboard.writeText(\`${cleanInput.replace(/`/g, "\\`").replace(/\\/g, "\\\\")}\`)">📋 Copy</button>
            </div>
            <pre class="sample-pre">${cleanInput}</pre>
          </div>
          <div class="sample-col">
            <div class="sample-head">
              <span>Sample Output ${i + 1}</span>
              <button class="btn-copy" onclick="navigator.clipboard.writeText(\`${cleanOutput.replace(/`/g, "\\`").replace(/\\/g, "\\\\")}\`)">📋 Copy</button>
            </div>
            <pre class="sample-pre">${cleanOutput || "(empty output)"}</pre>
          </div>
        </div>
      `;
    });
    samplesHtml += `</div>`;
    sampleContainer.innerHTML = samplesHtml;
  }

  // Trigger KaTeX math rendering across all elements (including pre blocks in input/output format)
  setTimeout(() => {
    const renderContainer = document.querySelector(".problem-statement-card");
    if (window.renderMathInElement && renderContainer) {
      window.renderMathInElement(renderContainer, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\(", right: "\\)", display: false },
          { left: "\\[", right: "\\]", display: true },
        ],
        throwOnError: false,
        errorColor: "#ef4444",
        ignoredTags: ["script", "noscript", "style", "textarea"],
      });
    }
  }, 40);

  // Start Stopwatch
  startStopwatch(session.started_at, session.status === "ac" ? session.finished_at : null, session.status, session.total_duration_seconds);
}

// Timezone-Safe UTC Date Parser
function parseUtcDate(dateStr) {
  if (!dateStr) return Date.now();
  if (typeof dateStr === "number") return dateStr;
  let str = String(dateStr).trim();
  // If no timezone indicator is present, force UTC interpretation
  if (!str.endsWith("Z") && !str.includes("+") && !str.includes("-", 10)) {
    str += "Z";
  }
  return new Date(str).getTime();
}

// Live Stopwatch Timer
function startStopwatch(startTimeStr, endTimeStr, status = "active", totalDurationSec = null) {
  if (stopwatchInterval) clearInterval(stopwatchInterval);

  const startTime = parseUtcDate(startTimeStr);
  const timerElem = document.getElementById("stopwatch-timer");
  const statusElem = document.getElementById("session-status-text");
  const pulseElem = document.getElementById("stopwatch-pulse");
  const stopBtn = document.getElementById("btn-stop-session");

  // Helper to get exact duration in seconds
  const resolveDuration = () => {
    if (totalDurationSec !== null && totalDurationSec !== undefined && totalDurationSec >= 0) {
      return totalDurationSec;
    }
    const endTime = parseUtcDate(endTimeStr || new Date().toISOString());
    return Math.max(0, (endTime - startTime) / 1000);
  };

  // 1. Solved with Accepted (AC)
  if (status === "ac") {
    const duration = resolveDuration();
    timerElem.textContent = formatDuration(duration);
    const targetSec = activeSession && activeSession.problem ? activeSession.problem.difficulty * 5 * 60 : 1500;
    const isSuccessful = duration <= targetSec;
    if (isSuccessful) {
      statusElem.textContent = `🏆 SUCCESSFUL (${formatDuration(duration)} ≤ ${Math.round(targetSec / 60)}m)`;
      statusElem.style.color = "var(--accent-success)";
    } else {
      statusElem.textContent = `⏱️ SOLVED (${formatDuration(duration)} > ${Math.round(targetSec / 60)}m TARGET)`;
      statusElem.style.color = "var(--accent-warning)";
    }
    if (pulseElem) pulseElem.style.display = "none";
    if (stopBtn) stopBtn.style.display = "none";
    return;
  }

  // 2. Manually Stopped / Paused (Unsolved)
  if (status === "stopped") {
    const duration = resolveDuration();
    timerElem.textContent = formatDuration(duration);
    statusElem.textContent = "⏹️ STOPPED (UNSOLVED)";
    statusElem.style.color = "var(--accent-danger)";
    if (pulseElem) pulseElem.style.display = "none";
    if (stopBtn) stopBtn.style.display = "none";
    return;
  }

  // 3. Abandoned (Unsolved)
  if (status === "abandoned") {
    const duration = resolveDuration();
    timerElem.textContent = formatDuration(duration);
    statusElem.textContent = "⚠️ ABANDONED";
    statusElem.style.color = "var(--text-muted)";
    if (pulseElem) pulseElem.style.display = "none";
    if (stopBtn) stopBtn.style.display = "none";
    return;
  }

  // 4. In Progress
  statusElem.textContent = "WORKOUT IN PROGRESS";
  statusElem.style.color = "var(--accent-success)";
  if (pulseElem) pulseElem.style.display = "inline-block";
  if (stopBtn) stopBtn.style.display = "inline-block";

  stopwatchInterval = setInterval(() => {
    const now = Date.now();
    const elapsedSeconds = Math.max(0, (now - startTime) / 1000);
    timerElem.textContent = formatDuration(elapsedSeconds);
  }, 100);
}

function formatDuration(seconds) {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);

  const hh = String(hrs).padStart(2, "0");
  const mm = String(mins).padStart(2, "0");
  const ss = String(secs).padStart(2, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

// Resume Stopwatch after judging, adjusting start time so judging latency is not penalized
function resumeStopwatchAfterJudging(judgingDurSec = 0) {
  if (!activeSession || activeSession.status === "ac" || activeSession.status === "stopped") return;
  if (judgingDurSec > 0 && activeSession.started_at) {
    const currentStartMs = parseUtcDate(activeSession.started_at);
    const adjustedStartMs = currentStartMs + (judgingDurSec * 1000);
    activeSession.started_at = new Date(adjustedStartMs).toISOString();
  }
  startStopwatch(activeSession.started_at, null, "active");
}

// Handle Solution Submission
async function submitSolution() {
  if (!activeSession) {
    alert("Please select a problem first!");
    return;
  }

  const code = document.getElementById("code-editor").value;
  const compiler = document.getElementById("compiler-select").value;
  const flags = document.getElementById("compiler-flags").value;
  const btn = document.getElementById("btn-submit");
  const statusElem = document.getElementById("session-status-text");

  if (!code.trim()) {
    alert("Please write some code before submitting!");
    return;
  }

  btn.disabled = true;
  btn.textContent = "⏳ Running Tests...";

  // Pause stopwatch while judging is in progress
  const judgingStartMs = Date.now();
  if (statusElem) {
    statusElem.textContent = "⚖️ JUDGING IN PROGRESS (TIMER PAUSED)...";
    statusElem.style.color = "var(--accent-warning)";
  }
  if (stopwatchInterval) {
    clearInterval(stopwatchInterval);
    stopwatchInterval = null;
  }

  try {
    const res = await fetch("/api/session/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: activeSession.id,
        problem_slug: activeSession.problem.slug,
        code: code,
        compiler_profile: compiler,
        compiler_flags: flags,
      }),
    });

    const data = await res.json();
    renderVerdict(data.submission);

    if (data.submission.verdict === "AC" || (data.session && data.session.status === "ac")) {
      if (data.session) {
        activeSession = data.session;
      }
      const startTime = activeSession ? activeSession.started_at : new Date().toISOString();
      const endTime = (activeSession && activeSession.finished_at) || new Date().toISOString();
      const totalDur = activeSession ? activeSession.total_duration_seconds : null;
      startStopwatch(startTime, endTime, "ac", totalDur);
    } else {
      // Not AC -> Resume stopwatch without penalizing for judging time
      const judgingDurSec = (Date.now() - judgingStartMs) / 1000;
      resumeStopwatchAfterJudging(judgingDurSec);
    }
  } catch (err) {
    alert("Submission error: " + err.message);
    resumeStopwatchAfterJudging(0);
  } finally {
    btn.disabled = false;
    btn.textContent = "🚀 Submit Solution";
  }
}

// Render Judge Verdict
function renderVerdict(sub) {
  currentSubmissionId = sub.id;
  const container = document.getElementById("verdict-container");
  container.style.display = "block";

  const badge = document.getElementById("latest-verdict");
  badge.textContent = sub.verdict;
  badge.className = `verdict-badge ${sub.verdict.toLowerCase()}`;

  document.getElementById("verdict-time").textContent = `${sub.exec_time_ms || 0} ms`;
  document.getElementById("verdict-mem").textContent = `${sub.memory_kb || 0} KB`;

  const list = document.getElementById("testcases-list");
  list.innerHTML = "";
  if (sub.test_results) {
    sub.test_results.forEach((tc) => {
      const item = document.createElement("div");
      item.className = "testcase-item";
      item.innerHTML = `<b>${tc.name}</b>: <span class="verdict-badge ${tc.verdict.toLowerCase()}">${tc.verdict}</span> (${tc.time_ms} ms)`;
      list.appendChild(item);
    });
  }

  const errLog = document.getElementById("compiler-error-log");
  const errText = document.getElementById("compiler-error-text");
  if (sub.error_message) {
    errLog.style.display = "block";
    errText.textContent = sub.error_message;
  } else {
    errLog.style.display = "none";
  }
}

// Refine with AI
async function refineLatestSubmission() {
  if (!currentSubmissionId) {
    alert("No active submission to refine!");
    return;
  }
  switchTab("ai-refiner");
  const content = document.getElementById("review-content");
  content.innerHTML = `<div class="loading-spinner">✨ AI is analyzing your solution architecture, time complexity, and memory layout...</div>`;

  try {
    const res = await fetch(`/api/submissions/${currentSubmissionId}/refine`, { method: "POST" });
    if (!res.ok) throw new Error("AI refinement failed");
    const review = await res.json();

    let html = `
      <div class="review-card">
        <h3>AI Optimization Insights</h3>
        <div class="review-markdown">${renderMathMarkdown(review.feedback_markdown)}</div>
        <div class="review-suggestions">
          <h4>Concrete Recommendations</h4>
          ${review.suggestions
            .map(
              (s) => `
            <div class="suggestion-item">
              <div class="sugg-header">
                <b>[${s.category}] ${s.title}</b>
              </div>
              <p>${s.detail}</p>
              ${s.code_diff ? `<pre class="code-diff"><code>${s.code_diff}</code></pre>` : ""}
            </div>
          `
            )
            .join("")}
        </div>
      </div>
    `;
    content.innerHTML = html;
  } catch (err) {
    content.innerHTML = `<div class="alert alert-danger">Failed to get AI refinement: ${err.message}</div>`;
  }
}

// Delete Submission Record
async function deleteSubmissionRecord(subId) {
  if (!confirm(`Are you sure you want to delete submission #${subId}?`)) return;
  try {
    const res = await fetch(`/api/submissions/${subId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete submission");
    document.getElementById("verdict-container").style.display = "none";
    loadHistory();
  } catch (err) {
    alert("Error deleting submission: " + err.message);
  }
}

// Delete Session Record
async function deleteSessionRecord(sessionId) {
  if (!confirm(`Are you sure you want to delete session #${sessionId} and its submissions?`)) return;
  try {
    const res = await fetch(`/api/history/sessions/${sessionId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete session");
    loadHistory();
  } catch (err) {
    alert("Error deleting session: " + err.message);
  }
}

// Load Session History Table
async function loadHistory() {
  try {
    const res = await fetch("/api/history/sessions");
    const sessions = await res.json();
    const tbody = document.getElementById("history-table-body");
    tbody.innerHTML = "";

    if (!sessions || sessions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No practice sessions recorded yet.</td></tr>`;
      return;
    }

    sessions.forEach((s) => {
      const tr = document.createElement("tr");
      const duration = s.total_duration_seconds ? formatDuration(s.total_duration_seconds) : "-";
      const dateStr = new Date(s.started_at).toLocaleString();
      const targetMin = s.problem ? s.problem.difficulty * 5 : 25;
      
      let outcomeHtml = `<span class="verdict-badge ${s.status}">${s.status.toUpperCase()}</span>`;
      if (s.status === "ac") {
        if (s.is_successful) {
          outcomeHtml = `<span class="verdict-badge ac" title="Solved in under ${targetMin} minutes">🏆 SUCCESS</span>`;
        } else {
          outcomeHtml = `<span class="verdict-badge wa" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24;" title="Solved but took longer than ${targetMin} minutes">⏱️ OVERTIME</span>`;
        }
      }

      tr.innerHTML = `
        <td>#${s.id}</td>
        <td><b>${s.problem.title}</b> (${s.problem.difficulty}/10)</td>
        <td><span class="tag-pill" style="color: #38bdf8; font-weight: 600;">🎯 ${targetMin} min</span></td>
        <td>${outcomeHtml}</td>
        <td>${duration}</td>
        <td>${s.submission_count}</td>
        <td>${dateStr}</td>
        <td>
          <div style="display: flex; gap: 0.4rem;">
            <button class="btn btn-primary btn-sm" onclick="startManualSession('${s.problem.slug}')">Replay</button>
            <button class="btn btn-danger btn-sm" onclick="deleteSessionRecord(${s.id})" title="Delete session record">🗑️</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed to load history:", err);
  }
}

// Gaussian Sampler Modal & Trigger
function initEventListeners() {
  // Sync Yosupo Repo Button
  const syncBtn = document.getElementById("btn-sync-yosupo");
  if (syncBtn) {
    syncBtn.addEventListener("click", () => {
      openSyncProgressModal(() => {
        loadProblems();
        initCategories();
      });
    });
  }

  // Stop / Pause Workout Session Button
  const stopSessionBtn = document.getElementById("btn-stop-session");
  if (stopSessionBtn) {
    stopSessionBtn.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to stop/pause this workout session?")) return;
      try {
        const sessId = activeSession ? activeSession.id : null;
        const res = await fetch(`/api/session/stop${sessId ? `?session_id=${sessId}` : ""}`, {
          method: "POST",
        });
        const stopped = await res.json();
        if (stopped) {
          activeSession = stopped;
          startStopwatch(stopped.started_at, stopped.finished_at, "stopped", stopped.total_duration_seconds);
        }
      } catch (err) {
        console.error("Failed to stop session:", err);
      }
    });
  }

  // Delete Latest Submission Button
  const delSubBtn = document.getElementById("btn-delete-submission");
  if (delSubBtn) {
    delSubBtn.addEventListener("click", () => {
      if (currentSubmissionId) {
        deleteSubmissionRecord(currentSubmissionId);
      }
    });
  }

  // Quick Sampler Modalbutton
  document.getElementById("btn-quick-sample").addEventListener("click", () => {
    document.getElementById("sampler-modal").style.display = "flex";
  });

  document.getElementById("btn-close-sampler-modal").addEventListener("click", () => {
    document.getElementById("sampler-modal").style.display = "none";
  });

  document.getElementById("btn-close-drawer").addEventListener("click", () => {
    document.getElementById("ai-drawer").style.display = "none";
  });

  // AI Settings Modal
  const aiModal = document.getElementById("ai-config-modal");
  const openAiBtn = document.getElementById("btn-open-ai-config");
  const closeAiBtn = document.getElementById("btn-close-ai-modal");
  const saveAiBtn = document.getElementById("btn-save-ai-config");

  // Dynamic AI Models population
  async function populateModelOptions(providerName, currentModel = null) {
    const datalist = document.getElementById("ai-models-datalist");
    if (!datalist) return;
    datalist.innerHTML = "";
    try {
      const res = await fetch(`/api/ai/models?provider=${providerName}`);
      const data = await res.json();
      (data.models || []).forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m;
        datalist.appendChild(opt);
      });
      if (currentModel) {
        document.getElementById("ai-model-input").value = currentModel;
      } else if (data.models && data.models.length > 0 && !document.getElementById("ai-model-input").value) {
        document.getElementById("ai-model-input").value = data.models[0];
      }
    } catch (err) {
      console.error("Failed to fetch models for provider:", err);
    }
  }

  const providerSelect = document.getElementById("ai-provider-select");
  if (providerSelect) {
    providerSelect.addEventListener("change", (e) => {
      populateModelOptions(e.target.value);
    });
  }

  if (openAiBtn) {
    openAiBtn.addEventListener("click", async () => {
      aiModal.style.display = "flex";
      try {
        const res = await fetch("/api/ai/config");
        const cfg = await res.json();
        const prov = cfg.provider || "openai";
        document.getElementById("ai-provider-select").value = prov;
        await populateModelOptions(prov, cfg.model);
        document.getElementById("ai-base-input").value = cfg.api_base || "";
        document.getElementById("ai-temp-slider").value = cfg.temperature || 0.3;
        document.getElementById("ai-temp-val").textContent = cfg.temperature || 0.3;
        document.getElementById("ai-tokens-input").value = cfg.max_tokens || 4096;
        document.getElementById("current-masked-key").textContent = cfg.api_key_masked || "None";
      } catch (err) {
        console.error("Failed to load AI config:", err);
      }
    });
  }

  if (closeAiBtn) {
    closeAiBtn.addEventListener("click", () => {
      aiModal.style.display = "none";
    });
  }

  const aiTempSlider = document.getElementById("ai-temp-slider");
  if (aiTempSlider) {
    aiTempSlider.addEventListener("input", (e) => {
      document.getElementById("ai-temp-val").textContent = e.target.value;
    });
  }

  if (saveAiBtn) {
    saveAiBtn.addEventListener("click", async () => {
      const provider = document.getElementById("ai-provider-select").value;
      const model = document.getElementById("ai-model-input").value.trim() || null;
      const key = document.getElementById("ai-key-input").value.trim() || null;
      const base = document.getElementById("ai-base-input").value.trim() || null;
      const temp = parseFloat(document.getElementById("ai-temp-slider").value);
      const tokens = parseInt(document.getElementById("ai-tokens-input").value);

      saveAiBtn.disabled = true;
      saveAiBtn.textContent = "⏳ Saving...";

      try {
        const res = await fetch("/api/ai/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: provider,
            model: model,
            api_key: key,
            api_base: base,
            temperature: temp,
            max_tokens: tokens,
          }),
        });
        const data = await res.json();
        alert(data.message || "AI Settings updated successfully!");
        aiModal.style.display = "none";
        document.getElementById("ai-key-input").value = "";
      } catch (err) {
        alert("Failed to save AI config: " + err.message);
      } finally {
        saveAiBtn.disabled = false;
        saveAiBtn.textContent = "💾 Save AI Settings";
      }
    });
  }

  // Sampler Sliders
  document.getElementById("sampler-mean").addEventListener("input", (e) => {
    document.getElementById("sampler-mean-val").textContent = e.target.value;
  });
  document.getElementById("sampler-std").addEventListener("input", (e) => {
    document.getElementById("sampler-std-val").textContent = e.target.value;
  });

  // Roll Sample Button
  document.getElementById("btn-roll-sample").addEventListener("click", async () => {
    const mean = parseFloat(document.getElementById("sampler-mean").value);
    const std = parseFloat(document.getElementById("sampler-std").value);
    const skew = document.querySelector('input[name="sampler-skew"]:checked').value;
    const excludeSolved = document.getElementById("sampler-exclude-solved").checked;

    try {
      const res = await fetch("/api/session/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sampler_config: {
            mean_difficulty: mean,
            standard_deviation: std,
            skewness: skew,
            exclude_solved: excludeSolved,
          },
        }),
      });

      if (!res.ok) throw new Error("Failed to sample problem");
      const session = await res.json();
      document.getElementById("sampler-modal").style.display = "none";
      setWorkoutSession(session);
    } catch (err) {
      alert("Error sampling problem: " + err.message);
    }
  });

  // Submit Button
  document.getElementById("btn-submit").addEventListener("click", submitCode);

  // Refine Latest Submission Button
  document.getElementById("btn-refine-latest").addEventListener("click", () => {
    if (currentSubmissionId) openAiRefinement(currentSubmissionId);
  });

  // Pagination Event Listeners
  const btnFirst = document.getElementById("btn-page-first");
  const btnPrev = document.getElementById("btn-page-prev");
  const btnNext = document.getElementById("btn-page-next");
  const btnLast = document.getElementById("btn-page-last");
  const pageSizeSelect = document.getElementById("page-size-select");

  if (btnFirst) btnFirst.addEventListener("click", () => loadProblems(1));
  if (btnPrev) btnPrev.addEventListener("click", () => loadProblems(Math.max(1, currentProblemPage - 1)));
  if (btnNext) btnNext.addEventListener("click", () => loadProblems(Math.min(totalProblemPages, currentProblemPage + 1)));
  if (btnLast) btnLast.addEventListener("click", () => loadProblems(totalProblemPages));
  if (pageSizeSelect) pageSizeSelect.addEventListener("change", () => loadProblems(1));

  // Filter Event Listeners (Reset to Page 1)
  document.getElementById("search-input").addEventListener("input", debounce(() => loadProblems(1), 300));
  document.getElementById("category-select").addEventListener("change", () => loadProblems(1));
  document.getElementById("status-select").addEventListener("change", () => loadProblems(1));
  document.getElementById("difficulty-slider").addEventListener("input", (e) => {
    document.getElementById("difficulty-label").textContent = e.target.value;
    loadProblems(1);
  });

  // Forge Problem Button
  document.getElementById("btn-forge-submit").addEventListener("click", async () => {
    const topic1 = document.getElementById("forge-topic-1").value;
    const topic2 = document.getElementById("forge-topic-2").value;
    const diff = parseInt(document.getElementById("forge-diff").value);
    const extra = document.getElementById("forge-extra").value;

    const btn = document.getElementById("btn-forge-submit");
    btn.disabled = true;
    btn.textContent = "⏳ Synthesizing problem & test cases with GPT...";

    try {
      const res = await fetch("/api/ai/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic_1: topic1,
          topic_2: topic2,
          target_difficulty: diff,
          extra_instructions: extra,
        }),
      });
      const prob = await res.json();
      document.getElementById("forge-result-container").style.display = "block";
      document.getElementById("btn-practice-forged").onclick = () => startManualSession(prob.slug);
    } catch (err) {
      alert("Error generating problem: " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "⚡ Synthesize Problem with GPT";
    }
  });
}

function switchTab(tabName) {
  document.querySelectorAll(".nav-tab").forEach((t) => {
    if (t.dataset.tab === tabName) t.classList.add("active");
    else t.classList.remove("active");
  });
  document.querySelectorAll(".tab-pane").forEach((p) => {
    if (p.id === `tab-${tabName}`) p.classList.add("active");
    else p.classList.remove("active");
  });
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}
