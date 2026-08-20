/**
 * ImpleGym - AI Problem Forge Logic
 */

let forgedProblemSlug = null;

document.addEventListener("DOMContentLoaded", () => {
  initForge();
});

function initForge() {
  const forgeBtn = document.getElementById("btn-forge-submit");
  const practiceBtn = document.getElementById("btn-practice-forged");

  if (forgeBtn) {
    forgeBtn.addEventListener("click", async () => {
      const topic1 = document.getElementById("forge-topic-1")?.value.trim() || "Heavy-Light Decomposition";
      const topic2 = document.getElementById("forge-topic-2")?.value.trim() || "Dynamic Fenwick Tree";
      const diff = parseInt(document.getElementById("forge-diff")?.value) || 7;
      const extra = document.getElementById("forge-extra")?.value.trim() || "";

      forgeBtn.disabled = true;
      forgeBtn.textContent = "⏳ Synthesizing Problem with AI...";

      const resultContainer = document.getElementById("forge-result-container");
      const previewCard = document.getElementById("forge-preview-card");
      if (resultContainer) resultContainer.style.display = "none";
      if (previewCard) previewCard.style.display = "none";

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

        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || "Problem generation failed");
        }

        const prob = await res.json();
        forgedProblemSlug = prob.slug;

        if (resultContainer) resultContainer.style.display = "block";
        if (previewCard) {
          previewCard.style.display = "block";
          document.getElementById("forged-title").textContent = prob.title;
          document.getElementById("forged-diff").textContent = `Difficulty: ${prob.difficulty}/10`;
          
          const bodyElem = document.getElementById("forged-body");
          if (bodyElem) {
            bodyElem.innerHTML = renderMathMarkdown(prob.statement);
            if (prob.constraints && !prob.statement.toLowerCase().includes("constraints")) {
              bodyElem.innerHTML += `<div class="constraints-box"><h4>Constraints</h4>${renderMathMarkdown(prob.constraints)}</div>`;
            }
            triggerKaTeX(bodyElem);
          }
        }
      } catch (err) {
        alert("Forge error: " + err.message);
      } finally {
        forgeBtn.disabled = false;
        forgeBtn.textContent = "⚡ Synthesize Problem with AI";
      }
    });
  }

  if (practiceBtn) {
    practiceBtn.addEventListener("click", () => {
      if (forgedProblemSlug) {
        window.location.href = `/gym?slug=${encodeURIComponent(forgedProblemSlug)}`;
      }
    });
  }
}
