/* Vencertia decision workbench — zero-build vanilla JS frontend.
   Calls the FastAPI /v1/solve endpoint and renders the Chinese 5-section contract. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const form = $("solve-form");
  const problem = $("problem");
  const mode = $("mode");
  const risk = $("risk");
  const options = $("options");
  const solveBtn = $("solve-btn");
  const resultPanel = $("result-panel");
  const errorBox = $("error");
  const summaryBox = $("summary");
  const advancedBox = $("advanced");
  const advancedToggle = $("advanced-toggle");

  let lastFull = null; // cached full result for the advanced toggle

  async function loadHealth() {
    try {
      const r = await fetch("/health");
      const j = await r.json();
      const d = j.data || {};
      $("health").textContent =
        "v" + (d.runtime_version || "?") + " · provider " + (d.model_provider || "?");
    } catch (e) {
      $("health").textContent = "offline";
    }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  }

  function card(title, body, cls) {
    return '<div class="card ' + (cls || "") + '"><h3>' + esc(title) + "</h3>" + body + "</div>";
  }
  function list(items) {
    if (!items || !items.length) return "<p>无</p>";
    return "<ul>" + items.map((i) => "<li>" + esc(i) + "</li>").join("") + "</ul>";
  }

  function renderSummary(s) {
    const html = [];
    // 段1 当前判断
    html.push(
      '<div class="verdict"><span class="pill">' + esc(s.current_judgment_zh || s.current_judgment) +
      '</span><span class="conf">' + esc(s.confidence_phrase || "") + "</span></div>"
    );
    // 段2 为什么
    html.push(card("为什么", "<p>" + esc(s.rationale || "") + "</p>"));
    // 段3 最大未知
    html.push(card("最大未知", "<p>" + esc(s.biggest_unknown || "") + "</p>", "warn"));
    // 段4 下一步
    html.push(card("下一步", "<p>" + esc(s.next_step || "") + "</p>"));
    // 段5 什么会改变判断
    html.push(card("什么会改变判断", list(s.change_condition)));

    // ABSTAIN 四要素
    if (s.why_not_decide) {
      html.push(
        card(
          "为什么暂不决策",
          "<p>" + esc(s.why_not_decide) + "</p>" +
            "<p><b>停止研究条件：</b>" + esc(s.stop_condition || "未设置") + "</p>" +
            "<p><b>最晚决策点：</b>" + esc(s.deadline || "未设置") + "</p>",
          "danger"
        )
      );
    }
    // 模型挑战
    const mc = s.model_critique || {};
    if (mc.available) {
      const tags = (mc.findings_zh || [])
        .map((f) => '<span class="tag">' + esc(f) + "</span>")
        .join("");
      html.push(
        card("模型挑战（整体风险 " + esc(mc.model_risk_zh || "?") + "）", "<p>" + tags + "</p><p>" + esc(mc.note || "") + "</p>")
      );
    } else {
      html.push(card("模型挑战", "<p>" + esc(mc.note || "未触发") + "</p>"));
    }
    // 实验价值
    const ev = s.experiment_voi || {};
    if (ev.experiment && ev.experiment.name) {
      html.push(
        card(
          "实验建议",
          "<p><b>" + esc(ev.experiment.name) + "</b>" + (ev.note ? " · " + esc(ev.note) : "") + "</p>" +
            "<p><b>停止规则：</b>" + esc(ev.stop_rule || "") + "</p>"
        )
      );
    }
    // 个性化
    const per = s.personalization || {};
    if (per.available) {
      html.push(card("个性化依据", "<p>" + esc(per.basis || "") + "（最大可承受损失 " + esc(per.max_financial_downside ?? "—") + "）</p>"));
    }
    summaryBox.innerHTML = html.join("");
  }

  function renderAdvanced(full) {
    const av = full.advanced_view || {};
    const parts = [];
    if (av.belief_graph && av.belief_graph.length) {
      parts.push(
        "<h3>信念依赖图</h3><div class='list'><ul>" +
          av.belief_graph
            .map((e) => "<li>" + esc(e.source_belief_id) + " → " + esc(e.target_belief_id) + "（" + esc(e.relation_zh || e.relation) + "）</li>")
            .join("") +
          "</ul></div>"
      );
    }
    if (av.parameter_provenance && av.parameter_provenance.length) {
      parts.push(
        "<h3>参数来源</h3><div class='list'><ul>" +
          av.parameter_provenance
            .map((p) => "<li>" + esc(p.belief_id) + " = " + esc(p.value) + " · " + esc(p.provenance_zh || p.provenance) + (p.needs_confirmation ? "（待确认）" : "") + "</li>")
            .join("") +
          "</ul></div>"
      );
    }
    if (av.utility) {
      parts.push("<h3>效用</h3><pre>" + esc(JSON.stringify(av.utility, null, 2)) + "</pre>");
    }
    if (av.sensitivity) {
      parts.push("<h3>敏感度</h3><pre>" + esc(JSON.stringify(av.sensitivity, null, 2)) + "</pre>");
    }
    if (!parts.length) parts.push("<p>暂无完整模型数据（未触发 advanced 视图）</p>");
    advancedBox.innerHTML = parts.join("");
  }

  async function onSubmit(e) {
    e.preventDefault();
    errorBox.hidden = true;
    solveBtn.disabled = true;
    solveBtn.textContent = "判断中…";
    const body = { project_id: "ui-" + Date.now(), problem_text: problem.value };
    if (mode.value) body.mode = mode.value;
    const rv = risk.value;
    if (rv) body.risk_aversion = parseFloat(rv);
    if (options.value.trim()) {
      try { body.options = JSON.parse(options.value); }
      catch (err) {
        showError("options 不是合法 JSON：" + err.message);
        solveBtn.disabled = false; solveBtn.textContent = "开始判断";
        return;
      }
    }
    try {
      const r = await fetch("/v1/solve?view=summary", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || j.code !== 0) { showError((j && j.message) || "请求失败"); return; }
      renderSummary(j.data);
      // fetch full for the advanced toggle
      const rf = await fetch("/v1/solve?advanced=true", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const jf = await rf.json();
      lastFull = jf.data || null;
      renderAdvanced(lastFull || {});
      advancedBox.hidden = true;
      advancedToggle.textContent = "展开完整模型";
      resultPanel.hidden = false;
      resultPanel.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      showError("网络错误：" + err.message);
    } finally {
      solveBtn.disabled = false;
      solveBtn.textContent = "开始判断";
    }
  }

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
    resultPanel.hidden = false;
  }

  advancedToggle.addEventListener("click", () => {
    const hidden = advancedBox.hidden;
    advancedBox.hidden = !hidden;
    advancedToggle.textContent = hidden ? "收起完整模型" : "展开完整模型";
  });
  $("reset-btn").addEventListener("click", () => {
    resultPanel.hidden = true; errorBox.hidden = true; lastFull = null;
    problem.focus();
  });
  form.addEventListener("submit", onSubmit);
  loadHealth();
})();
