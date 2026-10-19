import test from "node:test";
import assert from "node:assert/strict";
import { loadDashboardData, prepareDashboardData } from "../dashboard-data.js";

// Dados inteiramente sintéticos; estes testes nunca abrem o CSV do projeto.
const fixture = overrides => ({
  uf:"SP", municipio:"Cidade de teste", cd_ibge:"3550308", zona:"1", secao:"1", eleitores:"100",
  local_1t:"Escola antiga", endereco_1t:"Rua A; 10", lat_1t:"-23.55", lon_1t:"-46.63",
  local_2t:"Escola nova", endereco_2t:"Rua B", bairro_2t:"Centro", lat_2t:"-23.56", lon_2t:"-46.64",
  distancia_km:"2,5", regiao_longe_da_urna:"True",
  aptos_1t:"90", abstencao_1t:"10", lula_1t:"40", flavio_1t:"30", outros_1t:"5", brancos_1t:"2", nulos_1t:"3",
  ...overrides,
});

test("agrupa seções e calcula os totais a partir da fonte", () => {
  const data=prepareDashboardData([fixture(),fixture({secao:"2"})],{gen:"hoje"});
  assert.equal(data.g.length,1);
  assert.equal(data.g[0].s.length,2);
  assert.deepEqual(data.g[0].s[0],[1,100,90,10,40,30,5,2,3]);
  assert.equal(data.g[0].longe,true);
  assert.equal(data.g[0].km,2.5);
  assert.deepEqual(data.g[0].pf,[-23.56,-46.64]);
  assert.equal(data.meta.eleitores,200);
  assert.equal(data.meta.lula,80);
  assert.equal(data.meta.municipios,1);
  assert.equal(data.meta.gen,"hoje");
});

test("preserva valores ausentes e escapa texto vindo da fonte", () => {
  const data=prepareDashboardData([fixture({municipio:'<img src=x onerror="alert(1)">',lat_1t:"",lon_1t:"",lula_1t:"",distancia_km:""})]);
  assert.equal(data.g[0].po,null);
  assert.equal(data.g[0].km,null);
  assert.equal(data.g[0].s[0][4],null);
  assert.ok(!data.g[0].m.includes("<"));
});

test("rejeita schema inválido, seções duplicadas e valores inválidos", () => {
  assert.throws(()=>prepareDashboardData([{}]),/Colunas ausentes/);
  const rows=[];rows.columns=Object.keys(fixture());
  assert.throws(()=>prepareDashboardData(rows),/não contém/);
  assert.throws(()=>prepareDashboardData([fixture(),fixture()]),/duplicada/);
  for(const override of [{eleitores:""},{eleitores:"-1"},{eleitores:"1.5"},{lat_1t:"100"},{uf:"XX"},{regiao_longe_da_urna:"talvez"}]) {
    assert.throws(()=>prepareDashboardData([fixture(override)]));
  }
});

test("busca a fonte sem cache e converte as linhas retornadas pelo parser", async () => {
  let call;
  const data=await loadDashboardData("https://example.test/data.csv",{gen:"hoje"},{dsv:async(...args)=>{call=args;return [fixture()];}});
  assert.equal(call[0],";");
  assert.equal(call[1],"https://example.test/data.csv");
  assert.equal(call[2].cache,"no-store");
  assert.ok(call[2].signal instanceof AbortSignal);
  assert.equal(data.meta.secoes,1);
});

test("preserva indicadores desconhecidos e ignora o campo removido", () => {
  const data=prepareDashboardData([fixture({regiao_longe_da_urna:"",entrou_desde_15_10:"True"})]);
  assert.equal(data.g[0].longe,null);
  assert.equal(data.g[0].s[0].length,9);
});

test("carrega JSON público com nulls e números tipados", async t => {
  t.mock.method(globalThis,"fetch",async()=>({ok:true,json:async()=>({rows:[fixture({eleitores:100,regiao_longe_da_urna:null,entrou_desde_15_10:null})]})}));
  const data=await loadDashboardData("/api/secoes",{},undefined,"json");
  assert.equal(data.meta.eleitores,100);
  assert.equal(data.g[0].longe,null);
  assert.equal(data.g[0].s[0].length,9);
});

test("informa falha HTTP e payload JSON inválido", async t => {
  const mocked=t.mock.method(globalThis,"fetch",async()=>({ok:false,status:503}));
  await assert.rejects(loadDashboardData("/api/secoes",{},undefined,"json"),/503/);
  mocked.mock.mockImplementation(async()=>({ok:true,json:async()=>({wrong:[]})}));
  await assert.rejects(loadDashboardData("/api/secoes",{},undefined,"json"),/rows/);
});

test("carrega e valida snapshots completos por data da extração", async t => {
  t.mock.method(globalThis,"fetch",async()=>({ok:true,json:async()=>({
    snapshots:[
      {extracted_at:"2026-10-19T09:30:00Z",rows:[fixture({secao:"1"})]},
      {extracted_at:"2026-10-20T09:30:00Z",rows:[fixture({secao:"2"})]},
      {extracted_at:"2026-10-19T15:30:00Z",rows:[fixture({secao:"3"})]},
    ],
  })}));
  const data=await loadDashboardData("/api/secoes",{},undefined,"json");
  assert.equal(data.snapshots.length,3);
  assert.deepEqual(data.snapshots.map(snapshot=>snapshot.extractedAt),[
    "2026-10-19T09:30:00.000Z","2026-10-19T15:30:00.000Z","2026-10-20T09:30:00.000Z",
  ]);
  assert.equal(data.g[0].s[0][0],2);
});

test("informa indisponibilidade da biblioteca e falhas da fonte", async () => {
  await assert.rejects(loadDashboardData("/data.csv",{},{}),/D3/);
  await assert.rejects(loadDashboardData("/data.csv",{},{dsv:async()=>{throw new Error("HTTP 404");}}),/HTTP 404/);
});