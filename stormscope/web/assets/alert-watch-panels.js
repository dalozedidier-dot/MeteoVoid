/* MeteoVoid Storm-scope — panneaux Belgium Alert Watch + correction cartes. */
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (value) =>
    String(value ?? "—").replace(/[&<>'"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]
    );
  const n = (value, digits = 2) => {
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(digits).replace(".", ",") : "—";
  };

  async function getJSON(url) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return null;
      return await res.json();
    } catch (err) {
      return null;
    }
  }

  async function loadWatch() {
    const direct = await getJSON("api/watch.json");
    if (direct && direct.contract) return direct;
    const [latest, convective, sources, radar, upstream, validation, history, weather] =
      await Promise.all([
        getJSON("api/latest.json"),
        getJSON("api/convective_live.json"),
        getJSON("api/sources.json"),
        getJSON("api/radar.json"),
        getJSON("api/upstream.json"),
        getJSON("api/validation.json"),
        getJSON("api/validation_history.json"),
        getJSON("api/weather_5days.json"),
      ]);
    if (!latest && !convective && !radar) return null;
    return {
      contract: "meteovoid_belgium_alert_watch_public_fallback_v1",
      generated_at: latest && latest.generated_at,
      run_id: latest && latest.run_id,
      data_mode: latest && latest.data_mode,
      latest: latest || {},
      convective_live_inputs: convective || {},
      sources: sources || {},
      radar: { radar_stack: radar || {} },
      upstream_watch: upstream || {},
      validation: validation || {},
      validation_history: history || {},
      weather_5days: weather || {},
      artefacts: defaultArtefacts(),
    };
  }

  function defaultArtefacts() {
    return [
      ["Cartes", "Dashboard complet", "reports/latest/belgium_alert_dashboard.html"],
      ["Cartes", "Carte risque station", "reports/latest/belgium_alert_map.html"],
      ["Cartes", "Radar Belgique", "reports/latest/belgium_radar_map.html"],
      ["Cartes", "Convectif natif", "reports/latest/belgium_native_convective_map.html"],
      ["Cartes", "Radars nationaux Europe", "reports/latest/european_national_radar_map.html"],
      ["Analyse", "Rapport Belgique", "reports/latest/belgium_alert_report.md"],
      ["Analyse", "Transition convective", "reports/latest/convective_transition_dashboard.html"],
      ["Analyse", "Europe amont", "reports/latest/european_upstream_map.html"],
      ["Analyse", "Graphe informationnel", "reports/latest/information_graph.html"],
      ["Preuve", "Signaux précoces", "reports/latest/early_warning_dashboard.html"],
      ["Preuve", "Validation", "reports/latest/validation_dashboard.html"],
      ["Preuve", "Auto-surveillance", "reports/latest/self_watchdog.html"],
      ["Exports", "API watch", "api/watch.json"],
      ["Exports", "API radar", "api/radar.json"],
      ["Exports", "API sources", "api/sources.json"],
      ["Exports", "OPERA ORD", "reports/latest/opera_ord_status.json"],
    ].map(([group, label, href]) => ({ group, label, href }));
  }

  function levelLabel(obj, fallback = "—") {
    if (!obj) return fallback;
    if (typeof obj === "string") return obj.replaceAll("_", " ");
    return obj.label || obj.key || fallback;
  }

  function card(title, value, note = "", tag = "") {
    return `<div class="cmp"><div class="top"><span class="nm">${esc(title)}</span><span class="sc">${esc(
      value
    )}</span></div>${note ? `<div class="tx">${esc(note)}</div>` : ""}${
      tag ? `<div class="tag">${esc(tag)}</div>` : ""
    }</div>`;
  }

  function fieldCards(fields) {
    const entries = Object.values(fields || {}).filter((f) => f && typeof f === "object");
    const priority = [
      "dew_point_c",
      "cape_jkg",
      "cin_jkg",
      "shear_0_6km_ms",
      "surface_convergence_index",
      "pressure_hpa",
      "wind_gust_ms",
      "pwat_mm",
      "temperature_850hpa_c",
      "temperature_700hpa_c",
      "temperature_500hpa_c",
      "radar",
      "lightning",
      "satellite",
    ];
    entries.sort((a, b) => priority.indexOf(a.key) - priority.indexOf(b.key));
    return entries
      .map((f) => {
        const value = f.value == null ? f.status || "absent" : `${n(f.value, 1)} ${f.unit || ""}`;
        const note = `${f.available ? "réel" : "non intégré"} · ${f.source || f.basis || "source non renseignée"}`;
        return card(f.label || f.key, value, note, f.family || f.status || "ingrédient");
      })
      .join("");
  }

  function artefactLinks(items) {
    const list = (items && items.length ? items : defaultArtefacts()).slice(0, 42);
    return `<div class="watch-links">${list
      .map(
        (a) =>
          `<a href="${esc(a.href)}"><span>${esc(a.group || "Lien")}</span><b>${esc(
            a.label || a.href
          )}</b></a>`
      )
      .join("")}</div>`;
  }

  function renderWatch(watch) {
    const latest = watch.latest || {};
    const scoreLayers = latest.score_layers || {};
    const confidence = latest.confidence || {};
    const zone = latest.main_zone || {};
    const windowInfo = latest.critical_window || {};
    const heat = watch.heat || {};
    const convective = watch.convective_live_inputs || {};
    const sources = watch.sources || {};
    const sourceSummary = sources.summary || sources;
    const radar = watch.radar || {};
    const radarStack = radar.radar_stack || radar;
    const opera = radar.opera_ord_inventory || radarStack.opera_ord || {};
    const operaMetrics = radar.opera_radar_metrics || radarStack.opera_radar_metrics || {};
    const national = radar.european_national_radar || radarStack.european_national_radar || {};
    const upstream = watch.upstream_watch || {};
    const validation = watch.validation || {};
    const history = watch.validation_history || {};
    const dataQuality = watch.data_quality || {};
    const weather = watch.weather_5days || {};
    const explanation = latest.alert_explanation || {};
    const bullets = Array.isArray(explanation.bullets) ? explanation.bullets : [];

    return `
      <div class="sec-h"><h2>Belgium Alert Watch</h2><div class="rule"></div><span class="meta">run ${esc(
        watch.run_id || "—"
      )}</span></div>
      <div class="comp">
        ${card("Niveau public", levelLabel(latest.operational_level), latest.public_wording || latest.synthesis, "contrat public")}
        ${card("Score modèle", n(latest.model_score, 3), latest.synthesis || "", "signal interne")}
        ${card("Risque convectif", n(scoreLayers.convective_risk_score, 3), "score séparé de la chaleur", "convectif")}
        ${card("Chaleur", n(scoreLayers.heat_stress_score, 3), levelLabel(heat.level), "heat stress")}
        ${card("Confiance", n(confidence.score, 3), confidence.label || "", "qualité signal")}
        ${card("Zone principale", zone.name || "—", `station : ${zone.top_station || "—"}`, "spatial")}
        ${card("Fenêtre sensible", windowInfo.label || windowInfo.peak_hour || "—", `pic : ${windowInfo.peak || "—"}`, "timing")}
        ${card("Alerte officielle", latest.official_alert ? "oui" : "non", latest.public_alert_allowed ? "publication prudente autorisée" : "publication prudente", "IRM/MeteoAlarm")}
      </div>
      ${bullets.length ? `<div class="note"><b>Pourquoi ce niveau ?</b><ul>${bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></div>` : ""}

      <div class="sec-h"><h2>Ingrédients réels disponibles</h2><div class="rule"></div><span class="meta">${esc(
        convective.available_count || 0
      )}/${esc(convective.required_count || "—")}</span></div>
      <div class="comp">${fieldCards(convective.fields)}</div>
      <div class="note"><b>Règle de lecture.</b> Les champs absents restent absents. MeteoVoid ne transforme pas une tuile visuelle radar en preuve radar machine.</div>

      <div class="sec-h"><h2>Radar · OPERA ORD · Live Smoke</h2><div class="rule"></div><span class="meta">preuve machine séparée de l’affichage</span></div>
      <div class="comp">
        ${card("Radar machine", radarStack.machine_radar_confirmation ? "disponible" : "non disponible", radarStack.honest_state || radarStack.status || "", "confirmation")}
        ${card("RainViewer", radarStack.rainviewer_overlay_ready ? "overlay prêt" : "visuel seulement", radarStack.rainviewer_evidence_level || "display_only", "affichage")}
        ${card("OPERA ORD", opera.status || radarStack.opera_ord_status || "—", `liens : ${opera.data_links_count || opera.data_links || 0}`, "MeteoGate")}
        ${card("Métriques OPERA", operaMetrics.status || "—", `fichiers lisibles : ${operaMetrics.analysed_file_count || 0}`, "radar machine")}
        ${card("Radars nationaux", national.status || radarStack.national_radar_status || "—", `pays : ${national.country_count || radarStack.national_radar_country_count || 0}`, "Europe")}
        ${card("Nowcast pySTEPS", radarStack.pysteps_status || "—", "nécessite une séquence de frames radar locales", "Live Smoke")}
      </div>

      <div class="sec-h"><h2>Sources · validation · amont</h2><div class="rule"></div><span class="meta">contrôle qualité</span></div>
      <div class="comp">
        ${card("Mode données", watch.data_mode || "—", sourceSummary.primary_source || sourceSummary.data_mode || "", "sources")}
        ${card("Santé sources", n(sourceSummary.source_health_score, 3), `${sourceSummary.source_ok_count || 0} OK · ${sourceSummary.source_error_count || 0} erreurs`, "source_status")}
        ${card("Corridors amont", upstream.max_corridor_score == null ? "—" : n(upstream.max_corridor_score, 3), `${upstream.corridor_count || 0} corridors · ${upstream.region_count || 0} régions`, "upstream")}
        ${card("Validation run", validation.status || "—", `POD ${n(validation.scores && validation.scores.pod)} · CSI ${n(validation.scores && validation.scores.csi)}`, "événements vérifiés")}
        ${card("Historique", history.status || "—", `${history.stored_run_count || 0} runs stockés · ${history.evaluated_run_count || 0} évalués`, "append-only")}
        ${card("Qualité données", `${dataQuality.flagged_stations ? dataQuality.flagged_stations.length : 0} stations à revoir`, `flatline ${dataQuality.flatline_station_count || 0} · spatial ${dataQuality.spatial_incoherence_station_count || 0} · sources ${dataQuality.source_error_station_count || 0}`, "validation")}
        ${card("Bulletin 5 jours", weather.model || "best_match", weather.summary || "", "public")}
      </div>

      <div class="sec-h"><h2>Qualité et cohérence des données</h2><div class="rule"></div><span class="meta">voids · flatline · spatial</span></div>
      <div class="comp">
        ${card("Stations", dataQuality.station_count || 0, "stations analysées dans le dernier run", "qualité")}
        ${card("Flatline", dataQuality.flatline_station_count || 0, "plateaux/capteurs bloqués si le signal est disponible", "capteur")}
        ${card("Inter-stations", dataQuality.spatial_incoherence_station_count || 0, "écart anormal aux stations voisines si le signal est disponible", "spatial")}
        ${card("Sources", dataQuality.source_error_station_count || 0, "sources en erreur dans le run", "source")}
      </div>
      ${dataQuality.note ? `<p class="note">${esc(dataQuality.note)}</p>` : ""}

      <div class="sec-h"><h2>Cartes, rapports et exports disponibles</h2><div class="rule"></div><span class="meta">tout le run publié</span></div>
      ${artefactLinks(watch.artefacts)}
    `;
  }

  function ensureBlock(target, id, title) {
    if (!target || $(id)) return $(id);
    const block = document.createElement("div");
    block.id = id;
    block.className = "watch-block";
    block.innerHTML = `<div class="sec-h"><h2>${esc(title)}</h2><div class="rule"></div><span class="meta">chargement</span></div>`;
    target.appendChild(block);
    return block;
  }

  function renderAll(watch) {
    const expert = ensureBlock($("view-expert"), "alertWatchExpert", "Belgium Alert Watch");
    if (expert) expert.innerHTML = renderWatch(watch);

    const method = ensureBlock($("view-methode"), "alertWatchMethod", "Statut technique du dernier run");
    if (method) {
      method.innerHTML = `<div class="sec-h"><h2>Statut technique du dernier run</h2><div class="rule"></div><span class="meta">Belgium Alert Watch</span></div>${renderWatch(watch)}`;
    }

    const bulletin = ensureBlock($("view-bulletin"), "alertWatchBulletin", "Synthèse MeteoVoid");
    if (bulletin) {
      const latest = watch.latest || {};
      const weather = watch.weather_5days || {};
      bulletin.innerHTML = `
        <div class="sec-h"><h2>Synthèse MeteoVoid</h2><div class="rule"></div><span class="meta">dernier run publié</span></div>
        <div class="note"><b>${esc(levelLabel(latest.operational_level))}.</b> ${esc(
          latest.synthesis || weather.summary || "Aucune synthèse disponible."
        )}</div>
      `;
    }
  }

  function repairMaps() {
    const activeCarte = $("view-carte") && $("view-carte").classList.contains("active");
    const activeEurope = $("view-europe") && $("view-europe").classList.contains("active");
    requestAnimationFrame(() => {
      try {
        if (activeCarte && typeof mountMap === "function" && typeof CARTE !== "undefined") {
          mountMap(CARTE, "carteMap");
          [80, 250, 700].forEach((ms) => setTimeout(() => CARTE.map && CARTE.map.invalidateSize(true), ms));
        }
        if (activeEurope && typeof mountMap === "function" && typeof EU !== "undefined") {
          mountMap(EU, "euMap");
          [80, 250, 700].forEach((ms) => setTimeout(() => EU.map && EU.map.invalidateSize(true), ms));
        }
      } catch (err) {
        // The public page must not crash if Leaflet or external tiles are blocked.
      }
    });
  }

  function fixCountryMapLabels() {
    try {
      if (typeof PAGE !== "undefined" && PAGE.label) {
        const rail = document.querySelector("#view-carte .maprail .eyebrow");
        if (rail) rail.textContent = `${PAGE.label} · maintenant`;
        document.querySelectorAll("#view-carte .sec-h .meta, #view-heures .sec-h .meta").forEach((el) => {
          el.textContent = el.textContent.replace("Belgique", PAGE.label);
        });
      }
    } catch (err) {
      // Cosmetic only.
    }
  }

  function boot() {
    fixCountryMapLabels();
    loadWatch().then((watch) => {
      if (watch) renderAll(watch);
    });
    repairMaps();
    window.addEventListener("hashchange", () => setTimeout(repairMaps, 40));
    window.addEventListener("resize", repairMaps);
    document.querySelectorAll("#nav a").forEach((a) => a.addEventListener("click", () => setTimeout(repairMaps, 90)));
    [250, 800, 1600].forEach((ms) => setTimeout(repairMaps, ms));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
