/* MeteoVoid Storm-scope - European source stack panels. */
(function () {
  const esc = (value) =>
    String(value ?? "—").replace(/[&<>'"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]
    );
  const page = window.MV_PAGE || { region: "belgium", kind: "dashboard" };

  async function json(url) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return null;
      return await res.json();
    } catch (err) {
      return null;
    }
  }

  function sourceCard(src) {
    const roles = Array.isArray(src.roles) ? src.roles.slice(0, 4).join(" · ") : src.role || "—";
    return `<div class="cmp"><div class="top"><span class="nm">${esc(src.label || src.id)}</span><span class="sc">${esc(src.status)}</span></div><div class="tx">${esc(roles)}</div><div class="tag">${esc(src.scope || src.auth || "source")}</div></div>`;
  }

  function profileBlock(data, region) {
    const countries = data.countries || {};
    const profile = countries[region] || countries.europe || {};
    const stack = Array.isArray(profile.stack) ? profile.stack : [];
    const experimental = Array.isArray(data.experimental_sources) ? data.experimental_sources : [];
    return `
      <div class="sec-h"><h2>Sources Europe</h2><div class="rule"></div><span class="meta">${esc(profile.label || region)}</span></div>
      <div class="note"><b>Stratégie.</b> ${esc(profile.strategy || (data.summary && data.summary.rule) || "Open-Meteo reste le socle Europe.")}</div>
      <div class="comp">${stack.map(sourceCard).join("")}</div>
      <div class="sec-h" style="margin-top:24px"><h2 style="font-size:20px">Sources expérimentales écartées du cœur</h2><div class="rule"></div><span class="meta">scrapers · forks</span></div>
      <div class="comp">${experimental.slice(0, 6).map((src) => `<div class="cmp"><div class="top"><span class="nm">${esc(src.label || src.id)}</span><span class="sc">${esc(src.status)}</span></div><div class="tx">${esc(src.reason)}</div><div class="tag">${esc(src.category)}</div></div>`).join("")}</div>
    `;
  }

  function europeOverview(data) {
    const core = Array.isArray(data.core_sources) ? data.core_sources : [];
    const countries = Object.values(data.countries || {}).filter((x) => x && typeof x === "object");
    return `
      <div class="sec-h" style="margin-top:24px"><h2>Sources météo ouvertes</h2><div class="rule"></div><span class="meta">Europe</span></div>
      <div class="note"><b>Socle.</b> ${esc((data.summary && data.summary.rule) || "Open-Meteo reste la couche commune.")}</div>
      <div class="comp">${core.map(sourceCard).join("")}</div>
      <div class="sec-h" style="margin-top:24px"><h2 style="font-size:20px">Profil par pays</h2><div class="rule"></div><span class="meta">source active · candidate</span></div>
      <div class="comp">${countries.map((p) => `<div class="cmp"><div class="top"><span class="nm">${esc(p.label || p.country)}</span><span class="sc">${esc(p.forecast_primary || "open_meteo")}</span></div><div class="tx">${esc(p.strategy || "Open-Meteo first")}</div><div class="tag">active ${esc(p.active_count || 0)} · candidates ${esc(p.candidate_count || 0)}</div></div>`).join("")}</div>
    `;
  }

  function ensure(id, target) {
    if (!target) return null;
    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement("div");
      el.id = id;
      el.className = "source-block";
      target.appendChild(el);
    }
    return el;
  }

  async function render() {
    const data = await json("api/europe_sources.json");
    if (!data || !data.contract) return;
    const region = page.region || "europe";
    const europe = ensure("europeSourcesOverview", document.getElementById("view-europe"));
    if (europe) europe.innerHTML = europeOverview(data);
    const expert = ensure("europeSourcesExpert", document.getElementById("view-expert"));
    if (expert) expert.innerHTML = profileBlock(data, region);
    const method = ensure("europeSourcesMethod", document.getElementById("view-methode"));
    if (method) method.innerHTML = profileBlock(data, region);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
