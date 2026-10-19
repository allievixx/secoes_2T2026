import { loadDashboardData } from "./dashboard-data.js";

const $ = id => document.getElementById(id);
const int = value => value == null ? "–" : value.toLocaleString("pt-BR");
const pct = value => Math.round(value * 100) + "%";
const pct1 = value => (value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
const kmf = value => value.toLocaleString("pt-BR", { maximumFractionDigits: value < 10 ? 1 : 0 }) + " km";
const walk = value => {
  const minutes = Math.round(value / 5 * 60 / 5) * 5;
  return minutes < 60 ? `${Math.max(5, minutes)} min a pé` : `${Math.floor(minutes / 60)}h${minutes % 60 ? String(minutes % 60).padStart(2, "0") : ""} a pé`;
};
const UFCODE = {11:"RO",12:"AC",13:"AM",14:"RR",15:"PA",16:"AP",17:"TO",21:"MA",22:"PI",23:"CE",24:"RN",25:"PB",26:"PE",27:"AL",28:"SE",29:"BA",31:"MG",32:"ES",33:"RJ",35:"SP",41:"PR",42:"SC",43:"RS",50:"MS",51:"MT",52:"GO",53:"DF"};
const CODEOF = Object.fromEntries(Object.entries(UFCODE).map(([code, uf]) => [uf, code]));

async function fetchJSON(url, fresh = false) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(url, { signal: controller.signal, cache: fresh ? "no-store" : "default" });
    if (!response.ok) throw new Error(`Não foi possível buscar ${new URL(url, location.href).pathname} (HTTP ${response.status}).`);
    return await response.json();
  } finally { clearTimeout(timer); }
}

function initializeNavigation() {
  const navLinks = [...document.querySelectorAll(".nav a")];
  let hold = 0;
  function setNav(id) {
    for (const a of navLinks) {
      if (a.dataset.sec === id) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
  }
  navLinks.forEach(a => a.addEventListener("click", event => {
    event.preventDefault();
    const el = $(a.dataset.sec);
    if (el.tagName === "DETAILS") el.open = true;
    if (a.dataset.sec === "sec-timeline" && globalThis.allSnapshots) {
      renderTimeline(globalThis.allSnapshots);
    }
    hold = Date.now() + 1200;
    el.scrollIntoView({ behavior:"smooth", block:"start" });
    setNav(a.dataset.sec);
  }));
  document.querySelector(".logo").addEventListener("click", event => {
    event.preventDefault();
    window.scrollTo({ top:0, behavior:"smooth" });
    setNav("top");
  });
  window.addEventListener("scroll", () => requestAnimationFrame(() => {
    if (Date.now() < hold) return;
    let current = "top";
    for (const id of ["top", "sec-mapa", "sec-lista", "sec-uf", "sec-timeline", "sec-sobre"]) {
      if ($(id).getBoundingClientRect().top - 84 < innerHeight * .35) current = id;
    }
    setNav(current);
  }), { passive:true });
}

function renderTimeline(snapshots) {
  if (!snapshots || snapshots.length < 2) {
    $("timeline-charts").innerHTML = '<div class="facts" style="color:var(--muted);padding:12px">Necessário mínimo 2 cargas para comparação temporal.</div>';
    return;
  }
  
  const d3 = globalThis.d3;
  const timeLabel = snapshot => snapshot.extractedAt
    ? new Intl.DateTimeFormat("pt-BR", { hour:"2-digit", minute:"2-digit", timeZone:"America/Sao_Paulo" }).format(new Date(snapshot.extractedAt))
    : "Único";
  
  const data = snapshots.map((snapshot, idx) => {
    const T = { n:0, el:0, ap:0 };
    if (snapshot.data.g) {
      for (const g of snapshot.data.g) {
        for (const s of g.s) {
          T.n++;
          T.el += s[1] || 0;
          T.ap += s[2] || 0;
        }
      }
    }
    return {
      time: timeLabel(snapshot),
      idx,
      sections: T.n,
      voters: T.el,
      eligible: T.ap
    };
  });
  
  const container = $("timeline-charts");
  container.innerHTML = '';
  
  const metrics = [
    { key: "sections", label: "Seções que mudam de local", color: "var(--l3)" },
    { key: "voters", label: "Eleitores nelas", color: "var(--accent)" },
    { key: "eligible", label: "Aptos", color: "var(--muted)" }
  ];
  
  for (const metric of metrics) {
    const chartDiv = document.createElement("div");
    chartDiv.className = "timeline-chart";
    
    const title = document.createElement("div");
    title.className = "timeline-title";
    title.textContent = metric.label;
    chartDiv.appendChild(title);
    
    const svg = d3.create("svg")
      .attr("viewBox", [0, 0, 700, 300])
      .attr("class", "timeline-svg");
    
    const margin = { top: 20, right: 30, bottom: 30, left: 60 };
    const width = 700 - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;
    
    const x = d3.scaleLinear().domain([0, data.length - 1]).range([0, width]);
    const y = d3.scaleLinear().domain([0, d3.max(data, d => d[metric.key])]).range([height, 0]);
    
    const line = d3.line()
      .x((d, i) => x(i))
      .y(d => y(d[metric.key]));
    
    const g = svg.append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);
    
    g.append("g")
      .attr("transform", `translate(0,${height})`)
      .call(d3.axisBottom(x).tickFormat((d, i) => data[d] ? data[d].time : ""))
      .style("font-size", "12px");
    
    g.append("g")
      .call(d3.axisLeft(y))
      .style("font-size", "12px");
    
    g.append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", metric.color)
      .attr("stroke-width", 2.5)
      .attr("d", line);
    
    g.selectAll(".dot")
      .data(data)
      .enter()
      .append("circle")
      .attr("cx", (d, i) => x(i))
      .attr("cy", d => y(d[metric.key]))
      .attr("r", 4)
      .attr("fill", metric.color)
      .attr("opacity", 0.7);
    
    chartDiv.appendChild(svg.node());
    container.appendChild(chartDiv);
  }
}

function initializeDashboard(D, municipalities, states) {
  const d3 = globalThis.d3;
  const meta = D.meta;
  // Os textos da fonte já foram escapados para uso em templates HTML.
  const text = value => {
    const el = document.createElement("textarea"); el.innerHTML = value; return el.value;
  };
  const G = D.g.map((g, i) => {
    const t = { el:0, ap:0, ab:0, l:0, fv:0, ot:0, b:0, n:0 };
    for (const s of g.s) {
      ["el", "ap", "ab", "l", "fv", "ot", "b", "n"].forEach((field, j) => { t[field] += s[j + 1] || 0; });
    }
    const v = t.l + t.fv + t.ot;
    return Object.assign(g, t, { i, v, lr:v ? t.l/v : 0, fr:v ? t.fv/v : 0, ar:t.ap ? t.ab/t.ap : 0 });
  });
  const F = { far:false, longe:false };
  let WIN = "all", UF = "", SEL = null, SHOWN = 20;
  const secWin = s => s[4] == null || s[5] == null ? null : s[4] > s[5] ? "lula" : s[5] > s[4] ? "flavio" : "empate";
  const secOk = s => WIN === "all" || secWin(s) === WIN;
  const pass = (g, ignoreUF = false) => (ignoreUF || !UF || g.uf === UF) && g.s.some(secOk) && (!F.far || (g.km != null && g.km >= 2)) && (!F.longe || g.longe);
  const col = g => !g.v ? "var(--other)" : g.l > g.fv ? (g.lr-g.fr >= .3 ? "var(--l3)" : g.lr-g.fr >= .1 ? "var(--l2)" : "var(--l1)") : "var(--flavio)";
  const scope = (includeUF = true) => [includeUF && UF, WIN === "lula" ? "seções onde Lula venceu" : WIN === "flavio" ? "seções onde Flávio venceu" : "", F.far ? "mudaram 2 km ou mais" : "", F.longe ? "região longe da urna" : ""].filter(Boolean).join(" · ");

  function renderSummary() {
    const T = { n:0, el:0, ap:0, ab:0, l:0, f:0, o:0, bn:0, far:0, lon:0, lonUnknown:0, mun:new Set() };
    for (const g of G.filter(g => pass(g))) for (const s of g.s.filter(secOk)) {
      T.n++; T.el+=s[1]; T.ap+=s[2]||0; T.ab+=s[3]||0; T.l+=s[4]||0; T.f+=s[5]||0; T.o+=s[6]||0; T.bn+=(s[7]||0)+(s[8]||0);
      if (g.km != null && g.km >= 2) T.far++;
      if (g.longe) T.lon++;
      if (g.longe == null) T.lonUnknown++;
      T.mun.add(g.uf+g.ib);
    }
    const V = T.l+T.f+T.o;
    $("scope").textContent = `2º turno · ${meta.electionDate}${scope() ? " · "+scope() : ""}`;
    $("headline").textContent = `${int(T.n)} seç${T.n !== 1 ? "ões vão" : "ão vai"} votar em outro lugar no 2º turno`;
    // Metadados de configuração são inseridos como texto, não como HTML.
    $("lede").replaceChildren();
    const lead = ["São ", [int(T.el)+" eleitores"], ` em ${int(T.mun.size)} município${T.mun.size !== 1 ? "s" : ""} que vão votar em `, ["outro local"], ` no dia ${meta.electionDate}. Quem for ao mesmo lugar de ${meta.previousElectionDate} pode não encontrar a sua seção. Lista de seções alteradas no 2º turno publicada pelo TSE em ${meta.gen}.`];
    for (const piece of lead) {
      if (Array.isArray(piece)) { const b = document.createElement("b"); b.textContent = piece[0]; $("lede").append(b); }
      else $("lede").append(piece);
    }
    $("kpis").innerHTML = [
      ["hot",int(T.n),"seções mudam de local"], ["hot",int(T.el),"eleitores nelas"],
      ["",V ? pct1(T.l/V) : "–","Lula nelas no 1º turno"], ["",int(T.far),"seções mudaram 2 km ou mais"],
      ...(T.lonUnknown ? [] : [["",int(T.lon),"seções em região longe da urna"]]), ["",int(T.mun.size),"municípios"], ["",T.ap ? pct1(T.ab/T.ap) : "–","abstenção no 1º turno (Brasil: 20,8%)"],
    ].map(([c,v,l]) => `<div class="kpi ${c}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
    const parts = [["Lula",T.l,"var(--l3)"],["Flávio",T.f,"var(--flavio)"],["Outros",T.o,"var(--other)"],["Brancos e nulos",T.bn,"var(--bn)"],["Abstenção",T.ab,"var(--off)"]];
    const total = parts.reduce((sum,p) => sum+p[1],0) || 1;
    $("stack").innerHTML = parts.map(p => `<i style="width:${p[1]/total*100}%;background:${p[2]}" title="${p[0]}"></i>`).join("");
    $("keys").innerHTML = parts.map(p => `<span><i class="sw" style="background:${p[2]};border:1px solid var(--line)"></i>${p[0]} <b>${pct1(p[1]/total)}</b></span>`).join("")+`<span>dos ${int(T.ap)} aptos</span>`;
  }

  function renderUF() {
    const make = uf => ({uf,n:0,el:0,mun:new Set(),mv:0,wl:0,wf:0,we:0,l:0,f:0,o:0,ap:0,ab:0,far:0,lon:0,lonUnknown:0});
    const by = {}, tot = make("Total");
    for (const g of G.filter(g => pass(g,true))) {
      const r = by[g.uf] ||= make(g.uf);
      for (const s of g.s.filter(secOk)) for (const x of [r,tot]) {
        x.n++; x.el+=s[1]; x.l+=s[4]||0; x.f+=s[5]||0; x.o+=s[6]||0; x.ap+=s[2]||0; x.ab+=s[3]||0;
        const w=secWin(s); if(w==="lula")x.wl++; else if(w==="flavio")x.wf++; else if(w==="empate")x.we++;
        if(g.km!=null && g.km>=2)x.far++; if(g.longe)x.lon++; if(g.longe==null)x.lonUnknown++; x.mun.add(g.uf+g.ib);
      }
      r.mv++; tot.mv++;
    }
    const rows = Object.values(by).sort((a,b) => b.n-a.n);
    const cell = r => { const V=r.l+r.f+r.o; return [r.uf,int(r.n),int(r.el),int(r.mun.size),int(r.mv),int(r.wl),int(r.wf),int(r.we),V?pct1(r.l/V):"–",V?pct1(r.f/V):"–",r.ap?pct1(r.ab/r.ap):"–",int(r.far),r.lonUnknown?"–":int(r.lon)].map(v=>`<td>${v}</td>`).join(""); };
    $("ufscope").textContent = `${rows.length} estado${rows.length!==1?"s":""}${scope(false)?" · "+scope(false):""}`;
    $("uftab").innerHTML = `<thead><tr>${["UF","Seções","Eleitores","Municípios","Mudanças de local","Lula venceu","Flávio venceu","Empate","Lula %","Flávio %","Abstenção","Mudou 2 km+","Região longe"].map(v=>`<th>${v}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr data-uf="${r.uf}" class="${UF===r.uf?"on":""}">${cell(r)}</tr>`).join("")}</tbody><tfoot><tr>${cell(tot)}</tr></tfoot>`;
    document.querySelectorAll("#uftab tbody tr").forEach(tr => tr.onclick = () => { setUF(UF===tr.dataset.uf?"":tr.dataset.uf); $("top").scrollIntoView({behavior:"smooth",block:"start"}); });
  }

  // A geometria vem do IBGE; nenhum polígono fica embutido no HTML.
  const feats = municipalities.features;
  const fixPoly = p => d3.geoArea({type:"Polygon",coordinates:p}) > 2*Math.PI ? p.map(r=>r.slice().reverse()) : p;
  for (const f of [...feats,...states.features]) {
    const g=f.geometry;
    if(g?.type==="Polygon")g.coordinates=fixPoly(g.coordinates);
    else if(g?.type==="MultiPolygon")g.coordinates=g.coordinates.map(fixPoly);
  }
  const code = f => String(f.properties.codarea ?? f.properties.id);
  const svg=d3.select("#map"), W=1000, H=1000;
  svg.attr("viewBox",`0 0 ${W} ${H}`);
  const proj=d3.geoMercator().fitExtent([[10,10],[W-10,H-10]],municipalities);
  const path=d3.geoPath(proj), HAS=new Set(G.map(g=>String(g.ib)));
  const gm=svg.append("g"), gl=svg.append("g"), gp=svg.append("g");
  gm.selectAll("path.m").data(feats).join("path").attr("class",d=>"m"+(HAS.has(code(d))?" has":"")).attr("d",path);
  gm.selectAll("path.uf").data(states.features).join("path").attr("class","uf").attr("d",path);
  const P=G.map(g=>Object.assign(g,{xy:g.pf?proj([g.pf[1],g.pf[0]]):g.po?proj([g.po[1],g.po[0]]):null,xo:g.po&&g.pf&&g.km>.05?proj([g.po[1],g.po[0]]):null})).filter(g=>g.xy);
  let K=1;
  const rP=g=>Math.max(1.8,Math.sqrt(g.el)/8)/Math.pow(K,.75)*1.4, rO=()=>2/Math.pow(K,.75)*1.4;
  const tip=$("tip"), box=$("sec-mapa");
  function showTip(e,h) {
    const r=box.getBoundingClientRect(); tip.innerHTML=h; tip.hidden=false;
    let x=e.clientX-r.left+14,y=e.clientY-r.top+14;
    if(x+tip.offsetWidth>r.width-8)x=e.clientX-r.left-tip.offsetWidth-14;
    if(y+tip.offsetHeight>r.height-8)y=e.clientY-r.top-tip.offsetHeight-14;
    tip.style.left=Math.max(8,x)+"px"; tip.style.top=Math.max(8,y)+"px";
  }
  function draw() {
    const vis=P.filter(g=>pass(g)).sort((a,b)=>b.el-a.el); tip.hidden=true;
    gl.selectAll("line").data(vis.filter(g=>g.xo),g=>g.i).join("line").attr("class","mv").attr("x1",g=>g.xo[0]).attr("y1",g=>g.xo[1]).attr("x2",g=>g.xy[0]).attr("y2",g=>g.xy[1]);
    gl.selectAll("circle").data(vis.filter(g=>g.xo),g=>g.i).join("circle").attr("class","o").attr("cx",g=>g.xo[0]).attr("cy",g=>g.xo[1]).attr("r",rO);
    gp.selectAll("circle").data(vis,g=>g.i).join("circle").attr("class",g=>"p"+(SEL===g?" on":"")).attr("cx",g=>g.xy[0]).attr("cy",g=>g.xy[1]).attr("r",rP).attr("fill",col)
      .on("mousemove",(e,g)=>showTip(e,`<b>${g.m}</b> · ${g.uf} · zona ${g.z}<br>${g.o} → <b>${g.f}</b><br>${g.km!=null?`${kmf(g.km)} (${walk(g.km)})`:"distância desconhecida"} · ${g.s.length} seções, ${int(g.el)} eleitores<br>1º turno: Lula ${pct(g.lr)} · Flávio ${pct(g.fr)} · abstenção ${pct(g.ar)}`))
      .on("mouseleave",()=>tip.hidden=true).on("click",(e,g)=>pick(g,false));
  }
  const zoom=d3.zoom().scaleExtent([1,300]).filter(e=>e.type==="touchstart"?e.touches.length>1:!e.button)
    .on("zoom",e=>{for(const s of [gm,gl,gp])s.attr("transform",e.transform);K=e.transform.k;gp.selectAll("circle").attr("r",rP);gl.selectAll("circle").attr("r",rO);});
  svg.call(zoom).on("dblclick.zoom",null).style("touch-action","pan-y");
  $("zin").onclick=()=>svg.transition().duration(300).call(zoom.scaleBy,1.8);
  $("zout").onclick=()=>svg.transition().duration(300).call(zoom.scaleBy,1/1.8);
  function zoomTo(fc,pad=.85) {
    const [[x0,y0],[x1,y1]]=path.bounds(fc);
    const k=Math.min(300,pad/Math.max((x1-x0)/W,(y1-y0)/H,1e-6));
    svg.transition().duration(600).call(zoom.transform,d3.zoomIdentity.translate(W/2,H/2).scale(k).translate(-(x0+x1)/2,-(y0+y1)/2));
  }
  function zoomPts(pts) {
    const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
    const k=Math.min(40,.6/Math.max((x1-x0)/W,(y1-y0)/H,.004));
    svg.transition().duration(600).call(zoom.transform,d3.zoomIdentity.translate(W/2,H/2).scale(k).translate(-(x0+x1)/2,-(y0+y1)/2));
  }

  function renderCard() {
    if(!SEL) {
      const vis=G.filter(g=>pass(g)),t=vis.reduce((t,g)=>{for(const s of g.s.filter(secOk)){t.n++;t.el+=s[1];}return t;},{n:0,el:0});
      $("card").innerHTML=`<div class="eyebrow">${UF||"Brasil"}${scope()?" · com filtro":""}</div><h2>${int(t.n)} seç${t.n!==1?"ões":"ão"} em ${int(vis.length)} mudança${vis.length!==1?"s":""} de local</h2><div class="facts">${int(t.el)} eleitores. Toque num ponto do mapa ou numa linha da lista para ver de onde para onde a seção foi e como ela votou no 1º turno.</div>`; return;
    }
    const g=SEL;
    $("card").innerHTML=`<div><div class="eyebrow">${g.uf} · ${g.m} · zona ${g.z}</div><h2>${g.f}</h2></div>
      <span class="badge now">Muda de local no 2º turno</span>
      <div class="move"><span class="k">1º turno</span><div>${g.o}${g.eo?`<div class="addr">${g.eo}</div>`:""}</div><span class="k">2º turno</span><div><b>${g.f}</b>${g.ef?`<div class="addr">${g.ef}${g.bf?` · ${g.bf}`:""}</div>`:""}</div></div>
      <div class="facts"><span>Distância <b>${g.km!=null?kmf(g.km):"–"}</b></span>${g.km!=null?`<span>A pé <b>${walk(g.km)}</b></span>`:""}<span>Seções <b>${g.s.length}</b></span><span>Eleitores <b>${int(g.el)}</b></span><span>Região <b style="color:${g.longe?"var(--accent)":"inherit"}">${g.longe==null?"sem informação":g.longe?"longe":"perto"}</b>${g.longe==null?"":" da urna"}</span></div>
      <div><div class="eyebrow" style="margin-bottom:6px">1º turno nessas seções</div><div class="stack">${[[g.l,"var(--l3)"],[g.fv,"var(--flavio)"],[g.ot,"var(--other)"],[g.b+g.n,"var(--bn)"],[g.ab,"var(--off)"]].map(([v,c])=>`<i style="width:${g.ap?v/g.ap*100:0}%;background:${c}"></i>`).join("")}</div>
      <div class="keys" style="margin-top:6px"><span>Lula <b>${int(g.l)}</b> (${pct1(g.lr)})</span><span>Flávio <b>${int(g.fv)}</b> (${pct1(g.fr)})</span><span>Outros <b>${int(g.ot)}</b></span><span>Brancos e nulos <b>${int(g.b+g.n)}</b></span><span>Abstenção <b>${int(g.ab)}</b> (${pct1(g.ar)})</span></div></div>
      <div class="tblw"><table><thead><tr><th>Seção</th><th>Venceu</th><th>Eleitores</th><th>Lula</th><th>Flávio</th><th>Outros</th><th>Br/Nulos</th><th>Abst.</th></tr></thead><tbody>${g.s.map(s=>{
        const v=(s[4]||0)+(s[5]||0)+(s[6]||0);
        return `<tr><td>${s[0]}</td><td style="font-family:var(--f-ui);color:${secWin(s)==="lula"?"var(--accent)":"var(--muted)"}">${{lula:"Lula",flavio:"Flávio",empate:"Empate"}[secWin(s)]||"–"}</td><td>${int(s[1])}</td><td>${s[4]!=null?`${int(s[4])} <small>${v?pct(s[4]/v):""}</small>`:"–"}</td><td>${s[5]!=null?`${int(s[5])} <small>${v?pct(s[5]/v):""}</small>`:"–"}</td><td>${int(s[6])}</td><td>${s[7]!=null&&s[8]!=null?int(s[7]+s[8]):"–"}</td><td>${s[3]!=null?`${int(s[3])} <small>${s[2]?pct(s[3]/s[2]):""}</small>`:"–"}</td></tr>`;
      }).join("")}</tbody></table></div><button type="button" class="more" id="clear">Ver todas as mudanças</button>`;
    $("clear").onclick=()=>{SEL=null;draw();renderCard();};
  }

  function renderList() {
    const arr=G.filter(g=>pass(g)).sort((a,b)=>b.l-a.l);
    $("listscope").textContent=(UF||"Brasil")+" · mais votos do Lula no 1º turno primeiro";
    $("list").innerHTML=arr.length?arr.slice(0,SHOWN).map(g=>`<button type="button" class="row" data-i="${g.i}"><span class="nm">${g.m} · ${g.uf} <span style="font-weight:400;color:var(--muted)">zona ${g.z}</span></span><span class="sub">${g.o} → ${g.f}<br>${g.s.length} seç${g.s.length>1?"ões":"ão"}${WIN!=="all"?` (${g.s.filter(secOk).length} com vitória ${WIN==="lula"?"do Lula":"do Flávio"})`:""} · Lula ${pct(g.lr)} · Flávio ${pct(g.fr)} · abstenção ${pct(g.ar)}</span><span class="pc">${g.km!=null?walk(g.km):"–"}<small>${g.km!=null?kmf(g.km):"distância ?"}</small></span></button>`).join(""):'<div class="empty">Nenhuma mudança com esse filtro.</div>';
    $("more").hidden=arr.length<=SHOWN;
    $("list").querySelectorAll("[data-i]").forEach(b=>b.onclick=()=>pick(G[+b.dataset.i],true));
  }
  $("more").onclick=()=>{SHOWN+=20;renderList();};
  function render() { draw();renderList();renderCard();renderSummary();renderUF(); }
  function pick(g,scroll) {
    SEL=g;draw();renderCard();const pts=[g.xy,g.xo].filter(Boolean);if(pts.length)zoomPts(pts);
    if(scroll)$("sec-mapa").scrollIntoView({behavior:"smooth",block:"start"});
    else if(matchMedia("(hover:none)").matches)$("card").scrollIntoView({behavior:"smooth",block:"start"});
  }
  const ufSel=$("uf"),back=$("back");
  [...new Set(G.map(g=>g.uf))].sort().forEach(u=>ufSel.add(new Option(u,u)));
  function setUF(u) {
    UF=u;ufSel.value=u;back.hidden=!u;SEL=null;SHOWN=20;
    if(u)zoomTo({type:"FeatureCollection",features:states.features.filter(f=>code(f)===CODEOF[u])});
    else svg.transition().duration(600).call(zoom.transform,d3.zoomIdentity);
    render();
  }
  ufSel.onchange=()=>setUF(ufSel.value);back.onclick=()=>setUF("");
  const byLabel=new Map(),muns=[...new Map(G.map(g=>[g.uf+g.ib,g])).values()].sort((a,b)=>a.m.localeCompare(b.m));
  for(const g of muns) { const label=`${text(g.m)} (${g.uf})`;byLabel.set(label,g);$("muns").append(new Option(label,label)); }
  $("q").addEventListener("change",e=>{
    const g=byLabel.get(e.target.value);if(!g)return;
    UF=g.uf;ufSel.value=g.uf;back.hidden=false;SEL=null;SHOWN=20;
    const f=feats.find(f=>code(f)===String(g.ib));if(f)zoomTo(f,.4);render();e.target.blur();
  });
  document.querySelectorAll("[data-win]").forEach(b=>b.onclick=()=>{
    WIN=b.dataset.win;document.querySelectorAll("[data-win]").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));SEL=null;SHOWN=20;render();
  });
  for(const k of Object.keys(F)) { const b=$("f-"+k);b.onclick=()=>{F[k]=!F[k];b.setAttribute("aria-pressed",String(F[k]));SEL=null;SHOWN=20;render();}; }
  $("gen").textContent=meta.gen;$("registry-date").textContent=meta.reg;$("source-sections").textContent=int(meta.secoes);
  render();
}

async function start() {
  try {
    if(location.protocol==="file:")throw new Error("Abra a aplicação por um servidor HTTP ou pelo GitHub Pages. Consulte o README do projeto.");
    if(!globalThis.d3)throw new Error("Não foi possível carregar a biblioteca D3. Verifique a conexão e tente novamente.");
    const configURL=new URL(document.querySelector('meta[name="dashboard-config"]').content,location.href);
    const config=await fetchJSON(configURL,true);
    const [data,municipalities,states]=await Promise.all([
      loadDashboardData(new URL(config.dataUrl,configURL),config.metadata,globalThis.d3,config.dataFormat || "csv"),
      fetchJSON(new URL(config.municipalitiesUrl,configURL)),
      fetchJSON(new URL(config.statesUrl,configURL)),
    ]);
    for(const geo of [municipalities,states])if(geo.type!=="FeatureCollection"||!geo.features?.length)throw new Error("A fonte do mapa não retornou uma coleção de geometrias válida.");
    $("dashboard").hidden=false;
    initializeNavigation();
    const snapshots = data.snapshots ?? [{ extractedAt:null, dateLabel:config.metadata?.extractionDate || config.metadata?.gen || "Carga atual", data }];
    const dayKey = snapshot => {
      if (!snapshot.extractedAt) return snapshot.dateLabel;
      const parts = new Intl.DateTimeFormat("en-CA", {
        year:"numeric", month:"2-digit", day:"2-digit", timeZone:"America/Sao_Paulo",
      }).formatToParts(new Date(snapshot.extractedAt));
      const part = type => parts.find(item => item.type === type).value;
      return `${part("year")}-${part("month")}-${part("day")}`;
    };
    const dayLabel = snapshot => snapshot.extractedAt
      ? new Intl.DateTimeFormat("pt-BR", { dateStyle:"short", timeZone:"America/Sao_Paulo" }).format(new Date(snapshot.extractedAt))
      : snapshot.dateLabel;
    const timeLabel = snapshot => snapshot.extractedAt
      ? new Intl.DateTimeFormat("pt-BR", { hour:"2-digit", minute:"2-digit", timeZone:"America/Sao_Paulo" }).format(new Date(snapshot.extractedAt))
      : "Único";
    
    const byDay = new Map();
    for (const snapshot of snapshots) {
      const key = dayKey(snapshot);
      if (!byDay.has(key)) {
        byDay.set(key, { key, label:dayLabel(snapshot), loads:[] });
      }
      byDay.get(key).loads.push(snapshot);
    }
    
    globalThis.allSnapshots = snapshots;
    
    const days = [...byDay.values()].sort((a,b) => b.key.localeCompare(a.key));
    days.forEach(day => {
      day.loads.sort((a,b) => (b.extractedAt || "").localeCompare(a.extractedAt || ""));
    });
    
    const tabs = $("snapshot-tabs"), panel = $("snapshot-panel");
    const panelTemplate = panel.innerHTML;
    let activeDay = days[0].key;
    let activeLoad = null;
    
    const activate = (day, loadIndex = 0) => {
      activeDay = day;
      const dayData = days.find(d => d.key === day);
      const snapshot = dayData.loads[loadIndex];
      activeLoad = loadIndex;
      
      for (const tab of tabs.querySelectorAll('[role="tab"]')) {
        const selected = tab.dataset.day === activeDay;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
      }
      
      const select = tabs.querySelector(`select[data-day="${day}"]`);
      if (select) select.value = loadIndex;
      
      panel.innerHTML = panelTemplate;
      panel.setAttribute("aria-labelledby", `snapshot-tab-${activeDay}`);
      const displayLabel = dayData.loads.length > 1 
        ? `${dayData.label} - ${timeLabel(snapshot)}`
        : dayData.label;
      const genLabel = snapshot.extractedAt
        ? `${dayData.label} às ${timeLabel(snapshot)}`
        : snapshot.data.meta.gen;
      initializeDashboard({
        ...snapshot.data,
        meta: { ...snapshot.data.meta, extractionDate:displayLabel, gen:genLabel },
      }, municipalities, states);
    };
    
    days.forEach((day, index) => {
      const tabContainer = document.createElement("div");
      tabContainer.style.display = "contents";
      
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "snapshot-tab";
      tab.id = `snapshot-tab-${day.key}`;
      tab.dataset.day = day.key;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-controls", "snapshot-panel");
      tab.setAttribute("aria-selected", "false");
      tab.tabIndex = -1;
      tab.textContent = day.label;
      tab.onclick = () => activate(day.key, 0);
      tab.onkeydown = event => {
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % days.length;
        else if (event.key === "ArrowLeft") next = (index - 1 + days.length) % days.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = days.length - 1;
        else return;
        event.preventDefault();
        activate(days[next].key, 0);
        $(`snapshot-tab-${days[next].key}`).focus();
      };
      tabContainer.appendChild(tab);
      
      if (day.loads.length > 1) {
        const select = document.createElement("select");
        select.className = "snapshot-load-select";
        select.dataset.day = day.key;
        select.setAttribute("aria-label", `Cargas para ${day.label}`);
        select.onchange = event => activate(day.key, parseInt(event.target.value));
        
        day.loads.forEach((load, loadIdx) => {
          const option = document.createElement("option");
          option.value = loadIdx;
          option.textContent = timeLabel(load);
          select.appendChild(option);
        });
        
        tabContainer.appendChild(select);
      }
      
      tabs.append(tabContainer);
    });
    activate(activeDay, 0);
    $("dashboard").setAttribute("aria-busy","false");$("load-status").hidden=true;
  } catch(error) {
    $("dashboard").hidden=true;
    $("load-title").textContent="Não foi possível carregar o dashboard";
    $("load-message").textContent=error.name==="AbortError"?"A fonte demorou mais de 30 segundos para responder. Tente novamente.":error.message;
    $("retry-load").hidden=false;
  }
}
$("retry-load").onclick=()=>location.reload();
start();