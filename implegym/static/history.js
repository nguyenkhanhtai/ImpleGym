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
      const targetMin = s.problem ? s.problem.difficulty * 5 : 25;

      let outcomeHtml = `<span class="verdict-badge ${s.status}">${s.status.toUpperCase()}</span>`;
      if (s.status === "ac") {
        if (s.is_successful) {
          outcomeHtml = `<span class="verdict-badge ac" title="Solved in under ${targetMin} minutes">🏆 SUCCESS</span>`;
        } else {
          outcomeHtml = `<span class="verdict-badge wa" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24;" title="Solved but took longer than ${targetMin} minutes">⏱️ OVERTIME</span>`;
        }
      } else if (s.status === "stopped") {
        outcomeHtml = `<span class="verdict-badge tle">⏹️ STOPPED</span>`;
      } else if (s.status === "abandoned") {
        outcomeHtml = `<span class="verdict-badge ce">⚠️ ABANDONED</span>`;
      }

      tr.innerHTML = `
        <td>#${s.id}</td>
        <td><b>${s.problem ? s.problem.title : "-"}</b> (${s.problem ? s.problem.difficulty : "-"}/10)</td>
        <td><span class="tag-pill" style="color: #38bdf8; font-weight: 600;">🎯 ${targetMin} min</span></td>
        <td>${outcomeHtml}</td>
        <td>${duration}</td>
        <td>${s.submission_count}</td>
        <td>${dateStr}</td>
        <td>
          <div style="display: flex; gap: 0.4rem;">
            <button class="btn btn-primary btn-sm" onclick="window.location.href='/gym?slug=' + encodeURIComponent('${s.problem ? s.problem.slug : ''}')">Replay</button>
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
