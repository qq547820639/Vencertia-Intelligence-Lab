/* Vencertia decision-review workbench — zero-build vanilla JS frontend.
   Main surface = calibration dashboard + decision ledger (decision quality),
   with a "start a decision" entry that reuses /v1/solve. v1.9 adds the
   review loop (resolve open predictions), session history and timing. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const form = $("solve-form");
  const problem = $("problem");
  const mode = $("mode");
  const risk = $("risk");
  const solveBtn = $("solve-btn");
  const solveError = $("solve-error");
  const solveResult = $("solve-result");
  const ledgerList = $("ledger-list");
  const openPredWrap = $("open-predictions");
  const openPredList = $("open-pred-list");
  const calibChartWrap = $("calib-chart");
  const calibChartBox = $("calib-chart-box");
  const historySection = $("history-section");
  const historyList = $("history-list");
  const historyClear = $("history-clear");
  const ideaText = $("idea-text");
  const ideaBtn = $("idea-btn");
  const ideaError = $("idea-error");
  const ideaResult = $("idea-result");
  const bpPanel = $("bp-panel");
  const bpTitle = $("bp-title");
  const bpBody = $("bp-body");
  const bpCopy = $("bp-copy");

  const HISTORY_KEY = "vencertia.history.v1";
  const HISTORY_MAX = 10;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  }
  function pct(v) {
    return v == null ? "—" : Math.round(v * 100) + "%";
  }
  function num(v) {
    return v == null ? "—" : String(parseFloat(v.toFixed(3)));
  }
  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    const pad = (x) => String(x).padStart(2, "0");
    return (
      d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
      " " + pad(d.getHours()) + ":" + pad(d.getMinutes())
    );
  }

  // -- health -------------------------------------------------------------
  async function loadHealth() {
    try {
      const r = await fetch("/health");
      const j = await r.json();
      const d = j.data || {};
      const provider = d.model_provider || "?";
      const friendly =
        provider === "mock"
          ? "开发/测试模式（mock）"
          : "AI 服务 " + provider + "（未配置凭据时调用会失败）";
      $("health").textContent = "v" + (d.runtime_version || "?") + " · " + friendly;
    } catch (e) {
      $("health").textContent = "offline";
    }
  }

  // -- summary (5-section contract) ---------------------------------------
  function card(title, body, cls) {
    return '<div class="card ' + (cls || "") + '"><h3>' + esc(title) + "</h3>" + body + "</div>";
  }
  function list(items) {
    if (!items || !items.length) return "<p>无</p>";
    return "<ul>" + items.map((i) => "<li>" + esc(i) + "</li>").join("") + "</ul>";
  }
  function renderSummary(s, meta) {
    if (!s) return;
    const html = [];
    if (meta && meta.elapsed_ms != null) {
      html.push('<div class="timing">判断耗时 ' + meta.elapsed_ms + " ms</div>");
    }
    html.push(
      '<div class="verdict"><span class="pill">' + esc(s.current_judgment_zh || s.current_judgment) +
      '</span><span class="conf">' + esc(s.confidence_phrase || "") + "</span></div>"
    );
    html.push(card("为什么", "<p>" + esc(s.rationale || "") + "</p>"));
    html.push(card("最大未知", "<p>" + esc(s.biggest_unknown || "") + "</p>", "warn"));
    html.push(card("下一步", "<p>" + esc(s.next_step || "") + "</p>"));
    html.push(card("什么会改变判断", list(s.change_condition)));
    if (s.why_not_decide) {
      html.push(
        card(
          "为什么暂不决策",
          "<p>" + esc(s.why_not_decide) + "</p><p><b>停止研究条件：</b>" + esc(s.stop_condition || "未设置") + "</p>",
          "danger"
        )
      );
    }
    html.push(renderFullModel(s));
    solveResult.innerHTML = html.join("");
  }

  // v1.9: progressive disclosure — the engine has already computed the
  // belief graph / parameter provenance / VOI / critique; render them with
  // Chinese labels instead of raw JSON (UX diagnosis items #3/#4/#7).
  function renderFullModel(s) {
    const blocks = [];

    const deps = (s.belief_dependencies || []).map(
      (d) =>
        "<li>belief " + esc(d.source_belief_id) + " → " + esc(d.target_belief_id) +
        "（" + esc(d.relation_zh || d.relation || "关系未知") + "）</li>"
    );
    if (deps.length) blocks.push(card("信念依赖关系", "<ul>" + deps.join("") + "</ul>"));

    const prov = (s.provenance_summary || [])
      .filter((p) => p.needs_confirmation)
      .map(
        (p) =>
          "<li>方案 " + esc(p.option_id) + " 的 belief " + esc(p.belief_id) +
          "：系数 " + num(p.value) + "（" + esc(p.provenance_zh || p.provenance) + "）</li>"
      );
    if (prov.length) {
      blocks.push(card("待确认的模型参数", "<ul>" + prov.join("") + "</ul>", "warn"));
    } else {
      blocks.push(
        card("模型参数来源", "<p>全部参数均有明确来源，无需你确认。</p>")
      );
    }

    const voi = s.experiment_voi || {};
    if (voi.experiment && voi.experiment.name) {
      const cond = voi.decision_change_condition || {};
      blocks.push(
        card(
          "实验的决策价值",
          "<p><b>" + esc(voi.experiment.name) + "</b>" + (voi.note ? "（" + esc(voi.note) + "）" : "") + "</p>" +
          "<ul>" +
          "<li>成功判据：" + esc(cond.success || "—") + "</li>" +
          "<li>失败判据：" + esc(cond.failure || "—") + "</li>" +
          "<li>模糊判据：" + esc(cond.ambiguity || "—") + "</li>" +
          "</ul>" +
          "<p class='hint'>" + esc(voi.stop_rule || "") + "</p>"
        )
      );
    }

    const pers = s.personalization || {};
    if (pers.available) {
      blocks.push(
        card(
          "个性化依据",
          "<p>" + esc(pers.basis || "") + "</p><p class='hint'>风险档位：" +
          esc(pers.stakes_class_zh || pers.stakes_class || "—") + "</p>"
        )
      );
    }

    const crit = s.model_critique || {};
    if (crit.available) {
      blocks.push(
        card(
          "模型自检",
          "<p>" + esc(crit.note || "") + "</p>" +
          list(crit.findings_zh && crit.findings_zh.length ? crit.findings_zh : ["暂未识别到结构性风险"])
        )
      );
    }

    if (!blocks.length) return "";
    return (
      '<details class="model-details"><summary>展开完整模型</summary>' +
      '<div class="model-body">' + blocks.join("") + "</div></details>"
    );
  }
  function renderExamplePlaceholder() {
    solveResult.innerHTML =
      '<div class="example-note">' +
      "<h3>示例输出</h3>" +
      "<p>发起一个决策后，这里会显示 5 段判断合同：当前判断 · 为什么 · 最大未知 · 下一步 · 什么会改变判断。证据不足时会诚实给出「暂不决策」并附上最小验证实验。</p>" +
      "</div>";
  }

  // -- session history (localStorage) --------------------------------------
  function loadHistory() {
    try {
      return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    } catch (e) {
      return [];
    }
  }
  function saveHistoryItem(item) {
    const items = loadHistory();
    items.unshift(item);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, HISTORY_MAX)));
    renderHistory();
  }
  function renderHistory() {
    const items = loadHistory();
    historySection.hidden = items.length === 0;
    if (!items.length) return;
    historyList.innerHTML = items
      .map((item, i) => {
        const title = esc(item.problem || "（无标题）");
        const time = fmtDate(item.saved_at);
        return (
          '<button type="button" class="history-item" data-i="' + i + '">' +
          '<span class="hi-title">' + title + "</span>" +
          '<span class="hi-meta">' + time + " · " + esc(item.verdict || "") + "</span>" +
          "</button>"
        );
      })
      .join("");
    historyList.querySelectorAll(".history-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = loadHistory()[Number(btn.dataset.i)];
        if (item && item.summary) {
          renderSummary(item.summary, null);
          problem.value = item.problem || "";
        }
      });
    });
  }
  historyClear.addEventListener("click", () => {
    localStorage.removeItem(HISTORY_KEY);
    renderHistory();
  });

  // -- ledger + calibration dashboard --------------------------------------
  const STATUS_CLS = { RECOMMENDED: "st-rec", ACTED: "st-act", SETTLED: "st-set" };
  let ledgerCache = [];
  const RESULT_OPTIONS = [
    ["", "仅标记行动"],
    ["SUCCESS", "成功"],
    ["FAILURE", "失败"],
    ["PARTIAL", "部分成功"],
  ];
  function renderLedger(ledger) {
    ledgerCache = ledger || [];
    if (!ledger || !ledger.length) {
      ledgerList.innerHTML =
        '<div class="empty">还没有决策记录。发起一个决策，它会带着「推荐 → 行动 → 结果」进入台账。</div>';
      return;
    }
    ledgerList.innerHTML = ledger
      .map((r) => {
        const outs = (r.outcomes || [])
          .map(
            (o) =>
              '<span class="tag">复盘 ' + esc(o.counterfactual_status_zh || o.counterfactual_status) + "</span>"
          )
          .join("");
        const abstain = r.abstain_reason
          ? '<div class="lr-abstain">' + esc(r.abstain_reason) + "</div>"
          : "";
        const actions =
          '<div class="lr-actions" data-row="' + esc(r.decision_record_id) + '">' +
          (r.status === "RECOMMENDED"
            ? '<button type="button" class="btn-small act-btn" data-mode="act">标记行动</button>'
            : r.status === "ACTED"
              ? '<button type="button" class="btn-small act-btn" data-mode="settle">记录结果</button>'
              : "") +
          '<button type="button" class="btn-small bp-btn" data-did="' + esc(r.decision_id) + '">生成 BP</button>' +
          "</div>";
        return (
          '<div class="ledger-row">' +
          '<div class="lr-main">' +
          '<div class="lr-title">' + esc(r.decision_question || r.recommendation || "（未命名决策）") + "</div>" +
          '<div class="lr-sub">' + esc(r.decision_id || "") + " · " + esc(fmtDate(r.updated_at)) + "</div>" +
          "</div>" +
          '<div class="lr-right">' +
          '<span class="pill ' + (STATUS_CLS[r.status] || "") + '">' + esc(r.status_zh || r.status) + "</span>" +
          outs + abstain +
          "</div>" +
          actions +
          "</div>"
        );
      })
      .join("");
    ledgerList.querySelectorAll(".act-btn").forEach((btn) => {
      btn.addEventListener("click", () =>
        showActForm(btn.closest(".lr-actions"), btn.dataset.mode)
      );
    });
    ledgerList.querySelectorAll(".bp-btn").forEach((btn) => {
      btn.addEventListener("click", () => generateBp(btn.dataset.did));
    });
  }

  function showActForm(container, mode) {
    if (!container) return;
    const row = ledgerCache.find((r) => r.decision_record_id === container.dataset.row);
    if (!row) return;
    const actionValue = row.action_taken || "";
    const form = document.createElement("div");
    form.className = "act-form";
    form.innerHTML =
      (mode === "act"
        ? '<input type="text" class="act-input" placeholder="你实际做了什么？（一句话）" value="" />'
        : '<input type="text" class="act-input" disabled value="' + esc(actionValue) + '" />') +
      '<select class="act-result">' +
      RESULT_OPTIONS.map(
        (o) =>
          '<option value="' + o[0] + '"' + (o[0] === "" ? " selected" : "") + ">" + o[1] + "</option>"
      ).join("") +
      "</select>" +
      '<div class="act-btns">' +
      '<button type="button" class="btn-small act-confirm">确认</button>' +
      '<button type="button" class="btn-small btn-false act-cancel">取消</button>' +
      "</div>";
    container.replaceWith(form);
    form.querySelector(".act-cancel").addEventListener("click", () => loadReview());
    form.querySelector(".act-confirm").addEventListener("click", () => {
      const input = form.querySelector(".act-input");
      const sel = form.querySelector(".act-result");
      submitAct(row.decision_id, mode === "act" ? input.value.trim() : (row.action_taken || ""), sel.value);
    });
    if (mode === "act") form.querySelector(".act-input").focus();
  }

  async function submitAct(decisionId, actionTaken, outcomeType) {
    if (!actionTaken) {
      solveError.textContent = "请先填写行动内容";
      solveError.hidden = false;
      return;
    }
    const body = { action_taken: actionTaken };
    if (outcomeType) {
      body.outcome_type = outcomeType;
      body.result = "已按「" + outcomeType + "」复盘（Web 工作台记录）";
    }
    try {
      const r = await fetch("/v1/decisions/" + encodeURIComponent(decisionId) + "/act", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || j.code !== 0) {
        solveError.textContent = (j && j.message) || "标记行动失败";
        solveError.hidden = false;
        return;
      }
      solveError.hidden = true;
      loadReview();
    } catch (err) {
      solveError.textContent = "网络错误：" + err.message;
      solveError.hidden = false;
    }
  }
  function renderOpenPredictions(preds) {
    openPredWrap.hidden = !preds || preds.length === 0;
    if (!preds || !preds.length) {
      openPredList.innerHTML = "";
      return;
    }
    openPredList.innerHTML = preds
      .map(
        (p) =>
          '<div class="pred-row">' +
          '<div class="pred-main">' +
          '<div class="pred-target">' + esc(p.target || p.id) + "</div>" +
          '<div class="pred-meta">' + pct(p.predicted_probability) + " · 到期 " + esc(fmtDate(p.due_at) || "未设") + "</div>" +
          "</div>" +
          '<div class="pred-actions">' +
          '<button type="button" class="btn-small btn-true" data-id="' + esc(p.id) + '" data-outcome="true">成真</button>' +
          '<button type="button" class="btn-small btn-false" data-id="' + esc(p.id) + '" data-outcome="false">落空</button>' +
          "</div>" +
          "</div>"
      )
      .join("");
    openPredList.querySelectorAll(".pred-actions button").forEach((btn) => {
      btn.addEventListener("click", () => resolvePrediction(btn.dataset.id, btn.dataset.outcome === "true"));
    });
  }
  // v1.9.1: zero-dependency reliability diagram — predicted-confidence buckets
  // vs empirical hit rate, with the perfect-calibration diagonal.
  function renderCalibChart(buckets) {
    const usable = (buckets || []).filter(
      (b) => b && b.mean_confidence != null && b.lo != null && b.hi != null
    );
    calibChartWrap.hidden = usable.length === 0;
    if (!usable.length) {
      calibChartBox.innerHTML = "";
      return;
    }
    const W = 320;
    const H = 190;
    const left = 26;
    const right = 312;
    const top = 14;
    const bottom = 170;
    const px = (v) => left + (right - left) * Math.max(0, Math.min(1, Number(v)));
    const py = (v) => bottom - (bottom - top) * Math.max(0, Math.min(1, Number(v) || 0));
    const parts = [];
    parts.push(
      '<rect x="' + left + '" y="' + top + '" width="' + (right - left) + '" height="' + (bottom - top) +
      '" fill="var(--bg)" stroke="var(--line)"/>'
    );
    parts.push(
      '<line x1="' + left + '" y1="' + bottom + '" x2="' + right + '" y2="' + top +
      '" stroke="var(--ink-3)" stroke-dasharray="4 3" stroke-width="1.5"/>'
    );
    [0, 0.5, 1].forEach((t) => {
      const x = px(t);
      parts.push(
        '<text x="' + x + '" y="' + (bottom + 12) + '" font-size="9" fill="var(--ink-3)" text-anchor="middle">' +
        Math.round(t * 100) + "%</text>"
      );
    });
    usable.forEach((b) => {
      const x = px(b.lo);
      const w = Math.max(2, px(b.hi) - px(b.lo) - 2);
      const h = Math.max(0, bottom - py(b.empirical_rate));
      const y = bottom - h;
      const rate = b.empirical_rate == null ? "无样本" : Math.round(b.empirical_rate * 100) + "%";
      parts.push(
        '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + w.toFixed(1) +
        '" height="' + h.toFixed(1) + '" fill="var(--accent)" opacity="0.75">' +
        '<title>置信度 ' + Math.round(b.lo * 100) + "–" + Math.round(b.hi * 100) +
        "%：实际命中 " + rate + "</title></rect>"
      );
    });
    calibChartBox.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="校准曲线" style="width:100%;height:auto">' +
      parts.join("") + "</svg>";
  }

  async function resolvePrediction(id, outcome) {
    try {
      const r = await fetch("/v1/predictions/" + encodeURIComponent(id) + "/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome: outcome }),
      });
      const j = await r.json();
      if (!r.ok || j.code !== 0) {
        solveError.textContent = (j && j.message) || "复盘失败";
        solveError.hidden = false;
        return;
      }
      loadReview();
    } catch (err) {
      solveError.textContent = "网络错误：" + err.message;
      solveError.hidden = false;
    }
  }
  async function loadReview() {
    try {
      const r = await fetch("/v1/review");
      const j = await r.json();
      if (!r.ok || j.code !== 0) {
        ledgerList.innerHTML = '<div class="empty">复盘数据暂不可用。</div>';
        return;
      }
      const d = j.data || {};
      const cal = d.calibration || {};
      const fc = cal.forecast_calibration || {};
      $("stat-open").textContent = (d.open_predictions || []).length;
      $("stat-n").textContent = cal.n != null ? cal.n : "0";
      $("stat-hit").textContent = pct(fc.empirical_rate);
      $("stat-ece").textContent = num(fc.ece);
      $("stat-brier").textContent = num(fc.brier_score);
      $("calib-verdict").textContent = cal.verdict || "";
      renderCalibChart(cal.buckets || []);
      renderLedger(d.ledger || []);
      renderOpenPredictions(d.open_predictions || []);
    } catch (e) {
      ledgerList.innerHTML = '<div class="empty">复盘数据暂不可用。</div>';
    }
  }

  // -- submit --------------------------------------------------------------
  async function onSubmit(e) {
    e.preventDefault();
    solveError.hidden = true;
    const body = { project_id: "ui-" + Date.now(), problem_text: problem.value };
    if (mode.value) body.mode = mode.value;
    const rv = risk.value;
    if (rv) body.risk_aversion = parseFloat(rv);

    solveBtn.disabled = true;
    solveBtn.textContent = "判断中…";
    const started = performance.now();
    try {
      const r = await fetch("/v1/solve?view=summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const elapsed = Math.round(performance.now() - started);
      const j = await r.json();
      if (!r.ok || j.code !== 0) {
        solveError.textContent = (j && j.message) || "请求失败";
        solveError.hidden = false;
        return;
      }
      renderSummary(j.data, { elapsed_ms: elapsed });
      saveHistoryItem({
        problem: problem.value,
        verdict: (j.data || {}).current_judgment_zh || "",
        saved_at: new Date().toISOString(),
        summary: j.data,
      });
      loadReview();
    } catch (err) {
      solveError.textContent = "网络错误：" + err.message;
      solveError.hidden = false;
    } finally {
      solveBtn.disabled = false;
      solveBtn.textContent = "开始判断";
    }
  }

  // -- v2.0: idea intake (想法评估) ------------------------------------------
  let lastIdeaAssessment = null;
  async function assessIdea() {
    ideaError.hidden = true;
    const text = ideaText.value.trim();
    if (!text) {
      ideaError.textContent = "请先写下想法";
      ideaError.hidden = false;
      return;
    }
    ideaBtn.disabled = true;
    ideaBtn.textContent = "评估中…";
    try {
      const r = await fetch("/v1/ideas/assess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idea_text: text }),
      });
      const j = await r.json();
      if (!r.ok || j.code !== 0) {
        ideaError.textContent = (j && j.message) || "评估失败";
        ideaError.hidden = false;
        return;
      }
      lastIdeaAssessment = j.data;
      renderIdea(j.data);
    } catch (err) {
      ideaError.textContent = "网络错误：" + err.message;
      ideaError.hidden = false;
    } finally {
      ideaBtn.disabled = false;
      ideaBtn.textContent = "评估想法";
    }
  }
  function renderIdea(d) {
    const html = [];
    html.push(
      '<div class="card"><h3>决策问题</h3><p>' + esc(d.decision_question) +
      '（建议模式：' + esc(d.recommended_mode_zh || d.recommended_mode) + "）</p></div>"
    );
    const assumptions = (d.assumptions || []).map(
      (a) =>
        "<li>" + esc(a.statement) + " <span class='hint'>先验 " + esc(a.prior_phrase) +
        " · 不确定性 " + esc(a.uncertainty_phrase) + "</span></li>"
    );
    html.push(
      card("假设清单（模型提议，待确认）", assumptions.length ? "<ul>" + assumptions.join("") + "</ul>" : "<p>无</p>")
    );
    const unknowns = (d.biggest_unknowns || []).map(
      (u) =>
        "<li>" + esc(u.statement) + " <span class='hint'>不确定性 " + esc(u.uncertainty_phrase) + "</span></li>"
    );
    html.push(card("最大未知", unknowns.length ? "<ul>" + unknowns.join("") + "</ul>" : "<p>无</p>", "warn"));
    html.push('<button type="button" class="idea-to-solve">转入决策判断 →</button>');
    html.push('<p class="hint">' + esc(d.disclaimer || "") + "</p>");
    ideaResult.innerHTML = html.join("");
    ideaResult.querySelector(".idea-to-solve").addEventListener("click", ideaToSolve);
  }
  async function ideaToSolve() {
    if (!lastIdeaAssessment || !lastIdeaAssessment.solve_request) return;
    solveError.hidden = true;
    solveBtn.disabled = true;
    solveBtn.textContent = "判断中…";
    const started = performance.now();
    try {
      const r = await fetch("/v1/solve?view=summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastIdeaAssessment.solve_request),
      });
      const elapsed = Math.round(performance.now() - started);
      const j = await r.json();
      if (!r.ok || j.code !== 0) {
        solveError.textContent = (j && j.message) || "请求失败";
        solveError.hidden = false;
        return;
      }
      problem.value = lastIdeaAssessment.decision_question || "";
      mode.value = "EXPLORE";
      renderSummary(j.data, { elapsed_ms: elapsed });
      saveHistoryItem({
        problem: problem.value,
        verdict: (j.data || {}).current_judgment_zh || "",
        saved_at: new Date().toISOString(),
        summary: j.data,
      });
      loadReview();
    } catch (err) {
      solveError.textContent = "网络错误：" + err.message;
      solveError.hidden = false;
    } finally {
      solveBtn.disabled = false;
      solveBtn.textContent = "开始判断";
    }
  }

  // -- v2.0: business plan (决策 → BP) ----------------------------------------
  let bpMarkdownCache = "";
  async function generateBp(decisionId) {
    bpPanel.hidden = false;
    bpBody.innerHTML = '<div class="empty">生成中…（确定性骨架 + V11 skill 叙事）</div>';
    try {
      const r = await fetch("/v1/bp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision_id: decisionId }),
      });
      const j = await r.json();
      if (!r.ok || j.code !== 0) {
        bpBody.innerHTML = '<div class="empty">' + esc((j && j.message) || "生成失败") + "</div>";
        return;
      }
      bpMarkdownCache = j.data.markdown || "";
      renderBp(j.data.view, j.data.narratives || [], j.data.skill_traces || []);
      bpPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (err) {
      bpBody.innerHTML = '<div class="empty">网络错误：' + esc(err.message) + "</div>";
    }
  }
  function renderBp(view, narratives, traces) {
    const html = [];
    html.push(
      '<div class="verdict"><span class="pill">' + esc(view.company_name) + "</span>" +
      '<span class="conf">' + esc(view.tagline || "") + "</span></div>"
    );
    (view.sections || []).forEach((s) => {
      const lines = (s.lines || []).map((l) => "<p>" + esc(l) + "</p>").join("");
      const bullets = (s.bullets || []).map((b) => "<li>" + esc(b) + "</li>").join("");
      html.push(
        '<div class="card' + (s.na ? " warn" : "") + '"><h3>' + esc(s.title_zh) +
        (s.na ? "（数据不足）" : "") + "</h3>" + lines +
        (bullets ? "<ul>" + bullets + "</ul>" : "") + "</div>"
      );
    });
    if (narratives && narratives.length) {
      const narrItems = narratives
        .map(
          (n) =>
            "<li>" + esc(n.skill) + "（" + esc(n.contract) + "，" +
            (n.deterministic ? "确定性模板" : "真实模型") + "）</li>"
        )
        .join("");
      html.push(card("V11 skill 叙事（候选，已过校验）", "<ul>" + narrItems + "</ul>"));
    }
    if (traces && traces.some((t) => t.status === "REJECTED")) {
      html.push(
        card(
          "被校验门拒绝的 skill",
          "<ul>" +
            traces
              .filter((t) => t.status === "REJECTED")
              .map((t) => "<li>" + esc(t.skill) + "：" + esc(t.note || t.status) + "</li>")
              .join("") +
            "</ul>",
          "danger"
        )
      );
    }
    const notes = (view.honest_notes || []).map((n) => "<li>" + esc(n) + "</li>").join("");
    if (notes) html.push(card("诚实声明", "<ul>" + notes + "</ul>"));
    bpBody.innerHTML = html.join("");
  }
  bpCopy.addEventListener("click", async () => {
    if (!bpMarkdownCache) return;
    try {
      await navigator.clipboard.writeText(bpMarkdownCache);
      bpCopy.textContent = "已复制 ✓";
      setTimeout(() => (bpCopy.textContent = "复制全文"), 1600);
    } catch (e) {
      window.prompt("复制失败，请手动复制：", bpMarkdownCache);
    }
  });
  ideaBtn.addEventListener("click", assessIdea);

  form.addEventListener("submit", onSubmit);
  renderExamplePlaceholder();
  renderHistory();
  loadHealth();
  loadReview();
})();
