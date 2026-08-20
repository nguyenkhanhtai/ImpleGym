/**
 * ImpleGym - Common Shared Utilities & Modals
 */

// Math Protection & Clean KaTeX Markdown Renderer
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

  // Convert math code blocks (e.g. in Input/Output format: ~~~ or ``` containing $) to math-format-box
  text = text.replace(/~~~([\s\S]*?)~~~/g, (match, inner) => {
    if (inner.includes("$") || inner.includes("\\")) {
      return `\n\n<div class="math-format-box">\n\n${inner.trim()}\n\n</div>\n\n`;
    }
    return `\n\`\`\`\n${inner.trim()}\n\`\`\`\n`;
  });

  text = text.replace(/```([\s\S]*?)```/g, (match, inner) => {
    if (inner.includes("$") || inner.includes("\\dots") || inner.includes("\\le")) {
      return `\n\n<div class="math-format-box">\n\n${inner.trim()}\n\n</div>\n\n`;
    }
    return match;
  });

  // 4. Protect Math expressions from Marked's parser
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

// Trigger KaTeX rendering on DOM elements
function triggerKaTeX(element) {
  if (window.renderMathInElement && element) {
    window.renderMathInElement(element, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      ignoredTags: ["script", "noscript", "style", "textarea"],
      throwOnError: false,
    });
  }
}

// Format duration in seconds to HH:MM:SS.s
function formatDuration(sec) {
  if (sec === null || sec === undefined || isNaN(sec)) return "00:00:00.0";
  const totalMs = Math.floor(sec * 1000);
  const ms = Math.floor((totalMs % 1000) / 100);
  const totalSeconds = Math.floor(totalMs / 1000);
  const s = totalSeconds % 60;
  const m = Math.floor(totalSeconds / 60) % 60;
  const h = Math.floor(totalSeconds / 3600);

  const hh = String(h).padStart(2, "0");
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");

  return `${hh}:${mm}:${ss}.${ms}`;
}

// Parse ISO date string safely
function parseUtcDate(dateStr) {
  if (!dateStr) return Date.now();
  if (typeof dateStr === "string" && !dateStr.endsWith("Z") && !dateStr.includes("+")) {
    return new Date(dateStr + "Z").getTime();
  }
  return new Date(dateStr).getTime();
}

// Initialize Global Modals (Gaussian Sampler & AI Settings)
function initCommonModals() {
  // Gaussian Sampler Modal
  const samplerModal = document.getElementById("sampler-modal");
  const openSamplerBtn = document.getElementById("btn-quick-sample");
  const closeSamplerBtn = document.getElementById("btn-close-sampler-modal");
  const rollSampleBtn = document.getElementById("btn-roll-sample");
  const meanSlider = document.getElementById("sampler-mean");
  const stdSlider = document.getElementById("sampler-std");
  const meanVal = document.getElementById("sampler-mean-val");
  const stdVal = document.getElementById("sampler-std-val");

  if (openSamplerBtn && samplerModal) {
    openSamplerBtn.addEventListener("click", () => {
      samplerModal.style.display = "flex";
    });
  }

  if (closeSamplerBtn && samplerModal) {
    closeSamplerBtn.addEventListener("click", () => {
      samplerModal.style.display = "none";
    });
  }

  if (meanSlider && meanVal) {
    meanSlider.addEventListener("input", (e) => {
      meanVal.textContent = e.target.value;
    });
  }

  if (stdSlider && stdVal) {
    stdSlider.addEventListener("input", (e) => {
      stdVal.textContent = e.target.value;
    });
  }

  if (rollSampleBtn) {
    rollSampleBtn.addEventListener("click", async () => {
      const mean = parseFloat(meanSlider.value);
      const std = parseFloat(stdSlider.value);
      const skew = document.querySelector('input[name="sampler-skew"]:checked')?.value || "balanced";
      const excludeSolved = document.getElementById("sampler-exclude-solved")?.checked || false;

      try {
        const res = await fetch("/api/sampler/sample", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mean_difficulty: mean,
            std_dev: std,
            skewness: skew,
            exclude_solved: excludeSolved,
          }),
        });

        if (!res.ok) throw new Error("Failed to sample problem");
        const prob = await res.json();
        samplerModal.style.display = "none";
        // Redirect directly to gym page with problem slug
        window.location.href = `/gym?slug=${encodeURIComponent(prob.slug)}`;
      } catch (err) {
        alert("Sampling error: " + err.message);
      }
    });
  }

  // AI Configuration Modal
  const aiModal = document.getElementById("ai-config-modal");
  const openAiBtn = document.getElementById("btn-open-ai-config");
  const closeAiBtn = document.getElementById("btn-close-ai-modal");
  const saveAiBtn = document.getElementById("btn-save-ai-config");
  const providerSelect = document.getElementById("ai-provider-select");
  const modelInput = document.getElementById("ai-model-input");
  const keyInput = document.getElementById("ai-key-input");
  const baseInput = document.getElementById("ai-base-input");
  const tempSlider = document.getElementById("ai-temp-slider");
  const tempVal = document.getElementById("ai-temp-val");
  const tokensInput = document.getElementById("ai-tokens-input");
  const maskedKeySpan = document.getElementById("current-masked-key");

  if (openAiBtn && aiModal) {
    openAiBtn.addEventListener("click", async () => {
      aiModal.style.display = "flex";
      try {
        const res = await fetch("/api/ai/config");
        if (res.ok) {
          const cfg = await res.json();
          if (providerSelect) providerSelect.value = cfg.provider;
          if (modelInput) modelInput.value = cfg.model;
          if (baseInput) baseInput.value = cfg.api_base || "";
          if (tempSlider) {
            tempSlider.value = cfg.temperature;
            if (tempVal) tempVal.textContent = cfg.temperature;
          }
          if (tokensInput && cfg.max_tokens) tokensInput.value = cfg.max_tokens;
          if (maskedKeySpan) maskedKeySpan.textContent = cfg.api_key_masked || "Not Set";
          if (providerSelect) updateModelSuggestions(providerSelect.value);
        }
      } catch (err) {
        console.error("Failed to load AI config:", err);
      }
    });
  }

  if (closeAiBtn && aiModal) {
    closeAiBtn.addEventListener("click", () => {
      aiModal.style.display = "none";
    });
  }

  if (tempSlider && tempVal) {
    tempSlider.addEventListener("input", (e) => {
      tempVal.textContent = e.target.value;
    });
  }

  if (providerSelect) {
    providerSelect.addEventListener("change", (e) => {
      updateModelSuggestions(e.target.value);
    });
  }

  async function updateModelSuggestions(provider) {
    const datalist = document.getElementById("ai-models-datalist");
    if (!datalist) return;
    datalist.innerHTML = "";
    try {
      const res = await fetch(`/api/ai/models?provider=${encodeURIComponent(provider)}`);
      if (res.ok) {
        const data = await res.json();
        if (data.models && Array.isArray(data.models)) {
          data.models.forEach((m) => {
            const opt = document.createElement("option");
            opt.value = m;
            datalist.appendChild(opt);
          });
        }
      }
    } catch (err) {
      console.warn("Failed to fetch model suggestions:", err);
    }
  }

  if (saveAiBtn && aiModal) {
    saveAiBtn.addEventListener("click", async () => {
      const payload = {
        provider: providerSelect ? providerSelect.value : "openai",
        model: modelInput ? modelInput.value.trim() : "gpt-4o",
        temperature: tempSlider ? parseFloat(tempSlider.value) : 0.3,
        max_tokens: tokensInput ? parseInt(tokensInput.value) : 4096,
      };

      if (keyInput && keyInput.value.trim()) {
        payload.api_key = keyInput.value.trim();
      }
      if (baseInput) {
        payload.api_base = baseInput.value.trim() || null;
      }

      saveAiBtn.disabled = true;
      saveAiBtn.textContent = "Saving...";

      try {
        const res = await fetch("/api/ai/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || "Failed to update AI configuration");
        }

        const data = await res.json();
        alert(data.message || "AI Settings updated successfully!");
        aiModal.style.display = "none";
        if (keyInput) keyInput.value = "";
      } catch (err) {
        alert("Error saving AI settings: " + err.message);
      } finally {
        saveAiBtn.disabled = false;
        saveAiBtn.textContent = "💾 Save AI Settings";
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initCommonModals();
});
