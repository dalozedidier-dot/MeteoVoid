(function () {
  const apiCache = new Map();
  const FETCH_TIMEOUT_MS = 6500;

  function esc(value) {
    return String(value == null ? "—" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function target() {
    return (
      document.querySelector("#view-expert .sec") ||
      document.querySelector("#view-carte .sec") ||
      document.querySelector("#view-veille .sec") ||
      document.querySelector("main")
    );
  }

  async function readJson(path) {
    if (apiCache.has(path)) return apiCache.get(path);
    const promise = fetch(path, { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : {}))
      .catch(() => ({}));
    apiCache.set(path, promise);
    return promise;
  }

  function withTimeout(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    return fetch(url, { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .finally(() => clearTimeout(timer));
  }

  function clamp01(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 0;
    return Math.max(0, Math.min(1, number));
  }

  function findCurrentIndex(times) {
    if (!Array.isArray(times) || !times.length) return 0;
    const nowHour = new Date().toISOString().slice(0, 13);
    const index = times.findIndex((time) => String(time).slice(0, 13) >= nowHour);
    return index >= 0 ? index : 0;
  }

  function hourlyValue(hourly, keys, index) {
    if (!hourly) return null;
    for (const key of keys) {
      const values = hourly[key];
      if (Array.isArray(values) && values[index] != null) return Number(values[index]);
    }
    return null;
  }

  function scoreFromHourly(hourly) {
    const times = hourly && hourly.time;
    const index = findCurrentIndex(times);
    const cape = hourlyValue(hourly, ["cape"], index) || 0;
    const cin = hourlyValue(hourly, ["convective_inhibition"], index) || 0;
    const li = hourlyValue(hourly, ["lifted_index"], index);
    const pp = hourlyValue(hourly, ["precipitation_probability"], index) || 0;
    const gust = hourlyValue(hourly, ["wind_gusts_10m", "wind_gusts_10m_max"], index) || 0;
    const liValue = li == null ? 4 : li;
    const charge = clamp01(cape / 2500);
    const liBlock = clamp01((4 - liValue) / 14);
    const energy = clamp01(0.6 * charge + 0.4 * liBlock);
    const cap = clamp01(1 - cin / 150);
    const trigger = clamp01(0.55 * (pp / 100) + 0.3 * cap + 0.15 * clamp01((gust - 10) / 25));
    return {
      index,
      hour: Array.isArray(times) && times[index] ? times[index] : null,
      score: clamp01(energy * (0.45 + 0.55 * trigger)),
      cape,
      cin,
      li: liValue,
      pp,
      gust,
    };
  }

  function buildUrl(model, center) {
    const variables = [
      "cape",
      "convective_inhibition",
      "lifted_index",
      "precipitation_probability",
      "wind_gusts_10m",
    ].join(",");
    const params = new URLSearchParams({
      latitude: String(center.lat || 50.64),
      longitude: String(center.lon || 4.67),
      hourly: variables,
      forecast_days: "2",
      timezone: "Europe/Brussels",
    });
    if (model.model && model.model !== "best_match") params.set("models", model.model);
    return String(model.endpoint || "https://api.open-meteo.com/v1/forecast") + "?" + params.toString();
  }

  async function fetchModel(model, center) {
    try {
      const data = await withTimeout(buildUrl(model, center));
      const result = scoreFromHourly(data.hourly || {});
      return {
        ...model,
        live_score: Number(result.score.toFixed(3)),
        score_source: "open_meteo_live_browser",
        hour: result.hour,
        cape: result.cape,
        cin: result.cin,
        li: result.li,
        pp: result.pp,
        gust: result.gust,
        available: true,
      };
    } catch (error) {
      return {
        ...model,
        live_score: null,
        score_source: "static_fallback_after_fetch_error",
        error: String(error && error.message ? error.message : error),
        available: false,
      };
    }
  }

  function agreement(models) {
    const scores = models
      .map((model) => (model.live_score == null ? model.fallback_score : model.live_score))
      .filter((score) => Number.isFinite(Number(score)))
      .map(Number);
    if (!scores.length) return { mean: null, spread: null, label: "non disponible" };
    const mean = scores.reduce((acc, value) => acc + value, 0) / scores.length;
    const spread = Math.max(...scores) - Math.min(...scores);
    const label = spread <= 0.12 ? "accord fort" : spread <= 0.28 ? "accord partiel" : "désaccord marqué";
    return { mean, spread, label };
  }

  function addStyles() {
    if (document.getElementById("mv-model-compare-style")) return;
    const style = document.createElement("style");
    style.id = "mv-model-compare-style";
    style.textContent = [
      ".mv-model-compare{margin-top:18px}",
      ".mv-model-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:11px;margin-top:12px}",
      ".mv-model-card{border:1px solid var(--line);border-radius:14px;background:rgba(17,26,44,.72);padding:13px 14px;min-width:0;overflow:hidden}",
      ".mv-model-card b{display:block;font-size:14px;overflow-wrap:anywhere}",
      ".mv-model-card small{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);overflow-wrap:anywhere}",
      ".mv-model-score{font-family:var(--mono);font-size:24px;font-weight:700;margin-top:8px;color:var(--bolt)}",
      ".mv-model-meta{font-size:12px;color:var(--dim);margin-top:6px;overflow-wrap:anywhere}",
      ".mv-model-roadmap{margin-top:12px;font-size:12px;color:var(--dim)}",
      "@media(max-width:700px){.mv-model-grid{grid-template-columns:1fr}.mv-model-score{font-size:21px}}",
    ].join("");
    document.head.appendChild(style);
  }

  function render(config, models) {
    const root = document.getElementById("mv-model-compare") || document.createElement("section");
    root.id = "mv-model-compare";
    root.className = "mv-model-compare panel";
    if (!root.parentNode) {
      const parent = target();
      if (parent) parent.appendChild(root);
    }
    const ag = agreement(models);
    const cards = models
      .map((model) => {
        const score = model.live_score == null ? model.fallback_score : model.live_score;
        const source = model.live_score == null ? "repli statique" : "Open-Meteo live";
        const status = model.available === false ? "indisponible" : source;
        return (
          '<div class="mv-model-card">' +
          "<small>" + esc(model.family || model.provider || "modèle") + "</small>" +
          "<b>" + esc(model.label || model.id) + "</b>" +
          '<div class="mv-model-score">' + esc(Number(score || 0).toFixed(2)) + "</div>" +
          '<div class="mv-model-meta">' + esc(status) + " · " + esc(model.role || "") + "</div>" +
          "</div>"
        );
      })
      .join("");
    const roadmap = (config.grib_direct_roadmap || [])
      .map((item) => "<li><b>" + esc(item.label) + "</b> · " + esc(item.status) + " · " + esc(item.next_step) + "</li>")
      .join("");
    root.innerHTML =
      '<div class="sec-h"><h2>Comparaison modèles</h2><div class="rule"></div><span class="meta">' +
      esc(config.contract || "model_compare") +
      "</span></div>" +
      '<div class="ing">' +
      '<div class="cell2"><div class="k">Accord modèles</div><div class="v" style="font-size:18px">' + esc(ag.label) + "</div></div>" +
      '<div class="cell2"><div class="k">Moyenne</div><div class="v" style="font-size:18px">' + esc(ag.mean == null ? "—" : ag.mean.toFixed(2)) + "</div></div>" +
      '<div class="cell2"><div class="k">Écart</div><div class="v" style="font-size:18px">' + esc(ag.spread == null ? "—" : ag.spread.toFixed(2)) + "</div></div>" +
      "</div>" +
      '<div class="mv-model-grid">' + cards + "</div>" +
      '<div class="note mv-model-roadmap"><b>GRIB direct.</b> Préparé mais non actif dans le front. <ul>' + roadmap + "</ul></div>";
  }

  async function boot() {
    addStyles();
    const config = await readJson("api/model_compare.json");
    if (!config || !Array.isArray(config.models)) return;
    render(config, config.models || []);
    const center = config.center || { lat: 50.64, lon: 4.67 };
    const liveModels = await Promise.all((config.models || []).map((model) => fetchModel(model, center)));
    render(config, liveModels);
  }

  window.addEventListener("DOMContentLoaded", () => boot().catch(() => {}));
})();
