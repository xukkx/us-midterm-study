(function () {
  "use strict";
  const data = window.LH169_DATA;
  const updates = window.LH180_UPDATES || { senate: {}, house: {} };
  const modelReview = window.LH_MODEL_REVIEW || null;
  const latestPolls = window.LH216_LATEST_POLLS || { senate: {}, house: {} };
  if (!data) return;

  const $ = (id) => document.getElementById(id);
  const labels = {
    toward_D: "向 D",
    toward_R: "向 R",
    flat: "持平",
    insufficient: "证据不足",
  };
  const signalOrder = { toward_D: 0, toward_R: 1, flat: 2, insufficient: 3 };

  // Fresh, pollster-balanced Senate cross-check. This layer does not rewrite the
  // sealed poll ledger: it changes only the dashboard reading shown to users.
  const senateCrossChecks = {
    Michigan: {
      momentum: "toward_D",
      headline: "初选后向 D；最新 D+5",
      status: "跨机构确认",
      level: "晚窗约 D+4；MSU/YouGov D+5 LV",
      summary: "MSU/YouGov gives El-Sayed a 5-point likely-voter lead and a 4-point registered-voter lead. It confirms the post-primary Democratic advantage, but it is consistent with the existing late window rather than evidence of further acceleration.",
    },
    Texas: {
      momentum: "toward_D",
      headline: "自 6 月向 D 移动；最近趋稳",
      status: "跨机构确认",
      level: "当前约 D+2",
      summary: "7–8 月多数机构给出 D+2 至 D+6，Texas A&M 由持平转 D+4；Emerson 仍为 R+1。多机构确认相对 6 月向 D，但最近没有新的加速。",
    },
    "North Carolina": {
      momentum: "flat",
      headline: "D 领先稳定；可能温和增强",
      status: "方向大致一致",
      level: "当前约 D+8",
      summary: "Harper 由 D+8 升至 D+13，Change/Carolina Forward 大致 D+7 至 D+9，但 High Point 从 D+8 回到 D+5。D 领先获得多机构支持，新增动量尚未稳过 3pp 门槛。",
    },
    Georgia: {
      momentum: "flat",
      headline: "D 领先稳定；无清晰新动量",
      status: "水平获确认",
      level: "当前约 D+7.5",
      summary: "六家机构均给出 D 领先，范围约 D+4 至 D+13；最新两项为 D+7 与 D+9。证据支持当前 D 领先，不支持继续加速。",
    },
    Iowa: {
      momentum: "toward_R",
      headline: "两窗仍向 R；最新点有所缓和",
      status: "达到预注册门槛",
      level: "两窗变化约 3.5pp toward R；最新 R+2",
      summary: "Wedgewood's R+2 is less Republican than the preceding Emerson R+3 and Suffolk R+4 results. Adding it leaves the registered two-window change at roughly 3.5 points toward Republicans, while suggesting stabilization rather than continued acceleration.",
    },
    Maine: {
      momentum: "insufficient",
      headline: "最新一项偏 D；等待复核",
      status: "单项新证据",
      level: "旧均值约 D+2；新项 D+8",
      summary: "8 月末一项新民调给出 D+8，但尚缺第二家同期机构确认。先标作可能向 D，不把单项结果写成动量。",
    },
    "New Hampshire": {
      momentum: "insufficient",
      headline: "机构序列相互冲突",
      status: "不作动量判断",
      level: "UNH R+2；St. Anselm D+7",
      summary: "UNH 从年初 D+5 走到 8 月 R+2；St. Anselm 同期却从 D+3 走到 D+7。两条高频序列相差 9pp，不能合成为同一方向。",
    },
    "Ohio (special)": {
      momentum: "insufficient",
      headline: "D 小幅领先；机构间无一致动量",
      status: "水平可读、动量冲突",
      level: "当前约 D+2.6",
      summary: "Fox 5 月和 8 月均为 D+8，显示自身序列持平；NYT 为 R+3，AARP 为 D+3。旧两窗的 D+4 变化没有跨机构复现，因此不再写成确认动量。",
    },
    Alaska: {
      momentum: "insufficient",
      headline: "接近五五开；样本稀疏且冲突",
      status: "证据不足",
      level: "当前约 D+2",
      summary: "DFP 为 D+6、NYT/Siena 为 R+2、PPP 为 D+2。方向不一致且时间点少，暂只读作竞争激烈。",
    },
    "Florida (special)": {
      momentum: "flat",
      headline: "R 领先稳定；无清晰新动量",
      status: "水平获确认",
      level: "当前约 R+8.4",
      summary: "UNF 从 2 月 R+7 到 7 月 R+10，Echelon 与 Emerson 为 R+7、R+8。多机构确认 R 领先，位移幅度不足以支持新的趋势判断。",
    },
  };

  data.rows.forEach((row) => {
    if (row.chamber !== "senate" || !senateCrossChecks[row.race]) return;
    row.registered_momentum = row.momentum;
    row.registered_delta_pp = row.delta_pp;
    row.crosscheck = senateCrossChecks[row.race];
  });

  data.rows.forEach((row) => {
    const senateUpdate = row.chamber === "senate" ? updates.senate?.[row.race] : null;
    const currentSenate = row.chamber === "senate" ? latestPolls.senate?.[row.race] : null;
    if (currentSenate?.crosscheck) row.crosscheck = currentSenate.crosscheck;
    const incrementalPoints = [senateUpdate?.point, ...(currentSenate?.points || [])].filter(Boolean);
    if (incrementalPoints.length && row.poll_trend) {
      const points = [...(row.poll_trend.points || [])];
      incrementalPoints.forEach((newPoint) => {
        const key = `${newPoint.date}|${newPoint.pollster}|${newPoint.margin_dem_minus_rep}`;
        const exists = points.some((point) => `${point.date}|${point.pollster}|${point.margin_dem_minus_rep}` === key);
        if (!exists) points.push(newPoint);
      });
      points.sort((a, b) => a.date.localeCompare(b.date));
      row.poll_trend = {
        ...row.poll_trend,
        points,
        n: points.length,
        status: points.length > 1 ? "series" : points.length === 1 ? "single" : "missing",
        date_start: points[0]?.date || null,
        date_end: points.at(-1)?.date || null,
        latest_margin_dem_minus_rep: points.at(-1)?.margin_dem_minus_rep ?? null,
        source: `${row.poll_trend.source}; independent verified update layers through ${latestPolls.as_of || updates.as_of}`,
      };
      row.latest_poll_sources = (currentSenate?.points || []).map((point) => ({
        label: point.source_label,
        url: point.source_url,
      }));
    }
    const houseUpdate = row.chamber === "house" ? (latestPolls.house?.[row.race] || updates.house?.[row.race]) : null;
    if (houseUpdate) row.latest_evidence = houseUpdate;
  });

  $("asOf").textContent = data.as_of;
  if ($("crossCheckAsOf")) $("crossCheckAsOf").textContent = latestPolls.as_of || updates.as_of || "2026-09-01";
  if ($("modelReviewAsOf")) $("modelReviewAsOf").textContent = modelReview?.as_of || "—";
  $("genericBallot").textContent = `D+${data.summary.generic_ballot_poll_mean.toFixed(1)}`;
  $("genericMomentum").textContent = data.summary.generic_ballot_momentum === "none" ? "近 4/8 周无预注册动量" : data.summary.generic_ballot_momentum;
  $("environmentE").textContent = `D+${data.summary.cross_aggregator_E.toFixed(1)}`;
  $("environmentDelta").textContent = `较上次 ${signed(data.summary.cross_aggregator_delta_E)} pp`;
  if ($("environmentSources")) {
    $("environmentSources").textContent = "等权输入：DDHQ 6.1 · 501 6.1 · RtWH 6.0 · RCP 6.4 · Silver 6.6 · VoteHub 6.0";
  }
  $("houseCount").textContent = data.counts.house;
  $("senateCount").textContent = data.counts.senate;
  $("disclaimer").textContent = data.required_disclaimer;

  if ($("latestEvidence") && latestPolls.national_context) {
    const nationalLinks = (latestPolls.national_context.sources || []).map((source) =>
      `<a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.label)}</a>`
    ).join(" · ");
    const freshSenatePoints = Object.values(latestPolls.senate || {}).reduce((count, entry) => count + (entry.points || []).length, 0);
    const freshSenateStates = Object.keys(latestPolls.senate || {}).length;
    const iowaNewest = latestPolls.senate?.Iowa?.points?.at(-1);
    const tx35 = latestPolls.house?.["TX-35"];
    $("latestEvidence").innerHTML = `
      <div class="latest-heading"><div><span>LATEST VERIFIED EVIDENCE</span><h2>September 3 update</h2></div><b>No rating or model changes</b></div>
      <div class="latest-grid">
        <article><strong>National context · ${escapeHtml(latestPolls.national_context.aggregate_snapshot)}</strong><p>${escapeHtml(latestPolls.national_context.summary)}</p><small>${nationalLinks}</small></article>
        <article><strong>Senate · ${freshSenatePoints} new points across ${freshSenateStates} states</strong><p>Every point records field dates, population, sample, margin, source, and sponsorship status. Forecast outputs were excluded.</p><small>Gold dots are the independent verified layers; the sealed ledger remains unchanged.</small></article>
        <article><strong>Iowa · newest ${escapeHtml(iowaNewest ? signed(iowaNewest.margin_dem_minus_rep) : "—")}pp</strong><p>Emerson has Hinson ahead 50–45, while the adjacent Abacus sample points the other way. The dashboard marks the conflict instead of manufacturing a trend.</p><small><a href="${escapeHtml(iowaNewest?.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(iowaNewest?.source_label)}</a></small></article>
        <article><strong>TX-35 · ${escapeHtml(tx35?.headline || "new district poll")}</strong><p>${escapeHtml(tx35?.detail || "")}</p><small><a href="${escapeHtml(tx35?.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(tx35?.source_label)}</a></small></article>
      </div>`;
  }

  if ($("modelReview") && modelReview) {
    const layers = (modelReview.layers || []).map((layer) => `
      <article>
        <span>${escapeHtml(layer.label)}</span>
        <h3>${escapeHtml(layer.headline)}</h3>
        <p>${escapeHtml(layer.detail)}</p>
        <small>${escapeHtml(layer.evidence)}</small>
      </article>`).join("");
    $("modelReview").innerHTML = `
      <details><summary>历史模型审计（原文保留，已撤下当前映射）</summary><div class="model-review-head">
        <div><span>STRUCTURAL MODEL AUDIT · ${escapeHtml(modelReview.as_of)}</span><h2>What the map uses—and what it does not</h2></div>
        <b>${escapeHtml(modelReview.status)}</b>
      </div>
      <p class="model-review-summary">${escapeHtml(modelReview.summary)}</p>
      <div class="model-review-grid">${layers}</div></details>`;
  }

  function signed(value) {
    if (value == null) return "—";
    return `${value > 0 ? "+" : value < 0 ? "−" : "±"}${Math.abs(value).toFixed(1)}`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function senateTrend(row) {
    const trend = row.poll_trend;
    if (!trend || trend.status === "missing") {
      const excluded = trend?.excluded_count || 0;
      return `<section class="poll-trend empty-trend" aria-label="${escapeHtml(row.race)} polling trend unavailable">
        <div class="trend-head"><b>Polling trend · raw D−R</b><span>No qualifying series</span></div>
        <p>No qualifying formal-matchup polling series appears in the sealed data.${excluded ? ` ${excluded} malformed source row${excluded === 1 ? " was" : "s were"} excluded.` : ""}</p>
      </section>`;
    }
    const points = trend.points || [];
    const width = 340, height = 126, left = 30, right = 10, top = 12, bottom = 24;
    const values = points.map((point) => Number(point.margin_dem_minus_rep));
    const sortedAbs = values.map(Math.abs).sort((a, b) => a - b);
    const robustAbs = sortedAbs[Math.floor((sortedAbs.length - 1) * 0.9)];
    const limit = Math.min(20, Math.max(5, Math.ceil(robustAbs / 5) * 5));
    const timestamps = points.map((point) => new Date(`${point.date}T00:00:00Z`).getTime());
    const minTime = Math.min(...timestamps), maxTime = Math.max(...timestamps);
    const x = (time, index) => maxTime === minTime
      ? left + (points.length === 1 ? (width - left - right) / 2 : index * (width - left - right) / (points.length - 1))
      : left + (time - minTime) * (width - left - right) / (maxTime - minTime);
    const y = (value) => {
      const clippedValue = Math.max(-limit, Math.min(limit, value));
      return top + (limit - clippedValue) * (height - top - bottom) / (2 * limit);
    };
    const coords = points.map((point, index) => ({
      ...point,
      x: x(timestamps[index], index),
      y: y(Number(point.margin_dem_minus_rep)),
    }));
    const polyline = coords.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
    const circles = coords.map((point) => {
      const detail = `${point.date_label || point.date} · ${point.pollster || "Unknown pollster"} · D−R ${signed(Number(point.margin_dem_minus_rep))} pp${point.sample_size ? ` · n=${point.sample_size}` : ""}${point.population ? ` · ${point.population}` : ""}${point.partisan_sponsorship ? ` · ${point.partisan_sponsorship}` : ""}`;
      const isClipped = Math.abs(Number(point.margin_dem_minus_rep)) > limit;
      const pointClasses = [isClipped ? "trend-point-clipped" : "", point.update_layer ? "trend-point-update" : ""].filter(Boolean).join(" ");
      return `<circle class="${pointClasses}" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="${point.update_layer ? "4.1" : "3.2"}" tabindex="0"><title>${escapeHtml(point.update_layer ? `Verified incremental update${point.release_date ? ` · released ${point.release_date}` : ""} · ${detail}` : isClipped ? `Valid extreme value edge-clipped for display only · ${detail}` : detail)}</title></circle>`;
    }).join("");
    const clipped = coords.filter((point) => Math.abs(Number(point.margin_dem_minus_rep)) > limit);
    const clippedLabels = clipped.slice(0, 2).map((point) => {
      const isTop = Number(point.margin_dem_minus_rep) > 0;
      return `<text class="trend-outlier-label" x="${point.x.toFixed(1)}" y="${isTop ? top + 9 : height - bottom - 4}">${escapeHtml(signed(Number(point.margin_dem_minus_rep)))}</text>`;
    }).join("");
    const dateLabel = points.length === 1 ? points[0].date : `${trend.date_start} → ${trend.date_end}`;
    const statusParts = [points.length === 1 ? "One poll" : `${points.length} polls`];
    if (trend.excluded_count) statusParts.push(`${trend.excluded_count} malformed excluded`);
    if (clipped.length) statusParts.push(`${clipped.length} extreme value${clipped.length === 1 ? "" : "s"} edge-clipped`);
    statusParts.push(points.length === 1 ? "no trend inference" : `latest ${signed(trend.latest_margin_dem_minus_rep)} pp`);
    const statusText = statusParts.join(" · ");
    const clippedDisclosure = clipped.length
      ? `<p class="trend-clipping"><b>显示裁剪：</b>纵轴限于 ±${limit}pp；以下合法极值只在图上压到边缘，原始数值未改：${clipped.map((point) => `${escapeHtml(point.date)} ${escapeHtml(point.pollster || "Unknown pollster")} ${escapeHtml(signed(Number(point.margin_dem_minus_rep)))}pp`).join("；")}。</p>`
      : "";
    return `<section class="poll-trend" aria-label="${escapeHtml(row.race)} raw polling trend">
      <div class="trend-head"><b>Polling trend · raw D−R</b><span>${escapeHtml(statusText)}</span></div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(row.race)} raw Democratic minus Republican polling margins from ${escapeHtml(dateLabel)}">
        <line class="trend-zero" x1="${left}" y1="${y(0).toFixed(1)}" x2="${width - right}" y2="${y(0).toFixed(1)}"></line>
        <text class="trend-axis" x="2" y="${(y(limit) + 4).toFixed(1)}">D+${limit}</text>
        <text class="trend-axis" x="2" y="${(y(0) + 4).toFixed(1)}">0</text>
        <text class="trend-axis" x="2" y="${(y(-limit) + 4).toFixed(1)}">R+${limit}</text>
        ${points.length > 1 ? `<polyline class="trend-line" points="${polyline}"></polyline>` : ""}
        <g class="trend-points">${circles}</g>
        ${clippedLabels}
        <text class="trend-date" x="${left}" y="${height - 5}">${escapeHtml(points[0].date)}</text>
        <text class="trend-date trend-date-end" x="${width - right}" y="${height - 5}">${escapeHtml(points[points.length - 1].date)}</text>
      </svg>
      <p>${points.length === 1 ? "Only one qualifying poll; no trend inference." : `每个点是一份原始民调；${points.some((point) => point.update_layer) ? "金色圆点是独立核验增量；" : ""}下方跨机构复核决定最新判读。`}</p>
      ${clippedDisclosure}
    </section>`;
  }

  function currentFilters() {
    return {
      q: $("searchInput").value.trim().toLowerCase(),
      chamber: document.querySelector('input[name="chamber"]:checked').value,
      evidence: document.querySelector('input[name="evidence"]:checked').value,
      momentum: new Set([...document.querySelectorAll('input[name="momentum"]:checked')].map((el) => el.value)),
      sort: $("sortSelect").value,
    };
  }

  function displayedMomentum(row) {
    return row.chamber === "house" ? "insufficient" : (row.crosscheck?.momentum || row.momentum);
  }

  function matches(row, f) {
    const haystack = [row.race, row.state, row.state_name, row.candidate, row.opponent, row.incumbent, row.pvi].filter(Boolean).join(" ").toLowerCase();
    if (f.q && !haystack.includes(f.q)) return false;
    if (f.chamber !== "all" && row.chamber !== f.chamber) return false;
    if (!f.momentum.has(displayedMomentum(row))) return false;
    const estimated = row.evidence === "model_transfer_estimate";
    const measured = (!estimated && displayedMomentum(row) !== "insufficient") || Boolean(row.latest_evidence);
    if (f.evidence === "measured" && !measured) return false;
    if (f.evidence === "estimated" && !estimated) return false;
    if (f.evidence === "missing" && measured) return false;
    return true;
  }

  function sortRows(rows, mode) {
    return rows.sort((a, b) => {
      if (mode === "competitive") return Math.abs(a.pvi_dem ?? 99) - Math.abs(b.pvi_dem ?? 99) || a.race.localeCompare(b.race);
      if (mode === "state") return a.race.localeCompare(b.race);
      if (mode === "delta") return Math.abs(b.chamber === "house" ? 0 : (b.delta_pp ?? 0)) - Math.abs(a.chamber === "house" ? 0 : (a.delta_pp ?? 0)) || a.race.localeCompare(b.race);
      return signalOrder[displayedMomentum(a)] - signalOrder[displayedMomentum(b)] || Math.abs(b.chamber === "house" ? 0 : (b.delta_pp ?? 0)) - Math.abs(a.chamber === "house" ? 0 : (a.delta_pp ?? 0)) || a.race.localeCompare(b.race);
    });
  }

  function card(row) {
    const momentum = displayedMomentum(row);
    const senateDirection = Number(row.delta_pp) >= 0 ? "toward D" : "toward R";
    const delta = row.chamber === "house"
      ? "逐区动量证据不足"
      : row.crosscheck
        ? row.crosscheck.headline
      : row.delta_pp == null
        ? "Momentum not judged"
        : row.momentum === "flat"
          ? `Later-window change ${signed(row.delta_pp)} pp ${senateDirection} · stable`
          : `New momentum ${signed(row.delta_pp)} pp ${senateDirection}`;
    const subject = row.chamber === "house"
      ? (row.candidate || "提名待定")
      : ([row.candidate, row.opponent].filter(Boolean).join(" vs ") || "Matchup pending");
    const secondaryLabel = row.chamber === "house" ? "候选人层" : "评级共识";
    const secondary = row.chamber === "house"
      ? ({ qualified: "合格", unqualified: "未达冻结定义", pending: "待定" }[row.candidate_quality] || "—")
      : row.rating;
    const level = row.chamber === "house" ? (row.latest_evidence ? "有增量民调；见下方口径" : "暂无统一逐区序列") : `${row.competitive_raters}/${row.rater_count}`;
    const currentHolder = `${row.current_holder_label || "Current holder unknown"}${row.chamber === "senate" && row.retiring ? " (retiring)" : ""}`;
    const trend = row.chamber === "senate" ? senateTrend(row) : "";
    const structure = row.chamber === "senate" && row.structural_context?.insight
      ? `<section class="structure-note"><b>Race-specific structural insight</b><p>${escapeHtml(row.structural_context.insight)}</p></section>`
      : "";
    const freshSourceLinks = (row.latest_poll_sources || []).filter((source) => source.url).map((source) =>
      `<a class="source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.label || "原始来源")}</a>`
    ).join(" · ");
    const crosscheck = row.crosscheck
      ? `<section class="crosscheck-note status-${escapeHtml(row.crosscheck.momentum)}">
          <div class="crosscheck-head"><b>跨机构复核 · 截至 ${escapeHtml(latestPolls.as_of || updates.as_of || "—")}</b><span>${escapeHtml(row.crosscheck.status)}</span></div>
          <strong>${escapeHtml(row.crosscheck.level)}</strong>
          <p>${escapeHtml(row.crosscheck.summary)}</p>
          ${freshSourceLinks ? `<small>${freshSourceLinks}</small>` : ""}
        </section>`
      : "";
    const latestEvidence = row.latest_evidence
      ? `<section class="crosscheck-note ${row.latest_evidence.status === "partisan_conflict" ? "status-insufficient" : "status-flat"}">
          <div class="crosscheck-head"><b>District poll update · through ${escapeHtml(latestPolls.as_of || updates.as_of || "—")}</b><span>${row.latest_evidence.status === "partisan_conflict" ? "partisan internals conflict" : "single sponsored poll"}</span></div>
          <strong>${escapeHtml(row.latest_evidence.headline)}</strong>
          <p>${escapeHtml(row.latest_evidence.detail)}</p>
          <a class="source-link" href="${escapeHtml(row.latest_evidence.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.latest_evidence.source_label)}</a>
        </section>`
      : "";
    const explanation = row.chamber === "house" || row.crosscheck ? "" : `<p class="explanation">${escapeHtml(row.explanation)}</p>`;
    return `
      <article class="race-card ${momentum} holder-${(row.current_holder_party || "unknown").toLowerCase()}" tabindex="0" aria-label="${escapeHtml(row.race)}，${escapeHtml(delta)}">
        <div class="card-top">
          <div><span class="chamber">${row.chamber === "house" ? "HOUSE" : "SENATE"}</span><h3 class="race-name">${escapeHtml(row.race)}</h3></div>
          <span class="badge"><small>PVI baseline</small><b>${escapeHtml(row.pvi || "Unavailable")}</b></span>
        </div>
        <div class="delta">${escapeHtml(delta)}</div>
        <div class="evidence">${escapeHtml(row.chamber === "house" ? "旧筛选样本；不提供控制权推断" : row.evidence_label)}</div>
        <div class="meta">
          <div><span>${row.chamber === "house" ? "民主党提名人" : "Formal matchup"}</span><b title="${escapeHtml(subject)}">${escapeHtml(subject)}</b></div>
          <div><span>${escapeHtml(secondaryLabel)}</span><b>${escapeHtml(secondary)}</b></div>
          <div><span>Current holder</span><b class="holder-value" title="${escapeHtml(currentHolder)}">${escapeHtml(currentHolder)}</b></div>
          <div><span>${row.chamber === "house" ? "当前推断状态" : "最新证据状态"}</span><b>${escapeHtml(row.chamber === "house" ? "映射未验证" : labels[momentum])}</b></div>
          <div><span>${row.chamber === "house" ? "逐区证据覆盖" : "竞争评级方"}</span><b>${escapeHtml(level)}</b></div>
        </div>
        ${trend}
        ${crosscheck}
        ${latestEvidence}
        ${structure}
        ${explanation}
      </article>`;
  }

  function render() {
    const f = currentFilters();
    const rows = sortRows(data.rows.filter((row) => matches(row, f)), f.sort);
    $("resultCount").textContent = rows.length;
    $("senateGuide").hidden = !rows.some((row) => row.chamber === "senate");
    $("raceGrid").innerHTML = rows.map(card).join("");
    $("emptyState").hidden = rows.length !== 0;
  }

  document.querySelectorAll("input, select").forEach((el) => el.addEventListener(el.type === "search" ? "input" : "change", render));
  $("resetFilters").addEventListener("click", () => {
    $("searchInput").value = "";
    document.querySelector('input[name="chamber"][value="all"]').checked = true;
    document.querySelector('input[name="evidence"][value="all"]').checked = true;
    document.querySelectorAll('input[name="momentum"]').forEach((el) => { el.checked = true; });
    $("sortSelect").value = "signal";
    render();
  });
  render();
})();
