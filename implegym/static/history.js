/**
 * ImpleGym - Session History Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  loadHistory();
});

// Load Session History Table
async function loadHistory() {
  try {
    const res = await fetch("/api/history/sessions");
    const sessions = await res.json();
    const tbody = document.getElementById("history-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!sessions || sessions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">No practice sessions recorded yet. Start practicing in the Gym!</td></tr>`;
      return;
    }

    sessions.forEach((s) => {
      const tr = document.createElement("tr");
      const duration = s.total_duration_seconds ? formatDuration(s.total_duration_seconds) : "-";
      const dateStr = new Date(s.started_at).toLocaleString();
      const targetSec = s.total_target_time_seconds || (s.problem ? s.problem.difficulty * 5 * 60 : 1500);
      const targetMin = Math.round(targetSec / 60);

      let outcomeHtml = `<span class="verdict-badge ${s.status}">${s.status.toUpperCase()}</span>`;
      if (s.status === "ac") {
        if (s.is_successful) {
          outcomeHtml = `<span class="verdict-badge ac" title="Solved in under ${targetMin} minutes">🏆 SUCCESS</span>`;
        } else {
          outcomeHtml = `<span class="verdict-badge wa" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24;" title="Solved but took longer than ${targetMin} minutes">⏱️ OVERTIME</span>`;
        }
      } else if (s.status === "active") {
        outcomeHtml = `<span class="verdict-badge ac" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">🟢 IN PROGRESS</span>`;
      } else if (s.status === "stopped") {
        outcomeHtml = `<span class="verdict-badge tle">⏹️ STOPPED</span>`;
      } else if (s.status === "abandoned") {
        outcomeHtml = `<span class="verdict-badge ce">⚠️ ABANDONED</span>`;
      }

      const problems = s.problems && s.problems.length > 0 ? s.problems : [s.problem];
      const probSummary = problems.map((p, i) => `${String.fromCharCode(65 + i)}. ${p.title} (${p.difficulty}/10)`).join(", ");
      const contestName = s.name || `Session #${s.id}`;

      const hasSubmissions = s.submissions && s.submissions.length > 0;
      const subBadge = hasSubmissions
        ? `<button class="btn btn-sm" style="background: rgba(255,255,255,0.08); color: #e2e8f0; font-size: 0.75rem;" onclick="toggleSubmissionDetails(${s.id})">🔍 ${s.submission_count} view</button>`
        : `${s.submission_count}`;

      tr.innerHTML = `
        <td>
          <div style="font-weight: 700; color: #818cf8;">🏆 ${contestName}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">#${s.id}</div>
        </td>
        <td>
          <div style="font-weight: 600; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${probSummary}">${probSummary}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${s.solved_count || (s.status === 'ac' ? s.num_problems : 0)} / ${s.num_problems || problems.length} Solved</div>
        </td>
        <td><span class="tag-pill" style="color: #38bdf8; font-weight: 600;">🎯 ${targetMin} min</span></td>
        <td>${outcomeHtml}</td>
        <td>${duration}</td>
        <td>${subBadge}</td>
        <td>${dateStr}</td>
        <td>
          <div style="display: flex; gap: 0.4rem;">
            <button class="btn btn-primary btn-sm" onclick="window.location.href='/gym?slug=' + encodeURIComponent('${s.problem ? s.problem.slug : ''}')">Replay</button>
            <button class="btn btn-danger btn-sm" onclick="deleteSessionRecord(${s.id})" title="Delete session record">🗑️</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);

      // Expandable submission list row
      if (hasSubmissions) {
        const subRow = document.createElement("tr");
        subRow.id = `session-subs-${s.id}`;
        subRow.style.display = "none";
        subRow.style.backgroundColor = "rgba(0, 0, 0, 0.25)";

        let subsHtml = `
          <td colspan="8" style="padding: 1rem 1.5rem;">
            <div style="font-weight: 600; font-size: 0.85rem; margin-bottom: 0.5rem; color: var(--text-muted);">
              📋 Submissions for Session #${s.id} (${s.submissions.length} total):
            </div>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
        `;

        s.submissions.forEach((sub, idx) => {
          const subTime = new Date(sub.created_at).toLocaleTimeString();
          subsHtml += `
            <div style="display: flex; align-items: center; justify-content: space-between; background: var(--bg-card); padding: 0.5rem 1rem; border-radius: 0.4rem; border: 1px solid var(--border-color); font-size: 0.85rem;">
              <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="color: var(--text-muted);">#${idx + 1}</span>
                <span class="verdict-badge ${sub.verdict.toLowerCase()}">${sub.verdict}</span>
                <span>⏱️ ${sub.exec_time_ms || 0} ms</span>
                <span>💾 ${sub.memory_kb || 0} KB</span>
                <span style="color: var(--text-muted); font-size: 0.75rem;">(${sub.compiler_profile || "g++"})</span>
              </div>
              <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="color: var(--text-muted); font-size: 0.75rem;">${subTime}</span>
                <button class="btn btn-danger btn-sm" style="padding: 0.15rem 0.4rem; font-size: 0.7rem;" onclick="deleteSingleSubmission(${sub.id})" title="Delete this submission">🗑️</button>
              </div>
            </div>
          `;
        });

        subsHtml += `
            </div>
          </td>
        `;
        subRow.innerHTML = subsHtml;
        tbody.appendChild(subRow);
      }
    });
  } catch (err) {
    console.error("Failed to load history:", err);
  }
}

// Toggle display of session submission details
function toggleSubmissionDetails(sessionId) {
  const row = document.getElementById(`session-subs-${sessionId}`);
  if (row) {
    row.style.display = row.style.display === "none" ? "table-row" : "none";
  }
}

// Delete Single Submission
async function deleteSingleSubmission(subId) {
  if (!confirm(`Are you sure you want to delete submission #${subId}?`)) return;
  try {
    const res = await fetch(`/api/submissions/${subId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete submission");
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

