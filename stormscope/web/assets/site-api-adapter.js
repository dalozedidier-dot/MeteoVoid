/* ============================================================================
 * MeteoVoid Storm-scope — adaptateur API du site
 * ----------------------------------------------------------------------------
 * Objectif : faire consommer à l'interface les endpoints que
 * `tools/build_belgium_public_site.py` génère déjà (scores calculés côté
 * serveur, conformes à la règle no_machine_radar_data), plutôt que de
 * recalculer en direct depuis Open-Meteo.
 *
 * Stratégie : API d'abord, repli Open-Meteo si l'API est absente/vide.
 *   - En local (file://) ou hors run : pas d'api/ -> repli Open-Meteo.
 *   - Sur GitHub Pages avec un run publié : api/*.json peuplé -> API.
 *
 * Cet adaptateur N'EST PAS branché par défaut. Voir docs/INTEGRATION.md,
 * étape « Brancher l'API du site », pour l'activer (USE_SITE_API = true).
 *
 * --- CONTRATS D'ENDPOINTS (vérifiés sur build à report-dir vide ; confirmer
 *     les champs marqués (?) contre un run réel avant mise en production) ---
 *
 * api/latest.json
 *   generated_at        : string|null   (null = pas de run -> repli)
 *   model_score         : number|null   (0..1)  -> MODEL.now.score
 *   operational_level   : {key,label,class,rank}-> régime
 *   severity            : {key,label,class,rank}
 *   confidence          : {score,label,class,factors[]}
 *   window              : {start?,end?,peak?}    (?) -> fenêtre / pic
 *   score_layers        : {convective_risk_score, heat_stress_score, ...}
 *
 * api/timeline.json
 *   hours    : [{hour, score(?), class(?)}]      (?) -> MODEL.hours
 *   markers  : [{hour, kind, text}]
 *   narrative: [{hour, kind, text}]
 *
 * api/stations.json
 *   stations : [{name(?), lat(?), lon(?), score(?), class(?), level(?)}] (?)
 *   provinces: [...]
 *
 * api/heat.json
 *   max_humidex      : number|null  -> MODEL.now.humidex
 *   max_temperature_c: number|null  -> MODEL.now.tempC
 *   level            : {key,label,class,rank}
 *   peak_hour        : string
 *   timeline         : [{hour, humidex(?)}]       (?) -> MODEL.heatHours
 *   hottest          : [{name(?), humidex(?)}]     (?)
 *
 * api/europe.json
 *   page_contract = "meteovoid_europe_page_full_v3_same_design"
 *   countries(?) / simple / ...  -> contexte page Europe
 * ========================================================================== */

const CLASS_FROM_API = { calm:0, info:1, watch:2, elevated:2, high:3, danger:3 };

async function getJSON(url){
  try{ const r = await fetch(url, {cache:'no-store'}); if(!r.ok) return null; return await r.json(); }
  catch(e){ return null; }
}

/* Retourne un MODEL normalisé depuis l'API, ou null si indisponible/vide. */
async function loadModelFromSiteApi(base='api/'){
  const latest = await getJSON(base+'latest.json');
  if(!latest || latest.generated_at == null || latest.model_score == null) return null; // -> repli

  const [timeline, stations, heat] = await Promise.all([
    getJSON(base+'timeline.json'), getJSON(base+'stations.json'), getJSON(base+'heat.json')
  ]);

  const clsOf = r => r<0.25?0 : r<0.5?1 : r<0.72?2 : 3;
  const regimeName = (latest.operational_level && latest.operational_level.label) || '—';
  const classIdx = (latest.operational_level && CLASS_FROM_API[latest.operational_level.class]) ?? clsOf(latest.model_score);

  const hours = (timeline && timeline.hours || []).map(h => ({
    hour: h.hour, score: (h.score != null ? h.score : (CLASS_FROM_API[h.class] ?? 0)/3)
  }));

  const sta = (stations && stations.stations || []).map(s => ({
    name: s.name, lat: s.lat, lon: s.lon,
    score: (s.score != null ? s.score : (CLASS_FROM_API[s.class || s.level] ?? 0)/3)
  }));

  const heatHours = (heat && heat.timeline || []).map(h => ({ hour: h.hour, humidex: h.humidex }));

  return {
    source: 'site-api',
    now: {
      score: latest.model_score,
      classIdx,
      regimeName,
      tempC: heat && heat.max_temperature_c,
      humidex: heat && heat.max_humidex,
      peakHour: (latest.window && latest.window.peak) || (heat && heat.peak_hour) || '—',
      confidence: latest.confidence && latest.confidence.score
    },
    hours, stations: sta, heatHours,
    layers: latest.score_layers || {},
    raw: { latest, timeline, stations, heat },
    disclaimer: latest.disclaimer
  };
}

/* Exposé global pour app.js */
window.MeteoVoidSiteApi = { loadModelFromSiteApi, getJSON };
