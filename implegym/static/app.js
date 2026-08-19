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

// Load Problem Explorer Table
async function loadProblems() {
  const search = document.getElementById("search-input").value;
  const category = document.getElementById("category-select").value;
  const maxDiff = document.getElementById("difficulty-slider").value;
  const status = document.getElementById("status-select").value;

  const url = new URL("/api/problems", window.location.origin);
  if (search) url.searchParams.append("search", search);
  if (category) url.searchParams.append("category", category);
  url.searchParams.append("max_difficulty", maxDiff);
  url.searchParams.append("solved_status", status);

  try {
    const res = await fetch(url);
    const data = await res.json();
    renderProblemTable(data.items);
  } catch (err) {
    console.error("Failed to fetch problems:", err);
  }
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
    const tagsHtml = p.tags ? p.tags.map((t) => `<span class="tag-pill">${t}</span>`).join("") : "";
    const solveTime = p.best_time_seconds ? `⚡ ${formatDuration(p.best_time_seconds)}` : "-";

    tr.innerHTML = `
      <td><span class="diff-badge ${diffClass}">${p.difficulty}/10</span></td>
      <td><b>${p.title}</b> ${p.is_solved ? '<span style="color: var(--accent-success);">✓ AC</span>' : ''}</td>
      <td>${p.category}</td>
      <td>${tagsHtml}</td>
      <td>${solveTime}</td>
      <td>
        <button class="btn btn-primary btn-sm" onclick="startManualSession('${p.slug}')">🎯 Practice</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
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

  // Render Markdown + LaTeX
  const stmtBody = document.getElementById("stmt-body");
  stmtBody.innerHTML = marked.parse(prob.statement);
  
  if (prob.constraints) {
    stmtBody.innerHTML += `<h4>Constraints</h4>` + marked.parse(prob.constraints);
  }

  // Render Sample Cases
  const sampleContainer = document.getElementById("stmt-samples");
  sampleContainer.innerHTML = "<h4>Sample Cases</h4>";
  if (prob.sample_cases) {
    prob.sample_cases.forEach((sc, i) => {
      sampleContainer.innerHTML += `
        <div style="margin-top: 0.5rem;">
          <b>Sample Input ${i + 1}</b>
          <pre>${sc.input}</pre>
          <b>Sample Output ${i + 1}</b>
          <pre>${sc.output}</pre>
        </div>
      `;
    });
  }

  // Trigger KaTeX math rendering
  if (window.renderMathInElement) {
    window.renderMathInElement(stmtBody, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
    });
  }

  // Start Stopwatch
  startStopwatch(session.started_at, session.status === "ac" ? session.finished_at : null);
}

// Live Stopwatch Timer
function startStopwatch(startTimeStr, endTimeStr) {
  if (stopwatchInterval) clearInterval(stopwatchInterval);

  const startTime = new Date(startTimeStr).getTime();
  const timerElem = document.getElementById("stopwatch-timer");
  const statusElem = document.getElementById("session-status-text");

  if (endTimeStr) {
    // Session is completed / ACed
    const endTime = new Date(endTimeStr).getTime();
    const duration = (endTime - startTime) / 1000;
    timerElem.textContent = formatDuration(duration);
    statusElem.textContent = "🏆 SOLVED (AC)";
    statusElem.style.color = "var(--accent-success)";
    return;
  }

  statusElem.textContent = "WORKOUT IN PROGRESS";
  statusElem.style.color = "var(--accent-success)";

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

// Submit Solution
async function submitCode() {
  if (!activeSession) {
    alert("Please select a problem first!");
    return;
  }

  const code = document.getElementById("code-editor").value;
  const compiler = document.getElementById("compiler-select").value;
  const flags = document.getElementById("compiler-flags").value;

  const btn = document.getElementById("btn-submit");
  btn.disabled = true;
  btn.textContent = "⏳ Judging...";

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

    if (data.session && data.session.status === "ac") {
      activeSession = data.session;
      startStopwatch(activeSession.started_at, activeSession.finished_at);
    }
  } catch (err) {
    alert("Submission error: " + err.message);
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

// AI Code Refinement
async function openAiRefinement(submissionId) {
  const drawer = document.getElementById("ai-drawer");
  const content = document.getElementById("drawer-content");
  drawer.style.display = "flex";
  content.innerHTML = `<div class="loading-spinner">✨ Analyzing submission with OpenAI GPT...</div>`;

  try {
    const res = await fetch(`/api/submissions/${submissionId}/refine`, { method: "POST" });
    const review = await res.json();

    let html = `<div>${marked.parse(review.feedback_markdown)}</div>`;
    if (review.suggestions && review.suggestions.length > 0) {
      html += `<h3>Structured Suggestions</h3>`;
      review.suggestions.forEach((s) => {
        html += `
          <div class="ai-suggestion-card">
            <h4>[${s.category}] ${s.title}</h4>
            <p>${s.detail}</p>
            ${s.code_diff ? `<pre><code>${s.code_diff}</code></pre>` : ''}
          </div>
        `;
      });
    }
    content.innerHTML = html;
  } catch (err) {
    content.innerHTML = `<div class="alert alert-danger">Failed to get AI refinement: ${err.message}</div>`;
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
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No practice sessions recorded yet.</td></tr>`;
      return;
    }

    sessions.forEach((s) => {
      const tr = document.createElement("tr");
      const duration = s.total_duration_seconds ? formatDuration(s.total_duration_seconds) : "-";
      const dateStr = new Date(s.started_at).toLocaleString();

      tr.innerHTML = `
        <td>#${s.id}</td>
        <td><b>${s.problem.title}</b> (${s.problem.difficulty}/10)</td>
        <td><span class="verdict-badge ${s.status}">${s.status.toUpperCase()}</span></td>
        <td>${duration}</td>
        <td>${s.submission_count}</td>
        <td>${dateStr}</td>
        <td>
          <button class="btn btn-primary btn-sm" onclick="startManualSession('${s.problem.slug}')">Replay</button>
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
  // Quick Sample button
  document.getElementById("btn-quick-sample").addEventListener("click", () => {
    document.getElementById("sampler-modal").style.display = "flex";
  });

  document.getElementById("btn-close-sampler-modal").addEventListener("click", () => {
    document.getElementById("sampler-modal").style.display = "none";
  });

  document.getElementById("btn-close-drawer").addEventListener("click", () => {
    document.getElementById("ai-drawer").style.display = "none";
  });

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

  // Filter Event Listeners
  document.getElementById("search-input").addEventListener("input", debounce(loadProblems, 300));
  document.getElementById("category-select").addEventListener("change", loadProblems);
  document.getElementById("status-select").addEventListener("change", loadProblems);
  document.getElementById("difficulty-slider").addEventListener("input", (e) => {
    document.getElementById("difficulty-label").textContent = e.target.value;
    loadProblems();
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
