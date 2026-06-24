
const reduce=matchMedia('(prefers-reduced-motion:reduce)').matches;
const PAGE=window.MV_PAGE||{kind:'dashboard',region:'belgium',label:'Belgique',center:[50.799,4.358]};
const $=id=>document.getElementById(id);


/* clock */
function tick(){const d=new Date();document.getElementById('clock').textContent=d.toLocaleTimeString('fr-BE',{hour:'2-digit',minute:'2-digit'});}
tick();setInterval(tick,30000);

/* ---------------- lightning background ---------------- */
(function(){const cvs=document.getElementById('sky'),ctx=cvs.getContext('2d'),flash=document.getElementById('flash');let W,H,dpr,bolts=[];
 function size(){dpr=Math.min(2,devicePixelRatio||1);W=innerWidth;H=innerHeight;cvs.width=W*dpr;cvs.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);}size();addEventListener('resize',size);
 function jagged(x0){const pts=[[x0,0]];let x=x0,y=0;const end=H*(0.45+Math.random()*0.3);while(y<end){y+=14+Math.random()*30;x+=(Math.random()-0.5)*46;pts.push([x,y]);}
  const br=[];for(let i=2;i<pts.length-1;i++){if(Math.random()<0.22){let[bx,by]=pts[i];const s=[[bx,by]];const n=2+(Math.random()*3|0);for(let k=0;k<n;k++){bx+=(Math.random()-0.3)*40;by+=12+Math.random()*22;s.push([bx,by]);}br.push(s);}}return{pts,branches:br,life:1};}
 function dp(p,w,a){ctx.beginPath();ctx.moveTo(p[0][0],p[0][1]);for(let i=1;i<p.length;i++)ctx.lineTo(p[i][0],p[i][1]);ctx.lineWidth=w;ctx.globalAlpha=a;ctx.stroke();}
 function frame(){ctx.clearRect(0,0,W,H);ctx.lineCap='round';ctx.lineJoin='round';for(const b of bolts){ctx.shadowColor='#9fc6ff';ctx.shadowBlur=22;ctx.strokeStyle='rgba(116,180,255,.55)';dp(b.pts,5,b.life*.5);ctx.shadowBlur=12;ctx.strokeStyle='#eaf4ff';dp(b.pts,1.8,b.life);ctx.strokeStyle='rgba(190,220,255,.8)';b.branches.forEach(s=>dp(s,1.2,b.life*.7));b.life-=0.05;}ctx.globalAlpha=1;ctx.shadowBlur=0;bolts=bolts.filter(b=>b.life>0);requestAnimationFrame(frame);}
 function fl(s){flash.style.opacity=s;setTimeout(()=>flash.style.opacity=s*.3,80);setTimeout(()=>flash.style.opacity=0,260);}
 function strike(){bolts.push(jagged(W*(.15+Math.random()*.7)));fl(.85);if(Math.random()<.4)setTimeout(()=>bolts.push(jagged(W*(.15+Math.random()*.7))),90+Math.random()*120);}
 function loop(){const t=2600+Math.random()*5200;setTimeout(()=>{if(!document.hidden)Math.random()<.5?strike():fl(.28+Math.random()*.2);loop();},t);}
 if(!reduce){frame();setTimeout(strike,900);loop();}
})();

/* ---------------- shared model ---------------- */
const C=['#54BE96','#74B4FF','#F2B23E','#EE4F5C'],NAMES=['Stable','Latent','Transition','Bascule'];
const cls=r=>r<0.25?0:r<0.5?1:r<0.72?2:3, clamp=v=>Math.max(0,Math.min(1,v));
function numberOrNull(v){if(v==null||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null;}
function hasUsableSeries(values){const nums=(values||[]).map(numberOrNull).filter(v=>v!=null);if(!nums.length)return false;return Math.max(...nums)>0.001&&(Math.max(...nums)-Math.min(...nums)>0.002||nums.length===1);}
function risk(cape,cin,li,pp,gust){cape=cape||0;cin=cin||0;li=(li==null?4:li);pp=pp||0;gust=gust||0;const charge=clamp(cape/2500),liB=clamp((4-li)/14),energy=clamp(.6*charge+.4*liB),cap=clamp(1-cin/150),trig=clamp(.55*(pp/100)+.30*cap+.15*clamp((gust-10)/25));return{r:clamp(energy*(.45+.55*trig)),energy,trig,charge,cap,liB};}
function humidex(t,td){if(t==null||td==null)return null;const e=6.11*Math.exp(5417.7530*(1/273.16-1/(273.15+td)));return t+0.5555*(e-10);}
function hxClass(h){return h==null?0:h<30?0:h<40?1:h<45?2:3;}



let DASH=null;
const LIVE_STATE={region:null,payload:null,dashboard:null,loadedAt:null,source:null,loading:null};
function gridFor(R){const g=[],b=R.bbox,st=R.step;for(let la=b.s+st/2;la<b.n;la+=st)for(let lo=b.w+st/2;lo<b.e;lo+=st)g.push([+la.toFixed(3),+lo.toFixed(3)]);return g;}
async function getMapLivePayload(region='belgium', force=false){
  if(!window.MeteoVoidSiteApi||!window.MeteoVoidSiteApi.loadMapLiveFromSiteApi)return null;
  if(!force&&LIVE_STATE.region===region&&LIVE_STATE.payload)return LIVE_STATE.payload;
  if(LIVE_STATE.loading&&!force)return LIVE_STATE.loading;
  LIVE_STATE.loading=window.MeteoVoidSiteApi.loadMapLiveFromSiteApi('api/',region).then(payload=>{
    if(payload){LIVE_STATE.region=region;LIVE_STATE.payload=payload;LIVE_STATE.loadedAt=new Date();LIVE_STATE.source=(payload.contract==='meteovoid_country_live_v1'?'country-contract-live':'alert-watch-live');}
    return payload;
  }).finally(()=>{LIVE_STATE.loading=null;});
  return LIVE_STATE.loading;
}
function dashboardFromMapLivePayload(payload,R){
  const hours=(payload.hours||[]).slice(0,48);
  const hourScores=hours.map(h=>numberOrNull(h.score??h.max_score??h.mean_score));
  const out={
    hours:hours.map(h=>h.time||h.hour||''),
    hour_scores:hourScores,
    hour_mean_scores:hours.map(h=>numberOrNull(h.mean_score)),
    hour_max_scores:hours.map(h=>numberOrNull(h.max_score??h.score)),
    hour_severity:hours.map(h=>h.severity||'normal'),
    off:0,
    label:R.label,
    source:'alert-watch-live',
    timeline:payload.timeline||{},
    grid:[],
    stations:[]
  };
  out.grid=(payload.grid||[]).filter(p=>p.lat!=null&&p.lon!=null).map(p=>[Number(p.lat),Number(p.lon),apiHourlyFromMapItem(p,hours)]);
  out.stations=(payload.stations||[]).filter(s=>s.lat!=null&&s.lon!=null).map(s=>({name:s.name||s.station_id||'station',lat:Number(s.lat),lon:Number(s.lon),source:'alert-watch',score:s.score,h:apiHourlyFromMapItem(s,hours),signals:s.signals||[]}));
  return out;
}
function installDashboardFromMapLive(payload,R){
  DASH=dashboardFromMapLivePayload(payload,R);
  LIVE_STATE.dashboard=DASH;
  renderVeille();renderHours();renderChaleur();renderNet();renderExpert();
  return DASH;
}
async function loadDashboard(key){const R=REGIONS[key]||REGIONS.belgium;DASH=null;
  if(key==='belgium'){
    const payload=await getMapLivePayload(key,false);
    if(payload){installDashboardFromMapLive(payload,R);return;}
  }
  let grid=gridFor(R);const stations=R.stations.map(s=>({name:s[0],lat:s[1],lon:s[2]}));
  const cap=Math.max(8,90-stations.length);if(grid.length>cap){const k=Math.ceil(grid.length/cap);grid=grid.filter((_,i)=>i%k===0);}
  const pts=grid.concat(stations.map(s=>[s.lat,s.lon]));
  const url="https://api.open-meteo.com/v1/forecast?latitude="+pts.map(p=>p[0]).join(",")+"&longitude="+pts.map(p=>p[1]).join(",")+"&hourly=cape,convective_inhibition,lifted_index,precipitation_probability,wind_gusts_10m,temperature_2m,dew_point_2m&forecast_days=2&timezone=auto";
  const data=await(await fetch(url,{cache:"no-store"})).json();const arr=Array.isArray(data)?data:[data];
  const t=arr[0].hourly.time,nowIso=new Date().toISOString().slice(0,13);let off=t.findIndex(x=>x.slice(0,13)>=nowIso);if(off<0)off=0;
  DASH={hours:t.slice(off,off+18),off,label:R.label,source:'open-meteo-live',
    grid:grid.map((p,i)=>[p[0],p[1],arr[i].hourly]),
    stations:stations.map((s,i)=>({name:s.name,lat:s.lat,lon:s.lon,source:'Open-Meteo',h:arr[grid.length+i].hourly}))};
  renderVeille();renderHours();renderChaleur();renderNet();renderExpert();
}
function aggAt(i){const rs=DASH.grid.map(p=>risk(p[2].cape[DASH.off+i],p[2].convective_inhibition[DASH.off+i],p[2].lifted_index[DASH.off+i],p[2].precipitation_probability[DASH.off+i],p[2].wind_gusts_10m[DASH.off+i]).r);return rs.length?Math.max(...rs)*.6+rs.reduce((a,b)=>a+b,0)/rs.length*.4:0;}
function meanAt(key,i){const v=DASH.grid.map(p=>p[2][key][DASH.off+i]).filter(x=>x!=null);return v.length?v.reduce((a,b)=>a+b,0)/v.length:0;}

/* ---- Veille ---- */
function renderVeille(){if(!$('vWord')||!DASH)return;const rg=$('vRegion');if(rg)rg.textContent=DASH.label;const s=aggAt(0),c=cls(s);
  document.getElementById('vWord').textContent=NAMES[c].toUpperCase();
  document.getElementById('vAxis').textContent=s.toFixed(2)+" · "+NAMES[c].toLowerCase();
  // most exposed station
  const ex=DASH.stations.map(st=>({n:st.name,r:risk(st.h.cape[DASH.off],st.h.convective_inhibition[DASH.off],st.h.lifted_index[DASH.off],st.h.precipitation_probability[DASH.off],st.h.wind_gusts_10m[DASH.off]).r})).sort((a,b)=>b.r-a.r)[0];
  // peak hour
  let pk=0,pkv=0;DASH.hours.forEach((_,i)=>{const a=aggAt(i);if(a>pkv){pkv=a;pk=i;}});
  const pkHour=new Date(DASH.hours[pk]).toLocaleTimeString('fr-BE',{hour:'2-digit'});
  const tNow=Math.round(meanAt('temperature_2m',0));
  document.getElementById('vRead').innerHTML=c>=2
    ?`Ingrédients réunis : la fenêtre est ouverte. Zone la plus exposée : <em>${ex.n}</em>, pic vers <em>${pkHour}</em>. Anticipation modèle, pas confirmation radar.`
    :`L'énergie ${c>=1?'s'+"'"+'accumule sous un couvercle qui tient encore':'reste faible'}. Zone la plus exposée : <em>${ex.n}</em>${c>=1?`, pic possible vers <em>${pkHour}</em>`:''}. Anticipation, pas confirmation radar.`;
  const cur=document.getElementById('cur');cur.style.left=(s*100)+'%';
  // cross-section
  const H=422,lidY=176,top=H-(s*H*0.92);
  const rect=document.getElementById('chargeRect'),g=document.getElementById('chargeG'),dot=document.getElementById('topDot'),lit=document.getElementById('lit');
  rect.setAttribute('y',top);rect.setAttribute('height',H-top);dot.setAttribute('cy',top);g.style.transform='scaleY(0)';
  if(reduce)g.style.transform='scaleY(1)';else requestAnimationFrame(()=>{g.style.transition='transform 1.2s cubic-bezier(.2,.85,.2,1)';g.style.transform='scaleY(1)';});
  if(top<lidY){const f=()=>{lit.style.opacity='1';setTimeout(()=>lit.style.opacity='.2',90);setTimeout(()=>lit.style.opacity='.85',190);setTimeout(()=>lit.style.opacity='.25',320);};reduce?lit.style.opacity='.85':setTimeout(f,1250);}else lit.style.opacity='0';
  const hxNow=Math.round(Math.max(...DASH.stations.map(st=>humidex(st.h.temperature_2m[DASH.off],st.h.dew_point_2m[DASH.off])||0)));
  document.getElementById('vChips').innerHTML=
    `<div class="chip"><span class="k">Pic</span><span class="v mono">${pkHour} h</span></div>`+
    `<div class="chip"><span class="k">Zone</span><span class="v">${ex.n.split(' / ')[0]}</span></div>`+
    `<div class="chip"><span class="k">Température</span><span class="v mono">${tNow} °C</span></div>`+
    `<div class="chip"><span class="k">Humidex</span><span class="v mono">${hxNow}</span></div>`;
}
/* ---- Heures ---- */
function renderHours(){const bars=$('bars');if(!bars||!DASH)return;bars.innerHTML='';
  const gridVals=DASH.hours.map((_,i)=>aggAt(i));
  const vals=hasUsableSeries(DASH.hour_scores)?DASH.hour_scores.map(v=>clamp(numberOrNull(v)||0)):gridVals;
  let pk=vals.indexOf(Math.max(...vals));
  DASH.hours.forEach((iso,i)=>{const hh=new Date(iso).toLocaleTimeString('fr-BE',{hour:'2-digit'});const v=vals[i]??0;
    const col=document.createElement('div');col.className='col'+(i===pk?' peak':'');
    col.title=`${hh} h · score ${Number(v).toFixed(2)} · ${sourceText(DASH)}`;
    col.innerHTML=`<svg class="bolt" viewBox="0 0 24 24"><path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z"/></svg><div class="bar-track"><div class="bar-fill" style="height:0"></div></div><div class="hh">${hh}</div>`;
    bars.appendChild(col);const f=col.querySelector('.bar-fill');f.style.background=C[cls(v)];f.style.boxShadow=i===pk?`0 0 18px ${C[cls(v)]}`:'none';});
  animBars('#bars',vals);
  const pkHour=new Date(DASH.hours[pk]).toLocaleTimeString('fr-BE',{hour:'2-digit'});
  const mode=hasUsableSeries(DASH.hour_scores)?'série horaire Alert Watch':'agrégation de la grille affichée';
  document.getElementById('hNote').innerHTML=`<span>⚡ <b>${pkHour} h</b> pic de bascule (${vals[pk].toFixed(2)})</span><span>${mode} · ${sourceText(DASH)}</span>`;
}
function animBars(sel,vals){const f=document.querySelectorAll(sel+' .bar-fill');f.forEach((el,i)=>{el.style.height='0';requestAnimationFrame(()=>setTimeout(()=>el.style.height=(vals[i]*100)+'%',60+i*34));});}
/* ---- Chaleur ---- */
function renderChaleur(){if(!$('hxBig')||!DASH)return;
  const hxByHour=DASH.hours.map((_,i)=>Math.max(...DASH.stations.map(st=>humidex(st.h.temperature_2m[DASH.off+i],st.h.dew_point_2m[DASH.off+i])||0)));
  const mx=Math.round(Math.max(...hxByHour)),mc=hxClass(mx);
  document.getElementById('hxBig').textContent=mx;document.getElementById('hxBig').style.color=C[mc];
  const labels=['Confort','Inconfort','Forte gêne','Danger'];const cmf=document.getElementById('hxCmf');
  cmf.textContent=labels[mc];cmf.style.color=C[mc];cmf.style.borderColor=C[mc];
  document.getElementById('hxSub').textContent='Humidex = ressenti combinant température et humidité.';
  const bars=document.getElementById('heatBars');bars.innerHTML='';const norm=hxByHour.map(h=>clamp((h-18)/32));
  DASH.hours.forEach((iso,i)=>{const hh=new Date(iso).toLocaleTimeString('fr-BE',{hour:'2-digit'});const c=hxClass(hxByHour[i]);
    const col=document.createElement('div');col.className='col';col.title=`${hh} h · humidex ${Math.round(hxByHour[i]||0)} · ${sourceText(DASH)}`;col.innerHTML=`<svg class="bolt" viewBox="0 0 24 24"></svg><div class="bar-track"><div class="bar-fill" style="height:0"></div></div><div class="hh">${hh}</div>`;
    bars.appendChild(col);const f=col.querySelector('.bar-fill');f.style.background=C[c];});
  animBars('#heatBars',norm);
}
/* ---- Réseau ---- */
function renderNet(){const net=$('net');if(!net||!DASH)return;net.innerHTML='';
  const off=DASH.off||0,idx=0;
  const list=(DASH.stations||[]).map(st=>({n:st.name,r:stationRiskValue(st,off,idx)})).sort((a,b)=>b.r-a.r);
  const meta=document.getElementById('netMeta');
  if(meta)meta.textContent=list.length+' stations · '+sourceText(DASH);
  list.forEach(d=>{const c=cls(d.r);const el=document.createElement('div');el.className='det';
    el.innerHTML=`<span class="dot" style="background:${C[c]};box-shadow:0 0 10px ${C[c]}"></span><div><div class="nm">${d.n}</div><div class="lv">${NAMES[c]}</div></div><div class="sc">${d.r.toFixed(2)}</div>`;net.appendChild(el);});
}
/* ---- Expert ---- */
function renderExpert(){if(!$('comp')||!DASH)return;const i=0;const cape=meanAt('cape',i),cin=meanAt('convective_inhibition',i),li=meanAt('lifted_index',i),pp=meanAt('precipitation_probability',i),gust=meanAt('wind_gusts_10m',i);
  const R=risk(cape,cin,li,pp,gust);
  const comps=[
    ['Charge convective',clamp(cape/2500),`CAPE moyen ${Math.round(cape)} J/kg`,'énergie disponible'],
    ['Couvercle (inhibition)',clamp(cin/150),`CIN moyen ${Math.round(cin)} J/kg`,'plus haut = mieux retenu'],
    ['Soulèvement',R.liB,`LI ${li.toFixed(1)}`,'< 0 = instable'],
    ['Déclencheur',clamp(pp/100),`pluie ${Math.round(pp)} %`,'forçage de déclenchement'],
    ['Organisation',clamp((gust-10)/35),`rafales ${Math.round(gust)} km/h`,'structuration possible'],
    ['Signal de bascule',R.r,`${R.r.toFixed(2)} · ${NAMES[cls(R.r)]}`,'combinaison des composantes']];
  const el=document.getElementById('comp');el.innerHTML='';
  comps.forEach(([nm,v,sc,tx])=>{const c=cls(v);const d=document.createElement('div');d.className='cmp';
    d.innerHTML=`<div class="top"><span class="nm">${nm}</span><span class="sc" style="color:${C[c]}">${v.toFixed(2)}</span></div><div class="meter"><i style="width:0;background:${C[c]}"></i></div><div class="tx">${sc}</div><div class="tag">${tx}</div>`;
    el.appendChild(d);requestAnimationFrame(()=>setTimeout(()=>d.querySelector('i').style.width=(v*100)+'%',80));});
}

/* ---------------- bulletin ---------------- */
let BULL=null;
function wcat(c){if(c<=1)return'clear';if(c===2)return'partly';if(c===3)return'cloud';if(c===45||c===48)return'fog';if(c>=95)return'storm';if((c>=71&&c<=77)||c===85||c===86)return'snow';return'rain';}
function wicon(c){const k=wcat(c),A='#F2B23E',B='#8395B0',R='#74B4FF',S='#EE4F5C';
 const sun=`<circle cx="12" cy="12" r="5" fill="${A}"/>`+[0,45,90,135,180,225,270,315].map(a=>{const r=a*Math.PI/180,x1=12+Math.cos(r)*8,y1=12+Math.sin(r)*8,x2=12+Math.cos(r)*10.5,y2=12+Math.sin(r)*10.5;return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${A}" stroke-width="1.6" stroke-linecap="round"/>`;}).join('');
 const cloud=`<path d="M7 17a4 4 0 0 1 .4-8 5 5 0 0 1 9.5 1.2A3.4 3.4 0 0 1 17 17Z" fill="${B}"/>`;
 const drops=`<line x1="9" y1="18" x2="8" y2="21" stroke="${R}" stroke-width="1.8" stroke-linecap="round"/><line x1="13" y1="18" x2="12" y2="21" stroke="${R}" stroke-width="1.8" stroke-linecap="round"/>`;
 const boltp=`<path d="M13 14l-4 6h3l-1 4 5-7h-3l1-3z" fill="${S}"/>`;
 let body;
 if(k==='clear')body=sun;
 else if(k==='partly')body=`<g transform="translate(2,-3) scale(.72)">${sun}</g>`+cloud;
 else if(k==='cloud'||k==='fog')body=cloud;
 else if(k==='storm')body=cloud+boltp;
 else if(k==='snow')body=cloud+`<text x="12" y="22" font-size="7" fill="${R}" text-anchor="middle">*</text>`;
 else body=cloud+drops;
 return `<svg viewBox="0 0 24 24" width="100%" height="100%" style="max-width:42px;max-height:42px">${body}</svg>`;}
async function ensureBulletin(){if(BULL){renderBulletin();return;}await loadBulletin();}
async function loadBulletin(){
 const url="https://api.open-meteo.com/v1/forecast?latitude="+(PAGE.center?PAGE.center[0]:50.799)+"&longitude="+(PAGE.center?PAGE.center[1]:4.358)+"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,sunshine_duration&hourly=temperature_2m,precipitation_probability,weather_code,cape,convective_inhibition,lifted_index,wind_gusts_10m&forecast_days=14&timezone=auto";
 try{const d=await(await fetch(url,{cache:"no-store"})).json();const dayRisk={};
  d.hourly.time.forEach((t,i)=>{const day=t.slice(0,10);const r=risk(d.hourly.cape[i],d.hourly.convective_inhibition[i],d.hourly.lifted_index[i],d.hourly.precipitation_probability[i],d.hourly.wind_gusts_10m[i]).r;if(!(day in dayRisk)||r>dayRisk[day])dayRisk[day]=r;});
  BULL={d,dayRisk};renderBulletin();
 }catch(e){document.getElementById('bullParts').innerHTML='<div class="part">indices indisponibles</div>';}}
function hIdx(date,hh){return BULL.d.hourly.time.indexOf(date+'T'+hh+':00');}
function dayRiskFor(date){return BULL.dayRisk[date]||0;}
function renderBulletin(){renderParts();renderDays();renderChart();}
function renderParts(){if(!$('bullParts'))return;const bl=$('bullLoc');if(bl)bl.textContent=(PAGE.label||'Belgique')+' · live';const d=BULL.d,today=d.daily.time[0];
 document.getElementById('bullToday').textContent="Aujourd'hui · "+new Date(today).toLocaleDateString('fr-BE',{weekday:'long',day:'2-digit',month:'2-digit'});
 const parts=[['Matinée','09'],['Après-midi','15'],['Soirée','20'],['Nuit','23']];
 document.getElementById('bullParts').innerHTML=parts.map(([lab,hh])=>{let i=hIdx(today,hh);if(i<0)i=0;const t=Math.round(d.hourly.temperature_2m[i]),pp=d.hourly.precipitation_probability[i]||0,wc=d.hourly.weather_code[i];
  return `<div class="part"><div class="pl">${lab}</div><div class="pt">${t}&deg;</div><div class="ic">${wicon(wc)}</div><div class="pp">${pp}% pluie</div></div>`;}).join('');}
function renderDays(){if(!$('bullDays'))return;const d=BULL.d;let html='';
 for(let i=1;i<d.daily.time.length;i++){const date=d.daily.time[i],dt=new Date(date);
  const lab=i===1?'demain':dt.toLocaleDateString('fr-BE',{weekday:'short'});
  const mx=Math.round(d.daily.temperature_2m_max[i]),mn=Math.round(d.daily.temperature_2m_min[i]);
  const pp=d.daily.precipitation_probability_max[i]||0,sun=Math.round((d.daily.sunshine_duration[i]||0)/3600);
  const r=dayRiskFor(date),c=cls(r);
  html+=`<div class="daycard"><div class="dl">${lab}</div><div class="dd">${dt.toLocaleDateString('fr-BE',{day:'2-digit',month:'2-digit'})}</div><div class="ic">${wicon(d.daily.weather_code[i])}</div><div class="tx"><span class="mx">${mx}&deg;</span> <span class="mn">${mn}&deg;</span></div><div class="meta2"><span>${sun} h soleil</span><span>${pp}% pluie</span></div><div class="bsc"><i style="width:${(r*100)|0}%;background:${C[c]}"></i></div></div>`;}
 document.getElementById('bullDays').innerHTML=html;}
function renderChart(){if(!$('bullChart'))return;const d=BULL.d,days=d.daily.time,n=days.length;
 const W=Math.max(760,n*62),H=360,L=26,Rr=26,top=72,bot=270;
 const mx=days.map((_,i)=>d.daily.temperature_2m_max[i]),mn=days.map((_,i)=>d.daily.temperature_2m_min[i]);
 const hi=Math.max(...mx)+2,lo=Math.min(...mn)-2,span=(hi-lo)||1;
 const slot=(W-L-Rr)/n,X=i=>L+slot*(i+0.5),Y=t=>bot-(t-lo)/span*(bot-top);
 const line=(a,col)=>`<polyline fill="none" stroke="${col}" stroke-width="2" stroke-opacity=".5" points="${a.map((t,i)=>X(i).toFixed(1)+','+Y(t).toFixed(1)).join(' ')}"/>`;
 let dots='';
 mx.forEach((t,i)=>{dots+=`<circle cx="${X(i).toFixed(1)}" cy="${Y(t).toFixed(1)}" r="3.4" fill="${C[3]}"/><text x="${X(i).toFixed(1)}" y="${(Y(t)-9).toFixed(1)}" text-anchor="middle" font-family="JetBrains Mono" font-size="11" fill="#EAF0FA">${Math.round(t)}</text>`;});
 mn.forEach((t,i)=>{dots+=`<circle cx="${X(i).toFixed(1)}" cy="${Y(t).toFixed(1)}" r="3.4" fill="${C[1]}"/><text x="${X(i).toFixed(1)}" y="${(Y(t)+17).toFixed(1)}" text-anchor="middle" font-family="JetBrains Mono" font-size="11" fill="#8395B0">${Math.round(t)}</text>`;});
 let labels='';days.forEach((dd,i)=>{const w=new Date(dd).toLocaleDateString('fr-BE',{weekday:'short'}).replace('.','');labels+=`<text x="${X(i).toFixed(1)}" y="34" text-anchor="middle" font-family="Inter" font-size="12" fill="#8395B0">${w}</text>`;});
 let strip='';const sy=298,sh=34;days.forEach((dd,i)=>{const r=dayRiskFor(dd),c=cls(r),x=L+slot*i+3,w=slot-6;
  strip+=`<rect x="${x.toFixed(1)}" y="${sy}" width="${w.toFixed(1)}" height="${sh}" rx="5" fill="${C[c]}" fill-opacity="${(0.18+0.55*r).toFixed(2)}"/>`;
  if(c>=2)strip+=`<g transform="translate(${X(i).toFixed(1)},${sy+6})"><path d="M0 0 l-4 9 h3 l-2 9 7-12 h-4 l2-6z" fill="#fff" fill-opacity=".92"/></g>`;});
 document.getElementById('bullChart').innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMinYMin meet">${labels}${line(mx,C[3])}${line(mn,C[1])}${dots}<text x="${L}" y="294" font-family="JetBrains Mono" font-size="9" fill="#52617B">RISQUE DE BASCULE / JOUR</text>${strip}</svg>`;}

/* ---------------- maps (Carte = Belgique, Europe = régions) ---------------- */

const LIVE_REFRESH_MS={rainviewer:5*60*1000,mapFast:60*1000,mapSlow:10*60*1000,mapFallback:2*60*1000,dashboard:10*60*1000};
const RV={host:"https://tilecache.rainviewer.com",radar:[],sat:[],past:0,lastUpdate:null,lastError:null,loading:null};
async function refreshRainViewer(force=false){
  if(RV.loading&&!force)return RV.loading;
  RV.loading=fetch("https://api.rainviewer.com/public/weather-maps.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.json();}).then(d=>{
    RV.host=d.host||RV.host;
    const p=(d.radar&&d.radar.past)||[],n=(d.radar&&d.radar.nowcast)||[];
    RV.past=p.length;RV.radar=p.concat(n);RV.sat=(d.satellite&&d.satellite.infrared)||[];
    RV.lastUpdate=new Date();RV.lastError=null;
    [CARTE,EU].forEach(S=>{if(S&&S.booted)mapRender(S);});
    return RV;
  }).catch(e=>{RV.lastError=e;return RV;}).finally(()=>{RV.loading=null;});
  return RV.loading;
}
refreshRainViewer(true);setInterval(()=>refreshRainViewer(false),LIVE_REFRESH_MS.rainviewer);
function rvFrame(fr,i){if(!fr.length)return null;if(i===0)return fr[Math.max(0,RV.past-1)]||fr[fr.length-1];const fc=fr.slice(RV.past);return fc.length?fc[Math.min(fc.length-1,i-1)]:fr[fr.length-1];}
function rvTileLayer(frame,kind){
  if(!frame||!frame.path)return null;
  const tail=kind==='satellite'?'0/0_0.png':'2/1_1.png';
  return L.tileLayer(RV.host+frame.path+'/256/{z}/{x}/{y}/'+tail,{
    opacity:kind==='satellite'?.50:.62,
    zIndex:kind==='satellite'?350:400,
    tileSize:256,
    maxNativeZoom:7,
    maxZoom:12,
    updateWhenIdle:false,
    keepBuffer:3,
    crossOrigin:true
  });
}

function makeMap(o){ // o: {map:null,...,ids}
  return {map:null,canvas:null,stationRenderer:null,surf:null,sta:null,rad:null,sat:null,net:null,prov:null,grid:[],stations:[],hours:[],off:0,i:0,step:.18,region:o.region,play:null,refresh:null,booted:false,ids:o,source:'pending',lastMapRefresh:null};
}
function defaultBelgiumRegion(){return {label:"Belgique",center:[50.6,4.6],zoom:8,bbox:{w:2.55,s:49.45,e:6.35,n:51.55},step:0.18,prov:true,stations:[["Uccle / Bruxelles",50.799,4.358],["Jodoigne",50.724,4.87],["Namur",50.467,4.872],["Liège",50.633,5.58],["Charleroi",50.411,4.445],["Mons",50.454,3.957],["Gand",51.054,3.717],["Anvers",51.219,4.403],["Hasselt",50.931,5.333],["Arlon",49.683,5.817]]};}
function safeRegions(){return (typeof REGIONS!=="undefined"&&REGIONS&&REGIONS.belgium)?REGIONS:{belgium:defaultBelgiumRegion()};}
function safeRegion(key){const regs=safeRegions();return regs[key]||regs.belgium||defaultBelgiumRegion();}
function safeProvinceGeoJson(){return (typeof BE_PROV!=="undefined"&&BE_PROV&&BE_PROV.type)?BE_PROV:{type:"FeatureCollection",features:[]};}
function fallbackTimes(){const base=new Date();base.setMinutes(0,0,0);return Array.from({length:18},(_,i)=>new Date(base.getTime()+i*3600000).toISOString().slice(0,16));}

function mapStatus(S, word, sub, color){const d=S.ids||{};const w=document.getElementById(d.word), ss=document.getElementById(d.sub);if(w){w.textContent=word; if(color) w.style.color=color;}if(ss)ss.textContent=sub;}
function clockLabel(dt){return dt?dt.toLocaleTimeString('fr-BE',{hour:'2-digit',minute:'2-digit'}):'—';}
function ageLabel(dt){if(!dt)return 'âge inconnu';const m=Math.max(0,Math.round((Date.now()-dt.getTime())/60000));return m<1?'à jour':m+' min';}
function sourceText(S){return S.source==='alert-watch-live'?'Alert Watch live':S.source==='country-contract-live'?'Contrat pays live':S.source==='open-meteo-live'?'Open-Meteo live':S.source==='local-fallback'?'fallback local':S.source==='emergency-fallback'?'repli local':S.source||'source en attente';}
function mapFreshness(S){const parts=[sourceText(S)];if(S.lastMapRefresh)parts.push('maj '+clockLabel(S.lastMapRefresh),ageLabel(S.lastMapRefresh));if(RV.lastUpdate)parts.push('radar '+clockLabel(RV.lastUpdate));return parts.join(' · ');}

function mapPlayLabel(S,i){
  const forecast=(S.source==='alert-watch-live'||S.source==='country-contract-live')?'prévision modèle':(S.source==='open-meteo-live'?'prévision Open-Meteo':'simulation locale');
  const radarInfo=RV.radar.length?(i===0?'radar observé':'radar/nowcast court terme séparé'):'radar indisponible';
  return forecast+' · '+radarInfo;
}
function projectPoint(lat, lon, bbox, width, height){const x=((lon-bbox.w)/(bbox.e-bbox.w))*width;const y=(1-((lat-bbox.s)/(bbox.n-bbox.s)))*height;return [Math.max(0,Math.min(width,x)),Math.max(0,Math.min(height,y))];}
function riskColor(v){return C[cls(v||0)];}
function buildStaticMapSvg(S, R){const w=1000,h=520,b=R.bbox||defaultBelgiumRegion().bbox;let rects='',dots='',prov='';const grid=S.grid&&S.grid.length?S.grid:[];grid.forEach(p=>{const hh=(R.step||S.step||0.34)/2;const a=projectPoint(p[0]-hh,p[1]-hh,b,w,h),c=projectPoint(p[0]+hh,p[1]+hh,b,w,h);const x=Math.min(a[0],c[0]),y=Math.min(a[1],c[1]),rw=Math.abs(c[0]-a[0]),rh=Math.abs(c[1]-a[1]);let rr=0;try{rr=sRisk(p[2],S.off||0,S.i||0);}catch(e){rr=.24;}rects+=`<rect class="mf-grid" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(4,rw).toFixed(1)}" height="${Math.max(4,rh).toFixed(1)}" fill="${riskColor(rr)}"/>`;});
if(R.prov&&typeof BE_PROV!=='undefined'&&BE_PROV&&BE_PROV.features){BE_PROV.features.forEach(f=>{const rings=((f.geometry||{}).coordinates||[])[0]||[];if(!rings.length)return;const pts=rings.map(pt=>projectPoint(pt[1],pt[0],b,w,h).map(v=>v.toFixed(1)).join(',')).join(' ');prov+=`<polyline class="mf-province" points="${pts}"/>`;});}
(S.stations||[]).forEach(st=>{const q=projectPoint(st.lat,st.lon,b,w,h);let rr=.24;try{rr=sRisk(st.h,S.off||0,S.i||0);}catch(e){}dots+=`<circle class="mf-station" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="5.5" stroke="${riskColor(rr)}"/><text class="mf-label" x="${(q[0]+9).toFixed(1)}" y="${(q[1]-7).toFixed(1)}">${String(st.name||'station').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]))}</text>`;});
return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet"><defs><radialGradient id="mfGlow" cx="50%" cy="45%" r="70%"><stop offset="0" stop-color="#17304f"/><stop offset="1" stop-color="#07101f"/></radialGradient></defs><rect width="${w}" height="${h}" fill="url(#mfGlow)"/>${rects}${prov}${dots}<text class="mf-watermark" x="22" y="36">METEOVOID · CARTE LOCALE DE SECOURS</text></svg>`;}
function ensureStaticMapFallback(S, containerId, R){const box=document.getElementById(containerId)?.closest('.mapbox');if(!box)return;let el=box.querySelector('.map-static-fallback');if(!el){el=document.createElement('div');el.className='map-static-fallback';box.insertBefore(el,box.firstChild);}S.fallbackEl=el;if(R)el.innerHTML=buildStaticMapSvg(S,R);}
function markLeafletReady(S){const box=S.map&&S.map.getContainer()?S.map.getContainer().closest('.mapbox'):null;if(box)box.classList.add('leaflet-ready');}

function fallbackHourly(lat,lon,times){const phase=((lat*7+lon*11)%6)/6;const cape=[],cin=[],li=[],pp=[],gust=[];times.forEach((_,i)=>{const wave=(Math.sin((i/17+phase)*Math.PI*2)+1)/2;const pulse=(Math.sin((i/8+phase)*Math.PI)+1)/2;cape.push(Math.round(80+900*wave));cin.push(Math.round(35+45*(1-pulse)));li.push(+(3.5-5.5*wave).toFixed(1));pp.push(Math.round(10+45*pulse));gust.push(Math.round(18+24*wave));});return{time:times,cape,convective_inhibition:cin,lifted_index:li,precipitation_probability:pp,wind_gusts_10m:gust};}
function seedMapFallback(S,grid,stations,label){const times=fallbackTimes();S.off=0;S.hours=times;S.grid=grid.map(p=>[p[0],p[1],fallbackHourly(p[0],p[1],times)]);S.stations=stations.map(s=>({name:s.name,lat:s.lat,lon:s.lon,h:fallbackHourly(s.lat,s.lon,times)}));S.source=label||'local-fallback';const sl=document.getElementById(S.ids.time);if(sl){sl.max=times.length-1;sl.value=0;}S.i=0;}
function apiSeries(values, fallback, n){const arr=Array.isArray(values)?values:[];const out=[];for(let i=0;i<n;i++){const v=arr[i];out.push(v==null?fallback:Number(v));}return out;}
function apiConstant(value,n){return Array.from({length:n},()=>value==null?null:Number(value));}
function itemSeries(item,n,names,fallback){const hourly=item&&item.hourly?item.hourly:{};for(const name of names){if(Array.isArray(hourly[name]))return apiSeries(hourly[name],fallback,n);if(Array.isArray(item[name]))return apiSeries(item[name],fallback,n);}return apiConstant(fallback,n);}
function apiHourlyFromMapItem(item,hours){const n=Math.max(hours.length,1);const score=Number(item.score||0);return{time:hours.map(h=>h.time||h.hour),meteovoid_score:itemSeries(item,n,['scores','meteovoid_score'],score),cape:itemSeries(item,n,['cape_jkg','cape'],item.cape_jkg),convective_inhibition:itemSeries(item,n,['cin_jkg','convective_inhibition'],item.cin_jkg),lifted_index:itemSeries(item,n,['lifted_index_c','lifted_index'],item.lifted_index_c),precipitation_probability:itemSeries(item,n,['precip_probability_pct','precipitation_probability'],item.precip_probability_pct),wind_gusts_10m:itemSeries(item,n,['wind_gust_ms','wind_gusts_10m'],item.wind_gust_ms),dew_point_2m:itemSeries(item,n,['dew_point_c','dew_point_2m'],item.dew_point_c),temperature_2m:itemSeries(item,n,['temperature_c','temperature_2m'],item.temperature_c)};}
function applyMapLivePayload(S,payload,R){const hours=(payload.hours||[]).slice(0,48);S.off=0;S.hours=hours.map(h=>h.time||h.hour||'');S.hour_scores=hours.map(h=>numberOrNull(h.score??h.max_score??h.mean_score));S.grid=(payload.grid||[]).filter(p=>p.lat!=null&&p.lon!=null).map(p=>[Number(p.lat),Number(p.lon),apiHourlyFromMapItem(p,hours)]);S.stations=(payload.stations||[]).filter(s=>s.lat!=null&&s.lon!=null).map(s=>({name:s.name||s.station_id||'station',lat:Number(s.lat),lon:Number(s.lon),source:'alert-watch',score:s.score,signals:s.signals||[],h:apiHourlyFromMapItem(s,hours)}));S.source=payload.contract==='meteovoid_country_live_v1'?'country-contract-live':'alert-watch-live';S.timeline=payload.timeline||{};S.lastMapRefresh=new Date();const sl=document.getElementById(S.ids.time);if(sl){sl.max=Math.max(S.hours.length-1,0);sl.value=0;}S.i=0;ensureStaticMapFallback(S,S.ids.eye?'euMap':'carteMap',R);mapRender(S);if(S===CARTE){installDashboardFromMapLive(payload,R);}return S.grid.length>0||S.stations.length>0;}
async function trySiteApiMap(S,key,R){const payload=await getMapLivePayload(key,false);if(!payload)return false;return applyMapLivePayload(S,payload,R);}

async function fetchJsonWithTimeout(url,ms){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),ms);try{const r=await fetch(url,{cache:"no-store",signal:controller.signal});if(!r.ok)throw new Error("HTTP "+r.status);return await r.json();}finally{clearTimeout(timer);}}
function mapPointCap(R,stationCount){
  const label=(R.label||'').toLowerCase();
  if(label.includes('belgique'))return 260;
  if(label.includes('pays-bas')||label.includes('suisse')||label.includes('autriche')||label.includes('danemark'))return Math.max(70,120-stationCount);
  return Math.max(8,90-stationCount);
}
function scheduleMapAutoRefresh(S,key){
  if(S.refresh)clearTimeout(S.refresh);
  if(!S.booted)return;
  const delay=(S.source==='alert-watch-live'||S.source==='country-contract-live')?LIVE_REFRESH_MS.mapFast:(S.source==='open-meteo-live'?LIVE_REFRESH_MS.mapSlow:LIVE_REFRESH_MS.mapFallback);
  S.refresh=setTimeout(()=>{
    if(document.hidden){scheduleMapAutoRefresh(S,key);return;}
    mapLoad(S,key,{silent:true,preferSiteOnly:S.source==='alert-watch-live'||S.source==='country-contract-live'}).catch(()=>scheduleMapAutoRefresh(S,key));
  },delay);
}
async function mapLoad(S,key,opts={}){let R=safeRegion(key);const silent=!!opts.silent;const containerId=S.ids.eye?'euMap':'carteMap';
  try{
    R=safeRegion(key);
    S.region=key;S.step=R.step;
    if(!silent)(document.getElementById(S.ids.load)||{}).classList?.add('on');
    if(S.map&&!silent){S.map.setView(R.center,R.zoom);setTimeout(()=>S.map.invalidateSize(),30);}
    let grid=[];for(let la=R.bbox.s+R.step/2;la<R.bbox.n;la+=R.step)for(let lo=R.bbox.w+R.step/2;lo<R.bbox.e;lo+=R.step)grid.push([+la.toFixed(3),+lo.toFixed(3)]);
    const stations=R.stations.map(s=>({name:s[0],lat:s[1],lon:s[2]}));
    const cap=mapPointCap(R,stations.length);if(grid.length>cap){const k=Math.ceil(grid.length/cap);grid=grid.filter((_,i)=>i%k===0);}

    // Affichage immédiat au premier chargement : même si Leaflet, Open-Meteo
    // ou les tuiles externes bloquent, on pose une carte locale visible.
    if(!silent){
      seedMapFallback(S,grid,stations,'local-fallback');S.lastMapRefresh=new Date();
      ensureStaticMapFallback(S,containerId,R);
      mapStatus(S,'LOCAL','carte de secours active',C[1]);
      mapRender(S);
    }

    try{
      if(S.prov){S.map.removeLayer(S.prov);if(R.prov)S.prov.addTo(S.map);}
    }catch(e){/* La couche province ne doit jamais bloquer la carte. */}

    try{const siteOk=await trySiteApiMap(S,key,R);if(siteOk){return;}}catch(e){/* API du site indisponible : repli Open-Meteo. */}
    if(silent&&opts.preferSiteOnly&&S.grid.length){const rs=S.grid.map(p=>sRisk(p[2],S.off,S.i));const agg=rs.length?Math.max(...rs)*.6+rs.reduce((a,b)=>a+b,0)/rs.length*.4:0;mapStatus(S,NAMES[cls(agg)],'attente nouvelle donnée · '+mapFreshness(S),C[cls(agg)]);return;}

    const pts=grid.concat(stations.map(s=>[s.lat,s.lon]));
    const url="https://api.open-meteo.com/v1/forecast?latitude="+pts.map(p=>p[0]).join(",")+"&longitude="+pts.map(p=>p[1]).join(",")+"&hourly=cape,convective_inhibition,lifted_index,precipitation_probability,wind_gusts_10m,temperature_2m,dew_point_2m&forecast_days=2&timezone=auto";
    try{const data=await fetchJsonWithTimeout(url,7000);const arr=Array.isArray(data)?data:[data];if(!arr.length||!arr[0].hourly||!arr[0].hourly.time)throw new Error('Open-Meteo payload invalide');const t=arr[0].hourly.time,nowIso=new Date().toISOString().slice(0,13);let off=t.findIndex(x=>x.slice(0,13)>=nowIso);if(off<0)off=0;S.off=off;S.hours=t.slice(off,off+18);S.grid=grid.map((p,i)=>[p[0],p[1],arr[i].hourly]);S.stations=stations.map((s,i)=>({name:s.name,lat:s.lat,lon:s.lon,h:arr[grid.length+i].hourly}));S.source='open-meteo-live';S.lastMapRefresh=new Date();
     const sl=document.getElementById(S.ids.time);if(sl){sl.max=S.hours.length-1;sl.value=0;}S.i=0;ensureStaticMapFallback(S,containerId,R);mapRender(S);
    }catch(e){if(!silent||!S.grid.length){S.source='local-fallback';S.lastMapRefresh=S.lastMapRefresh||new Date();ensureStaticMapFallback(S,containerId,R);mapRender(S);}else{mapStatus(S,'LIVE',mapFreshness(S)+' · refresh en attente',C[1]);}}
  }catch(e){
    const R2=safeRegion(key),cid=S.ids.eye?'euMap':'carteMap';
    if(!silent||!S.grid.length){seedMapFallback(S,gridFor(R2).slice(0,24),(R2.stations||[]).map(s=>({name:s[0],lat:s[1],lon:s[2]})),'emergency-fallback');S.lastMapRefresh=new Date();ensureStaticMapFallback(S,cid,R2);mapStatus(S,'LOCAL','repli visuel actif',C[1]);}
  }finally{
    if(!silent)(document.getElementById(S.ids.load)||{}).classList?.remove('on');
    if(S.map)setTimeout(()=>S.map.invalidateSize(),80);
    scheduleMapAutoRefresh(S,key);
  }
}
function sRisk(h,off,i){if(h&&Array.isArray(h.meteovoid_score)){const v=h.meteovoid_score[off+i];if(v!=null&&!Number.isNaN(Number(v)))return clamp(Number(v));}return risk(h.cape[off+i],h.convective_inhibition[off+i],h.lifted_index[off+i],h.precipitation_probability[off+i],h.wind_gusts_10m[off+i]).r;}
function arrVal(a,idx){return Array.isArray(a)?a[idx]:null;}
function stationRiskValue(st,off,i){try{return sRisk(st.h,off||0,i||0);}catch(e){return clamp(Number(st.score||0));}}
function stationSourceLabel(st){return st.source==='alert-watch'?'Alert Watch':(st.source||'Open-Meteo');}
function fmtNum(v,digits,suffix){if(v==null||Number.isNaN(Number(v)))return '—';return Number(v).toFixed(digits)+(suffix||'');}
function stationPopupHtml(st,r,off,i){const idx=(off||0)+(i||0),h=st.h||{},c=cls(r);return `<div class="mv-station-popup"><div class="mv-sp-title">${String(st.name||'station').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]))}</div><div class="mv-sp-state" style="color:${C[c]}">${NAMES[c]} · ${r.toFixed(2)}</div><div class="mv-sp-grid"><span>CAPE</span><b>${fmtNum(arrVal(h.cape,idx),0,' J/kg')}</b><span>CIN</span><b>${fmtNum(arrVal(h.convective_inhibition,idx),0,'')}</b><span>LI</span><b>${fmtNum(arrVal(h.lifted_index,idx),1,'')}</b><span>Rafales</span><b>${fmtNum(arrVal(h.wind_gusts_10m,idx),0,'')}</b></div><div class="mv-sp-src">${stationSourceLabel(st)}</div></div>`;}
function addStationMarker(S,st,r,i){const c=cls(r),col=C[c];const marker=L.circleMarker([st.lat,st.lon],{renderer:S.stationRenderer||S.canvas,pane:'mvStationsPane',interactive:true,bubblingMouseEvents:false,radius:c>=2?8:7,weight:2.4,color:'#EAF0FA',opacity:.96,fillColor:col,fillOpacity:.94,className:'mv-station-marker'});marker.bindTooltip('<b>'+st.name+'</b><br>bascule '+r.toFixed(2)+' · '+NAMES[c],{direction:'top',sticky:true});marker.bindPopup(stationPopupHtml(st,r,S.off,i),{maxWidth:260,closeButton:true});marker.on('mouseover',()=>{try{marker.setStyle({radius:c>=2?10:9,weight:3.2});marker.bringToFront();}catch(e){}});marker.on('mouseout',()=>{try{marker.setStyle({radius:c>=2?8:7,weight:2.4});}catch(e){}});marker.addTo(S.sta);return marker;}
function hexToRgb(h){h=h.replace('#','');return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16)];}
const RGB=C.map(hexToRgb);
function mix(a,b,t){return Math.round(a+(b-a)*t);}
function rampColor(v,a){v=clamp(v||0);const x=v*(RGB.length-1),i=Math.min(RGB.length-2,Math.floor(x)),t=x-i;const A=RGB[i],B=RGB[i+1];return `rgba(${mix(A[0],B[0],t)},${mix(A[1],B[1],t)},${mix(A[2],B[2],t)},${a})`;}
function makeRiskSurfaceLayer(S){return new (L.Layer.extend({
  initialize:function(){this._S=S;},
  onAdd:function(map){this._map=map;this._canvas=L.DomUtil.create('canvas','mv-risk-canvas');this._canvas.style.position='absolute';this._canvas.style.pointerEvents='none';const pane=map.getPane('mvSurfacePane')||map.getPanes().overlayPane;pane.appendChild(this._canvas);map.on('moveend zoomend resize viewreset',this._reset,this);this._reset();},
  onRemove:function(map){map.off('moveend zoomend resize viewreset',this._reset,this);if(this._canvas&&this._canvas.parentNode)this._canvas.parentNode.removeChild(this._canvas);},
  _reset:function(){const map=this._map,S=this._S;if(!map||!S.grid||!S.grid.length)return;const size=map.getSize(),topLeft=map.containerPointToLayerPoint([0,0]),dpr=Math.min(2,window.devicePixelRatio||1);L.DomUtil.setPosition(this._canvas,topLeft);this._canvas.style.width=size.x+'px';this._canvas.style.height=size.y+'px';this._canvas.width=Math.max(1,Math.round(size.x*dpr));this._canvas.height=Math.max(1,Math.round(size.y*dpr));this._draw(size,dpr);},
  _draw:function(size,dpr){const map=this._map,S=this._S,idx=S.i||0,off=S.off||0;const samples=[];(S.grid||[]).forEach(p=>{try{samples.push({lat:p[0],lon:p[1],v:sRisk(p[2],off,idx),w:1});}catch(e){}});(S.stations||[]).forEach(st=>{try{samples.push({lat:st.lat,lon:st.lon,v:sRisk(st.h,off,idx),w:.65});}catch(e){}});if(!samples.length)return;const scale=size.x>900?7:6,ow=Math.max(1,Math.ceil(size.x/scale)),oh=Math.max(1,Math.ceil(size.y/scale));const tmp=document.createElement('canvas');tmp.width=ow;tmp.height=oh;const tctx=tmp.getContext('2d');for(let y=0;y<oh;y++){for(let x=0;x<ow;x++){const ll=map.containerPointToLatLng([x*scale+scale/2,y*scale+scale/2]);const cos=Math.cos(ll.lat*Math.PI/180);let sw=0,sv=0;for(const p of samples){const dx=(p.lon-ll.lng)*cos,dy=p.lat-ll.lat,d2=dx*dx+dy*dy;const ww=p.w/Math.pow(d2+.012,1.18);sw+=ww;sv+=p.v*ww;}const v=sw?sv/sw:0;tctx.fillStyle=rampColor(v,.07+.46*v);tctx.fillRect(x,y,1,1);}}const ctx=this._canvas.getContext('2d');ctx.clearRect(0,0,this._canvas.width,this._canvas.height);ctx.imageSmoothingEnabled=true;ctx.globalAlpha=.96;ctx.drawImage(tmp,0,0,this._canvas.width,this._canvas.height);}
}))();}
function mapRender(S){const i=S.i,d=S.ids,R=safeRegion(S.region);
  try{
    ensureStaticMapFallback(S,d.eye?'euMap':'carteMap',R);
    S.surf.clearLayers();
    const surf=document.getElementById(d.surf),sta=document.getElementById(d.sta),rad=document.getElementById(d.rad);
    if(surf&&surf.checked&&S.grid.length){makeRiskSurfaceLayer(S).addTo(S.surf);}
    S.sta.clearLayers();
    if(sta&&sta.checked){S.stations.forEach(s=>{const r=stationRiskValue(s,S.off,i);addStationMarker(S,s,r,i);});}
    if(S.rad){S.map.removeLayer(S.rad);S.rad=null;}if(S.sat){S.map.removeLayer(S.sat);S.sat=null;}
    if(d.sat&&document.getElementById(d.sat)&&document.getElementById(d.sat).checked&&RV.sat.length){const f=rvFrame(RV.sat,i);S.sat=rvTileLayer(f,'satellite');if(S.sat)S.sat.addTo(S.map);}
    if(rad&&rad.checked&&RV.radar.length){const f=rvFrame(RV.radar,i);S.rad=rvTileLayer(f,'radar');if(S.rad)S.rad.addTo(S.map);}
    const rs=S.grid.map(p=>sRisk(p[2],S.off,i));const agg=rs.length?Math.max(...rs)*.6+rs.reduce((a,b)=>a+b,0)/rs.length*.4:0;
    mapStatus(S,NAMES[cls(agg)],'bascule '+agg.toFixed(2)+' · '+mapFreshness(S)+' · '+mapPlayLabel(S,i),C[cls(agg)]);
    const iso=S.hours[i];const tl=document.getElementById(d.tl);if(tl){const hourLabel=i===0?'maintenant':'+'+i+' h · '+new Date(iso).toLocaleTimeString('fr-BE',{hour:'2-digit'});tl.textContent=hourLabel+' · '+mapPlayLabel(S,i);}
    if(d.eye)document.getElementById(d.eye).textContent=(safeRegion(S.region).label||'Belgique')+' · '+(i===0?'maintenant':'+'+i+' h');
    markLeafletReady(S);
  }catch(e){
    ensureStaticMapFallback(S,d.eye?'euMap':'carteMap',R);
    mapStatus(S,'LOCAL','repli visuel actif',C[1]);
  }
}
function mountMap(S,containerId){const R=safeRegion(S.region);ensureStaticMapFallback(S,containerId,R);
  if(S.booted){setTimeout(()=>{if(S.map)S.map.invalidateSize();mapRender(S);},100);return;}S.booted=true;
  if(typeof L==='undefined'){mapStatus(S,'LOCAL','Leaflet indisponible · repli visuel actif',C[1]);return;}
  try{
    S.canvas=L.canvas({padding:.5});S.map=L.map(containerId,{zoomControl:true,preferCanvas:true,worldCopyJump:true,maxZoom:12,zoomSnap:.25,wheelPxPerZoomLevel:90});
    if(!S.map.getPane('mvSurfacePane')){S.map.createPane('mvSurfacePane');S.map.getPane('mvSurfacePane').style.zIndex=420;S.map.getPane('mvSurfacePane').style.pointerEvents='none';}
    if(!S.map.getPane('mvStationsPane')){S.map.createPane('mvStationsPane');S.map.getPane('mvStationsPane').style.zIndex=760;S.map.getPane('mvStationsPane').style.pointerEvents='auto';}
    S.stationRenderer=L.svg({pane:'mvStationsPane',padding:.5});
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,opacity:.36,attribution:'&copy; OpenStreetMap'}).addTo(S.map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:19,attribution:'&copy; OSM &copy; CARTO'}).addTo(S.map);
    S.surf=L.layerGroup().addTo(S.map);S.sta=L.layerGroup().addTo(S.map);S.net=L.layerGroup();
    S.prov=L.geoJSON(safeProvinceGeoJson(),{style:{color:'#7B8EA8',weight:1.4,opacity:.75,dashArray:'3 4',fill:false}});
    const d=S.ids;
    [d.surf,d.sta].forEach(id=>{const el=document.getElementById(id);if(el)el.addEventListener('change',()=>mapRender(S));});
    const rad=document.getElementById(d.rad);if(rad)rad.addEventListener('change',()=>mapRender(S));
    if(d.sat&&document.getElementById(d.sat))document.getElementById(d.sat).addEventListener('change',()=>mapRender(S));
    if(d.net&&document.getElementById(d.net))document.getElementById(d.net).addEventListener('change',e=>{if(e.target.checked){S.net.clearLayers();RADAR_SITES.forEach(s=>{const m=L.circleMarker([s[1],s[2]],{renderer:S.canvas,radius:5,weight:2,color:'#F2B23E',fillColor:'#fff',fillOpacity:.9});m.bindTooltip('📡 '+s[0]+' · site radar (indicatif)',{direction:'top'});m.addTo(S.net);});S.net.addTo(S.map);}else S.map.removeLayer(S.net);});
    const time=document.getElementById(d.time);if(time)time.addEventListener('input',e=>{S.i=+e.target.value;mapRender(S);});
    const play=document.getElementById(d.play);if(play)play.addEventListener('click',()=>{const b=document.getElementById(d.play),sl=document.getElementById(d.time);if(S.play){clearInterval(S.play);S.play=null;b.innerHTML='&#9654;';return;}b.innerHTML='&#10074;&#10074;';S.play=setInterval(()=>{S.i=(S.i+1)%(S.hours.length||1);if(sl)sl.value=S.i;mapRender(S);},900);});
    if(d.region){const sel=document.getElementById(d.region);if(sel){Object.entries(safeRegions()).forEach(([k,v])=>{const o=document.createElement('option');o.value=k;o.textContent=v.label;sel.appendChild(o);});sel.value=S.region;sel.addEventListener('change',()=>{if(S.play){clearInterval(S.play);S.play=null;const p=document.getElementById(d.play);if(p)p.innerHTML='&#9654;';}if(S.refresh){clearTimeout(S.refresh);S.refresh=null;}mapLoad(S,sel.value);});}}
    setTimeout(()=>S.map.invalidateSize(),100);mapLoad(S,S.region);
  }catch(e){
    mapStatus(S,'LOCAL','Leaflet en erreur · repli visuel actif',C[1]);
  }
}
const CARTE=makeMap({region:(PAGE.region||"belgium"),surf:"cL-surf",sta:"cL-sta",rad:"cL-rad",sat:"cL-sat",time:"cTime",play:"cPlay",tl:"cTl",word:"cWord",sub:"cSub",load:"cLoad"});
const EU=makeMap({region:"europe",surf:"eL-surf",sta:"eL-sta",rad:"eL-rad",net:"eL-net",time:"eTime",play:"ePlay",tl:"eTl",word:"euWord",sub:"euSub",eye:"euEye",load:"eLoad",region_sel:true});
EU.ids.region="euRegion";

document.addEventListener('visibilitychange',()=>{
  if(document.hidden)return;
  refreshRainViewer(true);
  [CARTE,EU].forEach(S=>{if(S.booted)mapLoad(S,S.region,{silent:true});});
  if(PAGE.kind!=='europe'&&PAGE.kind!=='methode')loadDashboard(PAGE.region).catch(()=>{});
});

/* ---------------- router ---------------- */
const views=['veille','carte','heures','bulletin','chaleur','reseau','europe','expert','methode'];
function route(){const avail=views.filter(v=>document.getElementById('view-'+v));let h=(location.hash||'').slice(1);if(!avail.includes(h))h=avail[0]||'veille';
  avail.forEach(v=>document.getElementById('view-'+v).classList.toggle('active',v===h));
  document.querySelectorAll('#nav a').forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+h));
  if(DASH){if(h==='veille')renderVeille();if(h==='heures')renderHours();if(h==='chaleur')renderChaleur();if(h==='reseau')renderNet();if(h==='expert')renderExpert();}
  if(h==='carte')mountMap(CARTE,'carteMap');
  if(h==='europe')mountMap(EU,'euMap');
  if(h==='bulletin')ensureBulletin();
  scrollTo({top:0,behavior:'smooth'});
}
addEventListener('hashchange',route);

/* boot */
if(PAGE.kind==='europe'||PAGE.kind==='methode'){}else{loadDashboard(PAGE.region).catch(()=>{document.getElementById('vWord').textContent='HORS-LIGNE';document.getElementById('vRead').textContent='Réseau Open-Meteo injoignable — réessaie plus tard.';});setInterval(()=>{if(!document.hidden)loadDashboard(PAGE.region).catch(()=>{});},LIVE_REFRESH_MS.dashboard);}
route();

/* MeteoVoid offline/static cache + minimal a11y hardening. */
(function () {
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./sw.js").catch(() => {});
    });
  }
  window.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("button:not([aria-label])").forEach((button) => {
      const text = (button.textContent || button.id || "action").trim();
      button.setAttribute("aria-label", text || "action MeteoVoid");
    });
    document.querySelectorAll("input[type='checkbox']:not([aria-label])").forEach((input) => {
      const label = input.closest("label");
      input.setAttribute(
        "aria-label",
        (label && label.textContent ? label.textContent : input.id).trim()
      );
    });
  });
})();
