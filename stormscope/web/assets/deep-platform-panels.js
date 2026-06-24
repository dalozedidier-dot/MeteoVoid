(function () {
  const apiCache = new Map();
  async function readJson(path) {
    if (apiCache.has(path)) return apiCache.get(path);
    const promise = fetch(path, { cache: "no-store" }).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
    apiCache.set(path, promise);
    return promise;
  }
  function esc(value) {
    return String(value == null ? "—" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function target() {
    return document.querySelector("#view-expert .sec") || document.querySelector("#view-methode .sec") || document.querySelector("#view-europe .sec") || document.querySelector("main");
  }
  function panel(id, title, meta) {
    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement("section");
      el.id = id;
      el.className = "mv-deep-panel panel";
      const t = target();
      if (t) t.appendChild(el);
    }
    el.innerHTML = '<div class="sec-h"><h2>' + esc(title) + '</h2><div class="rule"></div><span class="meta">' + esc(meta || "API") + "</span></div>";
    return el;
  }
  function kv(label, value) {
    return '<div class="cell2"><div class="k">' + esc(label) + '</div><div class="v" style="font-size:18px">' + esc(value) + "</div></div>";
  }
  function renderSources(data) {
    const el = panel("mv-deep-sources", "Sources météo Europe", data.contract);
    const rows = Object.entries(data.countries || {}).slice(0, 12).map(([key, item]) => {
      const active = (item.active || []).map((s) => s.label || s.id).join(", ") || "—";
      const candidates = (item.candidates || []).map((s) => s.label || s.id).join(", ") || "—";
      return "<tr><td>" + esc(item.label || key) + "</td><td>" + esc(active) + "</td><td>" + esc(candidates) + "</td><td>" + esc(item.historical_validation || "—") + "</td></tr>";
    }).join("");
    el.innerHTML += '<div class="note"><b>Lecture.</b> Open-Meteo reste le socle. Les sources nationales enrichissent pays par pays.</div><div style="overflow:auto"><table class="mv-table"><thead><tr><th>Pays</th><th>Actives</th><th>Candidates</th><th>Historique</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
  }
  function renderValidation(data) {
    const el = panel("mv-deep-validation", "Validation et mémoire", data.contract);
    el.innerHTML += '<div class="ing">' + kv("Prévisions archivées", data.forecast_history_rows) + kv("Événements", data.history_rows) + kv("Brier", data.recommended_scores && data.recommended_scores.brier_score) + kv("CSI", data.recommended_scores && data.recommended_scores.csi) + '</div><div class="note"><b>Règle.</b> Les faux positifs, les ratés et les cas indéterminés doivent rester visibles.</div>';
  }
  function renderListPanel(id, title, data, rows) {
    const el = panel(id, title, data.contract);
    el.innerHTML += '<div class="net">' + (rows || '<div class="note">Aucune donnée disponible.</div>') + "</div>";
  }
  function renderExplain(data) {
    const rows = (data.top_contributors || []).map((x) => '<div class="det"><span class="dot" style="background:var(--c3)"></span><div><div class="nm">' + esc(x.name) + '</div><div class="lv">contribution</div></div><div class="sc">' + esc(x.value) + "</div></div>").join("");
    renderListPanel("mv-deep-explain", "Pourquoi le signal bouge ?", data, rows);
  }
  function renderCorridors(data) {
    const rows = (data.corridors || []).map((x) => '<div class="det"><span class="dot" style="background:var(--c2)"></span><div><div class="nm">' + esc(x.label) + '</div><div class="lv">' + esc(x.status) + '</div></div><div class="sc">' + esc(x.score) + "</div></div>").join("");
    renderListPanel("mv-deep-corridors", "Corridors amont", data, rows);
  }
  function renderTemporal(data) {
    const rows = (data.play_modes || []).map((x) => '<div class="det"><span class="dot" style="background:' + (x.available ? 'var(--c1)' : 'var(--faint)') + '"></span><div><div class="nm">' + esc(x.label) + '</div><div class="lv">' + esc(x.id) + '</div></div><div class="sc">' + esc(x.available ? 'actif' : 'séparé') + "</div></div>").join("");
    renderListPanel("mv-deep-temporal", "Temporalités séparées", data, rows);
  }
  function renderConfidence(data) {
    const el = panel("mv-deep-confidence", "Confiance du signal", data.contract);
    el.innerHTML += '<div class="ing">' + kv("Confiance", data.score) + kv("Règle", "potentiel ≠ observé") + '</div><div class="note">' + esc(data.interpretation || "") + "</div>";
  }
  function renderQuality(data) {
    const rows = (data.stations || []).slice(0, 12).map((x) => '<div class="det"><span class="dot" style="background:var(--c2)"></span><div><div class="nm">' + esc(x.name || x.station_id) + '</div><div class="lv">flatline ' + esc(x.flatline_suspected ? 'oui' : 'non') + ' · gap ' + esc(x.gap_suspected ? 'oui' : 'non') + '</div></div><div class="sc">' + esc(x.quality_score) + "</div></div>").join("");
    renderListPanel("mv-deep-quality", "Qualité des données station", data, rows);
  }
  function renderRadar(data) {
    const el = panel("mv-deep-radar-machine", "Radar machine OPERA", data.contract);
    el.innerHTML += '<div class="ing">' + kv("Fichiers OPERA", data.downloaded_file_count) + kv("Couche machine", data.machine_layer_ready ? "prête" : "non prête") + '</div><div class="note"><b>Pipeline.</b> ' + esc((data.recommended_pipeline || []).join(" → ")) + "</div>";
  }
  function addStyles() {
    if (document.getElementById("mv-deep-style")) return;
    const style = document.createElement("style");
    style.id = "mv-deep-style";
    style.textContent = ".mv-deep-panel{margin-top:18px}.mv-table{width:100%;border-collapse:collapse;font-size:12.5px}.mv-table th,.mv-table td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}.mv-table th{color:var(--dim);font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.08em}.mv-table td{color:var(--ink)}";
    document.head.appendChild(style);
  }
  async function boot() {
    addStyles();
    const [sources, validation, explain, corridors, radar, temporal, confidence, quality] = await Promise.all([
      readJson("api/europe_sources.json"), readJson("api/validation_summary.json"), readJson("api/explain.json"), readJson("api/corridors.json"), readJson("api/radar_machine.json"), readJson("api/temporal_layers.json"), readJson("api/signal_confidence.json"), readJson("api/station_quality_map.json")
    ]);
    if (sources && sources.countries) renderSources(sources);
    if (validation && validation.contract) renderValidation(validation);
    if (explain && explain.contract) renderExplain(explain);
    if (corridors && corridors.contract) renderCorridors(corridors);
    if (temporal && temporal.contract) renderTemporal(temporal);
    if (confidence && confidence.contract) renderConfidence(confidence);
    if (quality && quality.contract) renderQuality(quality);
    if (radar && radar.contract) renderRadar(radar);
  }
  window.addEventListener("DOMContentLoaded", () => boot().catch(() => {}));
})();
