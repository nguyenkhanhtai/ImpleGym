/**
 * ImpleGym - Problem Explorer Logic
 */

let currentProblemPage = 1;
let currentProblemPageSize = 20;
let totalProblemsCount = 0;
let totalProblemPages = 1;

document.addEventListener("DOMContentLoaded", () => {
  initCategories();
  initExplorerFilters();
  loadProblems(1);
});

// Load Categories
async function initCategories() {
  try {
    const res = await fetch("/api/categories");
    const categories = await res.json();
    const select = document.getElementById("category-select");
    if (!select) return;
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

// Initialize Filters & Listeners
function initExplorerFilters() {
  const searchInput = document.getElementById("search-input");
  const categorySelect = document.getElementById("category-select");
  const diffSlider = document.getElementById("difficulty-slider");
  const diffLabel = document.getElementById("difficulty-label");
  const statusSelect = document.getElementById("status-select");
  const pageSizeSelect = document.getElementById("page-size-select");
  const syncBtn = document.getElementById("btn-sync-yosupo");

  if (diffSlider && diffLabel) {
    diffSlider.addEventListener("input", (e) => {
      diffLabel.textContent = e.target.value;
      loadProblems(1);
    });
  }

  if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => loadProblems(1), 300);
    });
  }

  if (categorySelect) {
    categorySelect.addEventListener("change", () => loadProblems(1));
  }

  if (statusSelect) {
    statusSelect.addEventListener("change", () => loadProblems(1));
  }

  if (pageSizeSelect) {
    pageSizeSelect.addEventListener("change", () => {
      currentProblemPageSize = parseInt(pageSizeSelect.value) || 20;
      loadProblems(1);
    });
  }

  // Pagination navigation buttons
  const firstBtn = document.getElementById("btn-page-first");
  const prevBtn = document.getElementById("btn-page-prev");
  const nextBtn = document.getElementById("btn-page-next");
  const lastBtn = document.getElementById("btn-page-last");

  if (firstBtn) firstBtn.onclick = () => loadProblems(1);
  if (prevBtn) prevBtn.onclick = () => loadProblems(Math.max(1, currentProblemPage - 1));
  if (nextBtn) nextBtn.onclick = () => loadProblems(Math.min(totalProblemPages, currentProblemPage + 1));
  if (lastBtn) lastBtn.onclick = () => loadProblems(totalProblemPages);

  // Sync Yosupo Repo Button
  if (syncBtn) {
    syncBtn.addEventListener("click", async () => {
      syncBtn.disabled = true;
      syncBtn.textContent = "⏳ Syncing Yosupo Repo...";

      try {
        const res = await fetch("/api/problems/sync", { method: "POST" });
        if (!res.ok) throw new Error("Sync failed");
        const data = await res.json();
        alert(`Successfully synced ${data.count} problems from official Yosupo repository!`);
        loadProblems(1);
        initCategories();
      } catch (err) {
        alert("Sync error: " + err.message);
      } finally {
        syncBtn.disabled = false;
        syncBtn.textContent = "🔄 Sync Official Yosupo Repo";
      }
    });
  }
}

const problemListCache = new Map();

// Load Problem Explorer Table with Pagination and ETag 304 Caching
async function loadProblems(page = 1) {
  currentProblemPage = page;
  const search = document.getElementById("search-input")?.value || "";
  const category = document.getElementById("category-select")?.value || "";
  const maxDiff = document.getElementById("difficulty-slider")?.value || 10;
  const status = document.getElementById("status-select")?.value || "all";
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

  const cacheKey = url.toString();
  let cached = problemListCache.get(cacheKey);
  if (!cached) {
    try {
      const stored = sessionStorage.getItem(`cache_${cacheKey}`);
      if (stored) cached = JSON.parse(stored);
    } catch (e) {}
  }

  // Instant render from cache on page return
  if (cached && cached.data) {
    totalProblemsCount = cached.data.total;
    totalProblemPages = cached.data.total_pages;
    renderProblemTable(cached.data.items);
    renderPaginationControls(cached.data);
  }

  const headers = {};
  if (cached && cached.etag) {
    headers["If-None-Match"] = cached.etag;
  }

  try {
    const res = await fetch(url, { headers });
    if (res.status === 304) {
      // 304 Not Modified - cached data is completely fresh and already rendered!
      return;
    }

    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    const etag = res.headers.get("ETag");

    const cacheEntry = { etag, data };
    problemListCache.set(cacheKey, cacheEntry);
    try {
      sessionStorage.setItem(`cache_${cacheKey}`, JSON.stringify(cacheEntry));
    } catch (e) {}

    totalProblemsCount = data.total;
    totalProblemPages = data.total_pages;
    renderProblemTable(data.items);
    renderPaginationControls(data);
  } catch (err) {
    console.error("Failed to fetch problems:", err);
  }
}

function renderProblemTable(problems) {
  const tbody = document.getElementById("problem-table-body");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!problems || problems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">No problems found matching criteria.</td></tr>`;
    return;
  }

  problems.forEach((p) => {
    const tr = document.createElement("tr");
    tr.className = "clickable-problem-row";
    tr.title = `Click to view ${p.title}`;
    tr.onclick = (e) => {
      // Ignore click if clicking directly inside difficulty dropdown
      if (e.target.closest(".diff-select") || e.target.tagName === "SELECT" || e.target.tagName === "OPTION") {
        return;
      }
      window.location.href = `/gym?slug=${encodeURIComponent(p.slug)}`;
    };

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
        <select class="diff-select ${diffClass}" onchange="changeProblemDifficulty('${p.slug}', this.value)" title="Click to manually update difficulty" onclick="event.stopPropagation()">
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
        <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); window.location.href='/gym?slug=' + encodeURIComponent('${p.slug}')">🎯 View & Practice</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
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

  if (firstBtn) firstBtn.disabled = data.page <= 1;
  if (prevBtn) prevBtn.disabled = data.page <= 1;
  if (nextBtn) nextBtn.disabled = data.page >= data.total_pages || data.total_pages === 0;
  if (lastBtn) lastBtn.disabled = data.page >= data.total_pages || data.total_pages === 0;

  numbersElem.innerHTML = "";
  const totalP = Math.max(1, data.total_pages);
  const curP = data.page;

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
    problemListCache.clear();
    sessionStorage.clear();
    loadProblems(currentProblemPage);
  } catch (err) {
    alert("Error updating difficulty: " + err.message);
    loadProblems(currentProblemPage);
  }
}
