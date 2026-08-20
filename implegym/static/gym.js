/**
 * ImpleGym - Gym Workout & Stopwatch Logic
 */

let currentProblem = null;
let activeSession = null;
let stopwatchInterval = null;
let currentSubmissionId = null;

document.addEventListener("DOMContentLoaded", async () => {
  await initCompilers();
  initGymListeners();
  await checkUrlOrActiveSession();
});

// Load Compilers from Backend
async function initCompilers() {
  try {
    const res = await fetch("/api/compilers");
    const compilers = await res.json();
    const select = document.getElementById("compiler-select");
    if (!select) return;
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

// Check URL Params for ?slug= or fetch active session
async function checkUrlOrActiveSession() {
  const urlParams = new URLSearchParams(window.location.search);
  const slug = urlParams.get("slug");

  if (slug) {
    // Check if there is already an active in-progress session for this problem
    try {
      const activeRes = await fetch("/api/session/active");
      if (activeRes.ok) {
        const sess = await activeRes.json();
        if (sess && sess.problem && sess.problem.slug === slug && sess.status === "in_progress") {
          setWorkoutSession(sess);
          return;
        }
      }
    } catch (e) {
      console.warn("Could not check active session:", e);
    }

    // Otherwise load problem in Preview / Ready mode
    await loadProblemPreview(slug);
  } else {
    await checkActiveSession();
  }
}

// Load problem in Preview / Ready mode
async function loadProblemPreview(slug) {
  try {
    const res = await fetch(`/api/problems/${encodeURIComponent(slug)}`);
    if (!res.ok) throw new Error("Problem not found");
    const prob = await res.json();
    setProblemPreview(prob);
  } catch (err) {
    alert("Error loading problem: " + err.message);
  }
}

// Check Active Session on Server
async function checkActiveSession() {
  try {
    const res = await fetch("/api/session/active");
    if (res.ok) {
      const session = await res.json();
      if (session && session.problem) {
        setWorkoutSession(session);
      }
    }
  } catch (err) {
    console.error("Failed to check active session:", err);
  }
}

// Display Problem in "Ready / Preview" Mode (Timer NOT started yet)
function setProblemPreview(prob) {
  currentProblem = prob;
  activeSession = null;

  if (stopwatchInterval) {
    clearInterval(stopwatchInterval);
    stopwatchInterval = null;
  }

  // Populate metadata
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

  // Render Markdown + Protected LaTeX Statement
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
            <span class="sample-label">Sample Input ${i + 1}</span>
            <pre class="sample-code">${cleanInput}</pre>
          </div>
          <div class="sample-col">
            <span class="sample-label">Sample Output ${i + 1}</span>
            <pre class="sample-code">${cleanOutput}</pre>
          </div>
        </div>
      `;
    });
    samplesHtml += `</div>`;
    sampleContainer.innerHTML = samplesHtml;
  }

  // Trigger KaTeX rendering
  triggerKaTeX(stmtBody);
  triggerKaTeX(sampleContainer);

  // HUD in Ready State
  const timerElem = document.getElementById("stopwatch-timer");
  const statusElem = document.getElementById("session-status-text");
  const pulseElem = document.getElementById("stopwatch-pulse");
  const stopBtn = document.getElementById("btn-stop-session");
  const startBtnHud = document.getElementById("btn-start-practice");
  const startBtnBanner = document.getElementById("btn-start-practice-banner");

  if (timerElem) timerElem.textContent = "00:00:00.0";
  if (statusElem) {
    statusElem.textContent = "🎯 READY TO PRACTICE";
    statusElem.style.color = "#38bdf8";
  }
  if (pulseElem) pulseElem.style.display = "none";
  if (stopBtn) stopBtn.style.display = "none";
  if (startBtnHud) startBtnHud.style.display = "inline-block";
  if (startBtnBanner) startBtnBanner.style.display = "inline-block";

  // Hide any previous verdict
  const verdictContainer = document.getElementById("verdict-container");
  if (verdictContainer) verdictContainer.style.display = "none";
}

// Start Practice & Stopwatch (Triggered on click "Start Practice")
async function startPractice() {
  if (!currentProblem) {
    alert("Please select a problem first!");
    return;
  }

  const startBtnHud = document.getElementById("btn-start-practice");
  const startBtnBanner = document.getElementById("btn-start-practice-banner");
  if (startBtnHud) startBtnHud.disabled = true;
  if (startBtnBanner) startBtnBanner.disabled = true;

  try {
    const res = await fetch("/api/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem_slug: currentProblem.slug }),
    });

    if (!res.ok) throw new Error("Failed to start session");
    const session = await res.json();
    setWorkoutSession(session);
  } catch (err) {
    alert("Error starting practice session: " + err.message);
  } finally {
    if (startBtnHud) startBtnHud.disabled = false;
    if (startBtnBanner) startBtnBanner.disabled = false;
  }
}

// Populate Active Workout Session in UI (Timer running / restored)
function setWorkoutSession(session) {
  activeSession = session;
  currentProblem = session.problem;

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

  // Render Markdown + Protected LaTeX Statement
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
            <span class="sample-label">Sample Input ${i + 1}</span>
            <pre class="sample-code">${cleanInput}</pre>
          </div>
          <div class="sample-col">
            <span class="sample-label">Sample Output ${i + 1}</span>
            <pre class="sample-code">${cleanOutput}</pre>
          </div>
        </div>
      `;
    });
    samplesHtml += `</div>`;
    sampleContainer.innerHTML = samplesHtml;
  }

  // Trigger KaTeX rendering
  triggerKaTeX(stmtBody);
  triggerKaTeX(sampleContainer);

  // Hide Start Practice Buttons
  const startBtnHud = document.getElementById("btn-start-practice");
  const startBtnBanner = document.getElementById("btn-start-practice-banner");
  if (startBtnHud) startBtnHud.style.display = "none";
  if (startBtnBanner) startBtnBanner.style.display = "none";

  // Start / Restore Live Stopwatch
  const totalDur = session.total_duration_seconds !== undefined ? session.total_duration_seconds : null;
  startStopwatch(session.started_at, session.finished_at, session.status, totalDur);
}

// Live Stopwatch Manager
function startStopwatch(startTimeStr, endTimeStr = null, status = "in_progress", totalDurationSec = null) {
  if (stopwatchInterval) {
    clearInterval(stopwatchInterval);
    stopwatchInterval = null;
  }

  const timerElem = document.getElementById("stopwatch-timer");
  const statusElem = document.getElementById("session-status-text");
  const pulseElem = document.getElementById("stopwatch-pulse");
  const stopBtn = document.getElementById("btn-stop-session");

  if (!timerElem || !statusElem) return;

  const startTime = parseUtcDate(startTimeStr);

  const resolveDuration = () => {
    if (totalDurationSec !== null && totalDurationSec !== undefined) {
      return totalDurationSec;
    }
    const endTime = parseUtcDate(endTimeStr || new Date().toISOString());
    return Math.max(0, (endTime - startTime) / 1000);
  };

  // 1. Solved with Accepted (AC)
  if (status === "ac") {
    const duration = resolveDuration();
    timerElem.textContent = formatDuration(duration);
    const targetSec = currentProblem ? currentProblem.difficulty * 5 * 60 : 1500;
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

// Event Listeners for Gym Page
function initGymListeners() {
  // Start Practice Buttons
  const startBtnHud = document.getElementById("btn-start-practice");
  const startBtnBanner = document.getElementById("btn-start-practice-banner");
  if (startBtnHud) startBtnHud.addEventListener("click", startPractice);
  if (startBtnBanner) startBtnBanner.addEventListener("click", startPractice);

  // Submit Solution
  const submitBtn = document.getElementById("btn-submit");
  if (submitBtn) {
    submitBtn.addEventListener("click", submitSolution);
  }

  // Stop Session Button
  const stopBtn = document.getElementById("btn-stop-session");
  if (stopBtn) {
    stopBtn.addEventListener("click", async () => {
      if (!activeSession) return;
      if (!confirm("Are you sure you want to stop/pause this session? (Timer will stop as UNSOLVED)")) return;

      try {
        const res = await fetch("/api/session/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: activeSession.id }),
        });
        if (!res.ok) throw new Error("Failed to stop session");
        const session = await res.json();
        activeSession = session;
        startStopwatch(session.started_at, session.finished_at, "stopped", session.total_duration_seconds);
      } catch (err) {
        alert("Error stopping session: " + err.message);
      }
    });
  }

  // AI Refine Button
  const refineBtn = document.getElementById("btn-refine-latest");
  if (refineBtn) {
    refineBtn.addEventListener("click", refineLatestSubmission);
  }

  // Delete Submission Button
  const delSubBtn = document.getElementById("btn-delete-submission");
  if (delSubBtn) {
    delSubBtn.addEventListener("click", () => {
      if (currentSubmissionId) deleteSubmissionRecord(currentSubmissionId);
    });
  }

  // Close AI Drawer Button
  const closeDrawerBtn = document.getElementById("btn-close-drawer");
  const aiDrawer = document.getElementById("ai-drawer");
  if (closeDrawerBtn && aiDrawer) {
    closeDrawerBtn.addEventListener("click", () => {
      aiDrawer.style.display = "none";
    });
  }
}

// Handle Solution Submission
async function submitSolution() {
  if (!activeSession) {
    // If user submits while in preview mode, auto-start practice session first
    if (currentProblem) {
      const shouldStart = confirm("Start practice stopwatch now and submit your solution?");
      if (!shouldStart) return;
      await startPractice();
      if (!activeSession) return;
    } else {
      alert("Please select a problem first!");
      return;
    }
  }

  const code = document.getElementById("code-editor").value;
  const compiler = document.getElementById("compiler-select").value;
  const flags = document.getElementById("compiler-flags").value;
  const btn = document.getElementById("btn-submit");

  if (!code.trim()) {
    alert("Please write some code before submitting!");
    return;
  }

  btn.disabled = true;
  btn.textContent = "⏳ Running Tests...";

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

// Refine with AI
async function refineLatestSubmission() {
  if (!currentSubmissionId) {
    alert("No active submission to refine!");
    return;
  }
  const drawer = document.getElementById("ai-drawer");
  const content = document.getElementById("drawer-content");
  if (drawer) drawer.style.display = "flex";
  if (content) content.innerHTML = `<div class="loading-spinner">✨ AI is analyzing your solution architecture, time complexity, and memory layout...</div>`;

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
    if (content) {
      content.innerHTML = html;
      triggerKaTeX(content);
    }
  } catch (err) {
    if (content) content.innerHTML = `<div class="alert alert-danger">Failed to get AI refinement: ${err.message}</div>`;
  }
}

// Delete Submission Record
async function deleteSubmissionRecord(subId) {
  if (!confirm(`Are you sure you want to delete submission #${subId}?`)) return;
  try {
    const res = await fetch(`/api/submissions/${subId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete submission");
    document.getElementById("verdict-container").style.display = "none";
    currentSubmissionId = null;
  } catch (err) {
    alert("Error deleting submission: " + err.message);
  }
}
