/**
 * ImpleGym - Gym Workout & Stopwatch Logic
 */

let currentProblem = null;
let activeSession = null;
let stopwatchInterval = null;
let currentSubmissionId = null;
let allContestSessions = [];

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

// Load and Render Contest Sessions Tabs
async function loadContestsList(activeSessionId = null) {
  const tabsContainer = document.getElementById("contest-session-tabs");
  if (!tabsContainer) return;

  try {
    const res = await fetch("/api/history/sessions?limit=50");
    if (!res.ok) return;
    allContestSessions = await res.json();

    tabsContainer.innerHTML = "";

    if (!allContestSessions || allContestSessions.length === 0) {
      tabsContainer.innerHTML = `<span style="color: var(--text-muted); font-size: 0.85rem; font-style: italic;">No contests created yet. Click "+" to create one!</span>`;
      const emptyHero = document.getElementById("empty-contest-hero");
      if (emptyHero && !activeSession) emptyHero.style.display = "block";
      return;
    }

    const emptyHero = document.getElementById("empty-contest-hero");
    if (emptyHero) emptyHero.style.display = "none";

    const currentActiveId = activeSessionId || (activeSession ? activeSession.id : null);

    allContestSessions.forEach((sess) => {
      const tab = document.createElement("button");
      const isActive = currentActiveId === sess.id;
      const isAc = sess.status === "ac";
      const isRunning = sess.status === "active";

      let classNames = ["contest-session-tab"];
      if (isActive) classNames.push("active");
      if (isAc) classNames.push("status-ac");

      let badgeClass = "badge-stopped";
      let badgeText = "STOPPED";
      if (isRunning) {
        badgeClass = "badge-active";
        badgeText = "ACTIVE";
      } else if (isAc) {
        badgeClass = "badge-ac";
        badgeText = `${sess.solved_count}/${sess.num_problems} AC`;
      } else if (sess.solved_count > 0) {
        badgeClass = "badge-stopped";
        badgeText = `${sess.solved_count}/${sess.num_problems} SOLVED`;
      }

      tab.className = classNames.join(" ");
      tab.innerHTML = `
        <span>🏆 ${sess.name || `Contest #${sess.id}`}</span>
        <span class="contest-tab-badge ${badgeClass}">${badgeText}</span>
      `;

      tab.addEventListener("click", async () => {
        await selectContestSession(sess.id);
      });

      tabsContainer.appendChild(tab);
    });

    // Append "+" quick create button at end of tabs
    const plusBtn = document.createElement("button");
    plusBtn.className = "contest-tab-plus-btn";
    plusBtn.id = "btn-add-contest-tab";
    plusBtn.title = "Create New Contest";
    plusBtn.textContent = "+";
    plusBtn.addEventListener("click", () => {
      const modal = document.getElementById("contest-modal");
      if (modal) modal.style.display = "flex";
    });
    tabsContainer.appendChild(plusBtn);

  } catch (err) {
    console.error("Failed to load contests list:", err);
  }
}

// Select and load a contest session
async function selectContestSession(sessionId) {
  try {
    const res = await fetch(`/api/session/${sessionId}`);
    if (!res.ok) throw new Error("Failed to load contest session");
    const session = await res.json();
    setWorkoutSession(session);
    await loadContestsList(session.id);
  } catch (err) {
    alert("Error loading contest session: " + err.message);
  }
}

// Check URL Params for ?slug= or fetch active / latest session
async function checkUrlOrActiveSession() {
  let loadedSession = null;

  // 1. First check if there is an active session on the server
  try {
    const activeRes = await fetch("/api/session/active");
    if (activeRes.ok) {
      const sess = await activeRes.json();
      if (sess && (sess.status === "active" || sess.status === "in_progress")) {
        loadedSession = sess;
      }
    }
  } catch (e) {
    console.warn("Could not check active session:", e);
  }

  // 2. If active session exists, load it
  if (loadedSession) {
    setWorkoutSession(loadedSession);
    await loadContestsList(loadedSession.id);
    return;
  }

  // 3. Check for ?slug= to preview single problem
  const urlParams = new URLSearchParams(window.location.search);
  const slug = urlParams.get("slug");
  if (slug) {
    await loadProblemPreview(slug);
    await loadContestsList();
    return;
  }

  // 4. Otherwise load the most recent contest session
  try {
    const histRes = await fetch("/api/history/sessions?limit=1");
    if (histRes.ok) {
      const historyList = await histRes.json();
      if (historyList && historyList.length > 0) {
        setWorkoutSession(historyList[0]);
        await loadContestsList(historyList[0].id);
        return;
      }
    }
  } catch (e) {
    console.warn("Could not check history sessions:", e);
  }

  // 5. If absolutely no sessions exist, show empty state
  await loadContestsList();
  const emptyHero = document.getElementById("empty-contest-hero");
  if (emptyHero) emptyHero.style.display = "block";
}

const gymProblemDetailCache = new Map();

// Load problem in Preview / Ready mode with ETag 304 caching
async function loadProblemPreview(slug) {
  const cacheKey = `gym_prob_${slug}`;
  let cached = gymProblemDetailCache.get(cacheKey);
  if (!cached) {
    try {
      const stored = sessionStorage.getItem(cacheKey);
      if (stored) cached = JSON.parse(stored);
    } catch (e) {}
  }

  // Instant render from cache
  if (cached && cached.data) {
    setProblemPreview(cached.data);
  }

  const headers = {};
  if (cached && cached.etag) {
    headers["If-None-Match"] = cached.etag;
  }

  try {
    const res = await fetch(`/api/problems/${encodeURIComponent(slug)}`, { headers });
    if (res.status === 304) {
      // 304 Not Modified - cached data is fresh and already set!
      return;
    }
    if (!res.ok) throw new Error("Problem not found");
    const prob = await res.json();
    const etag = res.headers.get("ETag");

    const entry = { etag, data: prob };
    gymProblemDetailCache.set(cacheKey, entry);
    try {
      sessionStorage.setItem(cacheKey, JSON.stringify(entry));
    } catch (e) {}

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
  document.getElementById("stmt-category").textContent = `${prob.category} (Diff: ${prob.difficulty})`;
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

  // Hide contest tabs when in preview mode
  const contestContainer = document.getElementById("contest-hud-container");
  if (contestContainer) contestContainer.style.display = "none";
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

const problemCodeDrafts = new Map();

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

  // Render Contest HUD & Problem Tabs
  renderContestTabs(session);

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

  const outcomeCard = document.getElementById("workout-outcome-card");
  if (session.status === "ac") {
    renderWorkoutOutcome(session, null);
  } else if (outcomeCard) {
    outcomeCard.style.display = "none";
  }
}

// Render Contest Header & Problem Switcher Tabs
function renderContestTabs(session) {
  const contestContainer = document.getElementById("contest-hud-container");
  const tabsContainer = document.getElementById("contest-problem-tabs");
  const nameDisplay = document.getElementById("contest-name-display");
  const progressBadge = document.getElementById("contest-progress-badge");
  const targetDisplay = document.getElementById("contest-target-display");

  if (!contestContainer || !tabsContainer) return;

  const problems = session.problems && session.problems.length > 0 ? session.problems : [session.problem];
  const numProblems = session.num_problems || problems.length;
  const solvedCount = session.solved_count || 0;
  const statuses = session.problem_statuses || {};

  contestContainer.style.display = "flex";
  if (nameDisplay) {
    nameDisplay.textContent = session.name || "Gym Contest";
  }
  if (progressBadge) {
    progressBadge.textContent = `${solvedCount} / ${numProblems} Solved`;
    if (solvedCount === numProblems && numProblems > 0) {
      progressBadge.className = "contest-progress-badge";
      progressBadge.style.backgroundColor = "rgba(16, 185, 129, 0.35)";
      progressBadge.style.color = "#34d399";
    }
  }
  if (targetDisplay) {
    const totalTargetSec = session.total_target_time_seconds || (session.problem.difficulty * 5 * 60);
    targetDisplay.innerHTML = `🎯 Total Contest Target: <b>${Math.round(totalTargetSec / 60)}m</b>`;
  }

  tabsContainer.innerHTML = "";
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

  problems.forEach((p, idx) => {
    const tab = document.createElement("button");
    const letter = letters[idx] || `${idx + 1}`;
    const isSolved = statuses[String(p.id)] === "ac";
    const isActive = p.id === session.problem.id;

    let classNames = ["contest-problem-tab"];
    if (isActive) classNames.push("active");
    if (isSolved) classNames.push("solved");

    tab.className = classNames.join(" ");
    tab.innerHTML = `
      <span class="tab-letter">${letter}.</span>
      <span class="tab-title">${p.title}</span>
      <span class="diff-badge diff-${p.difficulty}" style="font-size: 0.72rem; padding: 0.1rem 0.35rem;">Diff: ${p.difficulty}</span>
      <span class="tab-status-icon">${isSolved ? "✓" : "⏳"}</span>
    `;

    tab.addEventListener("click", () => {
      if (p.id !== session.problem.id) {
        switchContestProblem(p.id, idx);
      }
    });

    tabsContainer.appendChild(tab);
  });
}

// Switch Active Problem in Contest
async function switchContestProblem(problemId, index) {
  if (!activeSession) return;

  // Save current code draft
  const editor = document.getElementById("code-editor");
  if (editor && currentProblem) {
    problemCodeDrafts.set(currentProblem.id, editor.value);
  }

  try {
    const res = await fetch("/api/session/switch-problem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: activeSession.id,
        problem_id: problemId,
        problem_index: index,
      }),
    });

    if (!res.ok) throw new Error("Failed to switch problem");
    const updatedSession = await res.json();

    // Restore draft code if available
    if (editor) {
      const savedDraft = problemCodeDrafts.get(problemId);
      if (savedDraft !== undefined) {
        editor.value = savedDraft;
      }
    }

    setWorkoutSession(updatedSession);
  } catch (err) {
    alert("Error switching problem: " + err.message);
  }
}

window.setWorkoutSession = setWorkoutSession;
window.loadContestsList = loadContestsList;

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
  // Empty State Create Contest Button
  const emptyCreateBtn = document.getElementById("btn-empty-create-contest");
  if (emptyCreateBtn) {
    emptyCreateBtn.addEventListener("click", () => {
      const modal = document.getElementById("contest-modal");
      if (modal) modal.style.display = "flex";
    });
  }

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
  // Next Random Problem from Outcome Card
  const nextOutcomeBtn = document.getElementById("btn-outcome-next");
  if (nextOutcomeBtn) {
    nextOutcomeBtn.addEventListener("click", async () => {
      try {
        const mean = currentProblem ? currentProblem.difficulty : 5.0;
        const res = await fetch("/api/sampler/sample", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mean_difficulty: mean,
            std_dev: 1.5,
            skewness: "balanced",
            exclude_solved: true,
          }),
        });
        if (!res.ok) throw new Error("Failed to sample next problem");
        const nextProb = await res.json();
        window.location.href = `/gym?slug=${encodeURIComponent(nextProb.slug)}`;
      } catch (err) {
        alert("Error fetching next problem: " + err.message);
      }
    });
  }

  // AI Refine from Outcome Card
  const outcomeRefineBtn = document.getElementById("btn-outcome-refine");
  if (outcomeRefineBtn) {
    outcomeRefineBtn.addEventListener("click", refineLatestSubmission);
  }
}

// Resume Stopwatch after judging, adjusting start time so judging latency is not penalized
function resumeStopwatchAfterJudging(judgingDurSec = 0) {
  if (!activeSession || activeSession.status === "ac" || activeSession.status === "stopped") return;
  if (judgingDurSec > 0 && activeSession.started_at) {
    const currentStartMs = parseUtcDate(activeSession.started_at);
    const adjustedStartMs = currentStartMs + (judgingDurSec * 1000);
    activeSession.started_at = new Date(adjustedStartMs).toISOString();
  }
  startStopwatch(activeSession.started_at, null, "in_progress");
}

// Handle Solution Submission
async function submitSolution() {
  if (!activeSession) {
    if (currentProblem) {
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
  const statusElem = document.getElementById("session-status-text");

  if (!code.trim()) {
    alert("Please write some code before submitting!");
    return;
  }

  btn.disabled = true;
  btn.textContent = "⏳ Running Tests...";

  // Pause the UI stopwatch while judging is in progress
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

    if (data.session) {
      activeSession = data.session;
      renderContestTabs(data.session);
    }

    if (data.session && data.session.status === "ac") {
      // Entire contest or session completed with AC -> Stop timer permanently
      const startTime = activeSession.started_at;
      const endTime = activeSession.finished_at || new Date().toISOString();
      const totalDur = activeSession.total_duration_seconds;
      startStopwatch(startTime, endTime, "ac", totalDur);
      renderWorkoutOutcome(activeSession, data.submission);
    } else if (data.submission && data.submission.verdict === "AC") {
      // Individual problem solved in contest session
      const progressBadge = document.getElementById("contest-progress-badge");
      if (progressBadge && activeSession) {
        progressBadge.textContent = `${activeSession.solved_count || 0} / ${activeSession.num_problems || 1} Solved`;
      }
      const judgingDurSec = (Date.now() - judgingStartMs) / 1000;
      resumeStopwatchAfterJudging(judgingDurSec);
      renderWorkoutOutcome(activeSession, data.submission);
    } else {
      // Not AC (WA / TLE / RE) -> Resume timer without penalizing for judging time
      const judgingDurSec = (Date.now() - judgingStartMs) / 1000;
      resumeStopwatchAfterJudging(judgingDurSec);
      const outcomeCard = document.getElementById("workout-outcome-card");
      if (outcomeCard) outcomeCard.style.display = "none";
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

// Render Workout Outcome Summary Card when problem/contest is AC
function renderWorkoutOutcome(session, sub) {
  const card = document.getElementById("workout-outcome-card");
  if (!card) return;

  const prob = (session && session.problem) ? session.problem : currentProblem;
  if (!prob) return;

  const targetSec = (session && session.total_target_time_seconds)
    ? session.total_target_time_seconds
    : (prob.difficulty * 5 * 60);
  const targetMin = Math.round(targetSec / 60);

  let durationSec = 0;
  if (session && session.total_duration_seconds !== null && session.total_duration_seconds !== undefined) {
    durationSec = session.total_duration_seconds;
  } else if (session && session.started_at) {
    const endMs = session.finished_at ? parseUtcDate(session.finished_at) : Date.now();
    durationSec = Math.max(0, (endMs - parseUtcDate(session.started_at)) / 1000);
  }

  const isSuccessful = durationSec <= targetSec;
  const outcomeBadge = isSuccessful
    ? `<span class="verdict-badge ac" title="Solved in under ${targetMin} minutes">🏆 SUCCESS</span>`
    : `<span class="verdict-badge wa" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24;" title="Solved but took longer than ${targetMin} minutes">⏱️ OVERTIME</span>`;

  const statusBadge = document.getElementById("outcome-status-badge");
  if (statusBadge) {
    statusBadge.innerHTML = isSuccessful ? "🏆 SUCCESS" : "⏱️ OVERTIME";
    statusBadge.className = isSuccessful ? "verdict-badge ac" : "verdict-badge wa";
    if (!isSuccessful) {
      statusBadge.style.background = "rgba(245, 158, 11, 0.2)";
      statusBadge.style.color = "#fbbf24";
    } else {
      statusBadge.style.background = "";
      statusBadge.style.color = "";
    }
  }

  const heading = document.getElementById("outcome-heading");
  const subtext = document.getElementById("outcome-subtext");
  if (heading) {
    heading.textContent = isSuccessful ? "🏆 Workout Completed Successfully!" : "⏱️ Workout Completed (Overtime)";
  }
  if (subtext) {
    subtext.textContent = isSuccessful
      ? `Completed in ${formatDuration(durationSec)}, beating the ${targetMin}m target time benchmark!`
      : `Completed in ${formatDuration(durationSec)}, exceeding the ${targetMin}m target time benchmark.`;
  }

  const tbody = document.getElementById("outcome-table-body");
  if (tbody) {
    const subCount = (session && session.submission_count) ? session.submission_count : (session && session.submissions ? session.submissions.length : 1);
    const maxTime = sub ? `${sub.exec_time_ms || 0} ms` : "-";
    const mem = sub ? `${sub.memory_kb || 0} KB` : "-";

    tbody.innerHTML = `
      <tr>
        <td>
          <div style="font-weight: 700; color: #818cf8;">${prob.title}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${prob.category}</div>
        </td>
        <td><span class="diff-badge diff-${prob.difficulty}">Diff: ${prob.difficulty}</span></td>
        <td><span class="tag-pill" style="color: #38bdf8; font-weight: 600;">🎯 ${targetMin} min</span></td>
        <td><b style="color: ${isSuccessful ? 'var(--accent-success)' : '#fbbf24'}; font-size: 1.05rem;">${formatDuration(durationSec)}</b></td>
        <td>${outcomeBadge}</td>
        <td><span class="badge" style="background: rgba(255,255,255,0.08); padding: 0.2rem 0.6rem; border-radius: 0.4rem;">${subCount}</span></td>
        <td><b>${maxTime}</b> <span style="font-size: 0.75rem; color: var(--text-muted);">(${mem})</span></td>
      </tr>
    `;
  }

  card.style.display = "block";
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
