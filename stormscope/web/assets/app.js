
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
function risk(cape,cin,li,pp,gust){cape=cape||0;cin=cin||0;li=(li==null?4:li);pp=pp||0;gust=gust||0;const charge=clamp(cape/2500),liB=clamp((4-li)/14),energy=clamp(.6*charge+.4*liB),cap=clamp(1-cin/150),trig=clamp(.55*(pp/100)+.30*cap+.15*clamp((gust-10)/25));return{r:clamp(energy*(.45+.55*trig)),energy,trig,charge,cap,liB};}
function humidex(t,td){if(t==null||td==null)return null;const e=6.11*Math.exp(5417.7530*(1/273.16-1/(273.15+td)));return t+0.5555*(e-10);}
function hxClass(h){return h==null?0:h<30?0:h<40?1:h<45?2:3;}



let DASH=null;
function gridFor(R){const g=[],b=R.bbox,st=R.step;for(let la=b.s+st/2;la<b.n;la+=st)for(let lo=b.w+st/2;lo<b.e;lo+=st)g.push([+la.toFixed(3),+lo.toFixed(3)]);return g;}
async function loadDashboard(key){const R=REGIONS[key]||REGIONS.belgium;DASH=null;
  let grid=gridFor(R);const stations=R.stations.map(s=>({name:s[0],lat:s[1],lon:s[2]}));
  const cap=Math.max(8,90-stations.length);if(grid.length>cap){const k=Math.ceil(grid.length/cap);grid=grid.filter((_,i)=>i%k===0);}
  const pts=grid.concat(stations.map(s=>[s.lat,s.lon]));
  const url="https://api.open-meteo.com/v1/forecast?latitude="+pts.map(p=>p[0]).join(",")+"&longitude="+pts.map(p=>p[1]).join(",")+"&hourly=cape,convective_inhibition,lifted_index,precipitation_probability,wind_gusts_10m,temperature_2m,dew_point_2m&forecast_days=2&timezone=auto";
  const data=await(await fetch(url,{cache:"no-store"})).json();const arr=Array.isArray(data)?data:[data];
  const t=arr[0].hourly.time,nowIso=new Date().toISOString().slice(0,13);let off=t.findIndex(x=>x.slice(0,13)>=nowIso);if(off<0)off=0;
  DASH={hours:t.slice(off,off+18),off,label:R.label,
    grid:grid.map((p,i)=>[p[0],p[1],arr[i].hourly]),
    stations:stations.map((s,i)=>({name:s.name,lat:s.lat,lon:s.lon,h:arr[grid.length+i].hourly}))};
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
  const vals=DASH.hours.map((_,i)=>aggAt(i));let pk=vals.indexOf(Math.max(...vals));
  DASH.hours.forEach((iso,i)=>{const hh=new Date(iso).toLocaleTimeString('fr-BE',{hour:'2-digit'});const v=vals[i];
    const col=document.createElement('div');col.className='col'+(i===pk?' peak':'');
    col.innerHTML=`<svg class="bolt" viewBox="0 0 24 24"><path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z"/></svg><div class="bar-track"><div class="bar-fill" style="height:0"></div></div><div class="hh">${hh}</div>`;
    bars.appendChild(col);const f=col.querySelector('.bar-fill');f.style.background=C[cls(v)];f.style.boxShadow=i===pk?`0 0 18px ${C[cls(v)]}`:'none';});
  animBars('#bars',vals);
  const pkHour=new Date(DASH.hours[pk]).toLocaleTimeString('fr-BE',{hour:'2-digit'});
  document.getElementById('hNote').innerHTML=`<span>⚡ <b>${pkHour} h</b> pic de bascule (${vals[pk].toFixed(2)})</span><span>Score = max·0.6 + moyenne·0.4 sur la grille belge</span>`;
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
    const col=document.createElement('div');col.className='col';col.innerHTML=`<svg class="bolt" viewBox="0 0 24 24"></svg><div class="bar-track"><div class="bar-fill" style="height:0"></div></div><div class="hh">${hh}</div>`;
    bars.appendChild(col);const f=col.querySelector('.bar-fill');f.style.background=C[c];});
  animBars('#heatBars',norm);
}
/* ---- Réseau ---- */
function renderNet(){const net=$('net');if(!net||!DASH)return;net.innerHTML='';
  const list=DASH.stations.map(st=>({n:st.name,r:risk(st.h.cape[DASH.off],st.h.convective_inhibition[DASH.off],st.h.lifted_index[DASH.off],st.h.precipitation_probability[DASH.off],st.h.wind_gusts_10m[DASH.off]).r})).sort((a,b)=>b.r-a.r);
  document.getElementById('netMeta').textContent=list.length+' stations · live';
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

const RV={host:"https://tilecache.rainviewer.com",radar:[],sat:[],past:0};
fetch("https://api.rainviewer.com/public/weather-maps.json",{cache:"no-store"}).then(r=>r.json()).then(d=>{RV.host=d.host||RV.host;const p=(d.radar&&d.radar.past)||[],n=(d.radar&&d.radar.nowcast)||[];RV.past=p.length;RV.radar=p.concat(n);RV.sat=(d.satellite&&d.satellite.infrared)||[];}).catch(()=>{});
function rvFrame(fr,i){if(!fr.length)return null;if(i===0)return fr[Math.max(0,RV.past-1)]||fr[fr.length-1];const fc=fr.slice(RV.past);return fc.length?fc[Math.min(fc.length-1,i-1)]:fr[fr.length-1];}

function makeMap(o){ // o: {map:null,...,ids}
  return {map:null,canvas:null,surf:null,sta:null,rad:null,sat:null,net:null,prov:null,grid:[],stations:[],hours:[],off:0,i:0,step:.34,region:o.region,play:null,booted:false,ids:o};
}
async function mapLoad(S,key){const R=REGIONS[key]||{label:"Belgique",center:[50.6,4.6],zoom:8,bbox:{w:2.55,s:49.45,e:6.35,n:51.55},step:0.34,prov:true,stations:REGIONS.belgium.stations};
  S.region=key;S.step=R.step;document.getElementById(S.ids.load).classList.add('on');
  S.map.setView(R.center,R.zoom);
  if(S.prov){S.map.removeLayer(S.prov);if(R.prov)S.prov.addTo(S.map);}
  let grid=[];for(let la=R.bbox.s+R.step/2;la<R.bbox.n;la+=R.step)for(let lo=R.bbox.w+R.step/2;lo<R.bbox.e;lo+=R.step)grid.push([+la.toFixed(3),+lo.toFixed(3)]);
  S.stations=R.stations.map(s=>({name:s[0],lat:s[1],lon:s[2]}));
  const cap=Math.max(8,90-S.stations.length);if(grid.length>cap){const k=Math.ceil(grid.length/cap);grid=grid.filter((_,i)=>i%k===0);}
  const pts=grid.concat(S.stations.map(s=>[s.lat,s.lon]));
  const url="https://api.open-meteo.com/v1/forecast?latitude="+pts.map(p=>p[0]).join(",")+"&longitude="+pts.map(p=>p[1]).join(",")+"&hourly=cape,convective_inhibition,lifted_index,precipitation_probability,wind_gusts_10m&forecast_days=2&timezone=auto";
  try{const data=await(await fetch(url,{cache:"no-store"})).json();const arr=Array.isArray(data)?data:[data];const t=arr[0].hourly.time,nowIso=new Date().toISOString().slice(0,13);let off=t.findIndex(x=>x.slice(0,13)>=nowIso);if(off<0)off=0;S.off=off;S.hours=t.slice(off,off+18);
   S.grid=grid.map((p,i)=>[p[0],p[1],arr[i].hourly]);S.stations.forEach((s,i)=>s.h=arr[grid.length+i].hourly);
   document.getElementById(S.ids.time).max=S.hours.length-1;S.i=0;document.getElementById(S.ids.time).value=0;
   mapRender(S);document.getElementById(S.ids.load).classList.remove('on');
  }catch(e){document.getElementById(S.ids.load).classList.remove('on');document.getElementById(S.ids.word).textContent="Indisponible";}
}
function sRisk(h,off,i){return risk(h.cape[off+i],h.convective_inhibition[off+i],h.lifted_index[off+i],h.precipitation_probability[off+i],h.wind_gusts_10m[off+i]).r;}
function mapRender(S){const i=S.i,d=S.ids;
  S.surf.clearLayers();
  if(document.getElementById(d.surf).checked){const hh=S.step/2;S.grid.forEach(p=>{const r=sRisk(p[2],S.off,i);L.rectangle([[p[0]-hh,p[1]-hh],[p[0]+hh,p[1]+hh]],{renderer:S.canvas,stroke:false,fillColor:C[cls(r)],fillOpacity:.10+.5*r}).addTo(S.surf);});}
  S.sta.clearLayers();
  if(document.getElementById(d.sta).checked){S.stations.forEach(s=>{const r=sRisk(s.h,S.off,i);const m=L.circleMarker([s.lat,s.lon],{renderer:S.canvas,radius:6,weight:2.5,color:C[cls(r)],fillColor:"#fff",fillOpacity:.95});m.bindTooltip("<b>"+s.name+"</b><br>bascule "+r.toFixed(2)+" · "+NAMES[cls(r)]+"<br>CAPE "+Math.round(s.h.cape[S.off+i]||0)+" · LI "+(s.h.lifted_index[S.off+i]==null?"—":s.h.lifted_index[S.off+i].toFixed(1)),{direction:"top"});m.addTo(S.sta);});}
  if(S.rad){S.map.removeLayer(S.rad);S.rad=null;}if(S.sat){S.map.removeLayer(S.sat);S.sat=null;}
  if(d.sat&&document.getElementById(d.sat)&&document.getElementById(d.sat).checked&&RV.sat.length){const f=rvFrame(RV.sat,i);if(f)S.sat=L.tileLayer(RV.host+f.path+"/256/{z}/{x}/{y}/0/0_0.png",{opacity:.5,zIndex:350}).addTo(S.map);}
  if(document.getElementById(d.rad).checked&&RV.radar.length){const f=rvFrame(RV.radar,i);if(f)S.rad=L.tileLayer(RV.host+f.path+"/256/{z}/{x}/{y}/2/1_1.png",{opacity:.62,zIndex:400}).addTo(S.map);}
  const rs=S.grid.map(p=>sRisk(p[2],S.off,i));const agg=rs.length?Math.max(...rs)*.6+rs.reduce((a,b)=>a+b,0)/rs.length*.4:0;
  document.getElementById(d.word).textContent=NAMES[cls(agg)];document.getElementById(d.word).style.color=C[cls(agg)];
  document.getElementById(d.sub).textContent="bascule "+agg.toFixed(2);
  const iso=S.hours[i];document.getElementById(d.tl).textContent=i===0?"maintenant":"+"+i+" h · "+new Date(iso).toLocaleTimeString('fr-BE',{hour:'2-digit'});
  if(d.eye)document.getElementById(d.eye).textContent=(REGIONS[S.region]?REGIONS[S.region].label:"Belgique")+" · "+(i===0?"maintenant":"+"+i+" h");
}
function mountMap(S,containerId){if(S.booted){setTimeout(()=>S.map.invalidateSize(),100);return;}S.booted=true;
  S.canvas=L.canvas({padding:.5});S.map=L.map(containerId,{zoomControl:true,preferCanvas:true,worldCopyJump:true});
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",{subdomains:"abcd",maxZoom:19,attribution:'&copy; OSM &copy; CARTO'}).addTo(S.map);
  S.surf=L.layerGroup().addTo(S.map);S.sta=L.layerGroup().addTo(S.map);S.net=L.layerGroup();
  S.prov=L.geoJSON(BE_PROV,{style:{color:'#5A6B7D',weight:1,opacity:.5,dashArray:"3 4",fill:false}});
  const d=S.ids;
  [d.surf,d.sta].forEach(id=>document.getElementById(id).addEventListener('change',()=>mapRender(S)));
  document.getElementById(d.rad).addEventListener('change',()=>mapRender(S));
  if(d.sat&&document.getElementById(d.sat))document.getElementById(d.sat).addEventListener('change',()=>mapRender(S));
  if(d.net&&document.getElementById(d.net))document.getElementById(d.net).addEventListener('change',e=>{if(e.target.checked){S.net.clearLayers();RADAR_SITES.forEach(s=>{const m=L.circleMarker([s[1],s[2]],{renderer:S.canvas,radius:5,weight:2,color:'#F2B23E',fillColor:"#fff",fillOpacity:.9});m.bindTooltip("📡 "+s[0]+" · site radar (indicatif)",{direction:"top"});m.addTo(S.net);});S.net.addTo(S.map);}else S.map.removeLayer(S.net);});
  document.getElementById(d.time).addEventListener('input',e=>{S.i=+e.target.value;mapRender(S);});
  document.getElementById(d.play).addEventListener('click',()=>{const b=document.getElementById(d.play),sl=document.getElementById(d.time);if(S.play){clearInterval(S.play);S.play=null;b.innerHTML="&#9654;";return;}b.innerHTML="&#10074;&#10074;";S.play=setInterval(()=>{S.i=(S.i+1)%(S.hours.length||1);sl.value=S.i;mapRender(S);},900);});
  if(d.region){const sel=document.getElementById(d.region);Object.entries(REGIONS).forEach(([k,v])=>{const o=document.createElement('option');o.value=k;o.textContent=v.label;sel.appendChild(o);});sel.value=S.region;sel.addEventListener('change',()=>{if(S.play){clearInterval(S.play);S.play=null;document.getElementById(d.play).innerHTML="&#9654;";}mapLoad(S,sel.value);});}
  setTimeout(()=>S.map.invalidateSize(),100);mapLoad(S,S.region);
}
const CARTE=makeMap({region:(PAGE.region||"belgium"),surf:"cL-surf",sta:"cL-sta",rad:"cL-rad",sat:"cL-sat",time:"cTime",play:"cPlay",tl:"cTl",word:"cWord",sub:"cSub",load:"cLoad"});
const EU=makeMap({region:"europe",surf:"eL-surf",sta:"eL-sta",rad:"eL-rad",net:"eL-net",time:"eTime",play:"ePlay",tl:"eTl",word:"euWord",sub:"euSub",eye:"euEye",load:"eLoad",region_sel:true});
EU.ids.region="euRegion";

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
if(PAGE.kind==='europe'||PAGE.kind==='methode'){}else loadDashboard(PAGE.region).catch(()=>{document.getElementById('vWord').textContent='HORS-LIGNE';document.getElementById('vRead').textContent='Réseau Open-Meteo injoignable — réessaie plus tard.';});
route();
