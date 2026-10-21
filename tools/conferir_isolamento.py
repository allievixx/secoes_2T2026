"""Trava de isolamento: PARA tudo se o deploy de dev apontar para produção.

    python tools/conferir_isolamento.py            confere o alvo do deploy (projeto/job/credencial)
    python tools/conferir_isolamento.py --simular   mostra o que conferiria, sem rede

Roda em TODO job dos workflows (.github/workflows/deploy-dev.yml e deploy-prod.yml), ANTES de
qualquer `terraform apply` ou deploy de imagem.

Segue a mesma filosofia do boralula-bot / agregador-de-agendas:
  o ambiente de dev vive num PROJETO GCP separado do de produção. Se, por engano, o pipeline de dev
  receber o project_id de PRODUÇÃO (nos segredos/vars do repositório, ou no tfvars),
  esta trava falha o job e nada é aplicado.

O que ela recusa (sai com código 1), para o ambiente ALVO (SECOES_ENV=dev|prod):
  - em dev: o project_id, o bucket ou o nome do job alvo pertencem à lista de PRODUÇÃO;
  - a conta de serviço do GCP ativa (do GOOGLE_APPLICATION_CREDENTIALS) pertence a um projeto de
    produção, quando o ambiente alvo é dev;
  - opcionalmente, confere via API (Cloud Resource Manager) se as credenciais ativas enxergam o
    projeto de produção — só quando há rede e credencial (desligável com --sem-rede).

Variáveis de ambiente suportadas:
  SECOES_ENV                     "dev" (padrão) ou "prod" — qual ambiente este job está deployando
  SECOES_PROJECT_ID              project_id ALVO deste deploy (o mesmo passado ao Terraform)
  SECOES_JOB_NAME                (opcional) nome do job Cloud Run alvo
  SECOES_BUCKET                  (opcional) bucket alvo
  GOOGLE_APPLICATION_CREDENTIALS (opcional) JSON da conta de serviço, para conferência por API
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

CRM_API = os.environ.get("GCP_CRM_URL", "https://cloudresourcemanager.googleapis.com/v1")

# Identificadores de PRODUÇÃO que o deploy de DEV nunca pode usar.
PRODUCAO = {
    "projects": {"thech-against-bozo", "tech-against-bozo"},
    "jobs": {"secoes-etl-prod"},
    "buckets": set(),
}


def _do_ambiente(nome: str) -> set[str]:
    bruto = os.environ.get(nome, "")
    return {p.strip() for p in bruto.split(",") if p.strip()}


def producao() -> dict[str, set[str]]:
    return {
        "projects": PRODUCAO["projects"] | _do_ambiente("SECOES_PROD_PROJECTS"),
        "jobs": PRODUCAO["jobs"] | _do_ambiente("SECOES_PROD_JOBS"),
        "buckets": PRODUCAO["buckets"] | _do_ambiente("SECOES_PROD_BUCKETS"),
    }


def _project_da_credencial() -> str:
    """Lê o project_id do JSON apontado por GOOGLE_APPLICATION_CREDENTIALS, se houver."""
    caminho = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not caminho or not os.path.isfile(caminho):
        return ""
    try:
        with open(caminho, encoding="utf-8") as f:
            return (json.load(f).get("project_id") or "").strip()
    except (ValueError, OSError):
        return ""


def pedir(api: str, caminho: str, token: str):
    """GET autenticado na API GCP; devolve JSON. Erros não são fatais aqui: a trava decide."""
    req = urllib.request.Request(api + caminho, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            texto = r.read()
            return json.loads(texto) if texto else None
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(texto).get("error", {}).get("message") or texto
        except (ValueError, AttributeError):
            msg = texto
        return {"__erro__": e.code, "__msg__": msg}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"__erro__": "rede", "__msg__": str(e)}


def conferir_alvo(env: str, prod: dict[str, set[str]], problemas: list[str]) -> None:
    """Confere os identificadores ALVO deste deploy contra a lista de produção.

    Só trava quando o ambiente alvo é dev: um deploy de prod PODE usar os ids de produção.
    """
    project = os.environ.get("SECOES_PROJECT_ID", "").strip()
    job = os.environ.get("SECOES_JOB_NAME", "").strip()
    bucket = os.environ.get("SECOES_BUCKET", "").strip()

    if env != "dev":
        print(f"Alvo: ambiente '{env}' (produção) — conferência de alvo-vs-produção não se aplica.")
        return

    if not project:
        problemas.append("Alvo: falta SECOES_PROJECT_ID (não dá para conferir o isolamento do deploy de dev)")
    elif project in prod["projects"]:
        problemas.append(f"Alvo: SECOES_PROJECT_ID '{project}' é um projeto de PRODUÇÃO")

    if job and job in prod["jobs"]:
        problemas.append(f"Alvo: SECOES_JOB_NAME '{job}' é um job de PRODUÇÃO")

    if bucket and bucket in prod["buckets"]:
        problemas.append(f"Alvo: SECOES_BUCKET '{bucket}' é um bucket de PRODUÇÃO")

    cred_proj = _project_da_credencial()
    if cred_proj and cred_proj in prod["projects"]:
        problemas.append(
            f"Alvo: a conta de serviço ativa pertence ao projeto de PRODUÇÃO '{cred_proj}' "
            "(GOOGLE_APPLICATION_CREDENTIALS)"
        )

    if not problemas:
        print(f"Alvo: ok — projeto '{project or '(não informado)'}' não é de produção.")


def conferir_api(env: str, prod: dict[str, set[str]], problemas: list[str], sem_rede: bool) -> None:
    """Conferência opcional por API: as credenciais ativas enxergam um projeto de produção?

    Usa GCP_ACCESS_TOKEN (ex.: `gcloud auth print-access-token`), se disponível. Sem token/rede, pula
    silenciosamente — o gate principal é conferir_alvo(), que não depende de rede.
    """
    if env != "dev" or sem_rede:
        return
    token = os.environ.get("GCP_ACCESS_TOKEN", "").strip()
    if not token:
        print("API: sem GCP_ACCESS_TOKEN — pulando a conferência por rede (gate principal já rodou).")
        return
    r = pedir(CRM_API, "/projects", token)
    if not isinstance(r, dict) or "projects" not in r:
        if isinstance(r, dict) and "__erro__" in r:
            print(f"API: não deu para listar projetos ({r['__erro__']}): {r['__msg__']} — seguindo pelo gate local.")
        return
    ids = {p.get("projectId") for p in r.get("projects") or [] if isinstance(p, dict)}
    ids.discard(None)
    vazou = ids & prod["projects"]
    if vazou:
        problemas.append(f"API: as credenciais enxergam projeto(s) de PRODUÇÃO: {', '.join(sorted(vazou))}")
    else:
        print(f"API: ok — {len(ids)} projeto(s) visível(is), nenhum de produção.")


def main() -> int:
    env = os.environ.get("SECOES_ENV", "dev").strip().lower()
    prod = producao()
    sem_rede = "--sem-rede" in sys.argv[1:]

    if "--simular" in sys.argv[1:]:
        print(f"Conferiria (ambiente alvo: {env}), sem apontar para produção:")
        print(f"  projetos de produção proibidos: {', '.join(sorted(prod['projects'])) or '(nenhum)'}")
        print(f"  jobs de produção proibidos:     {', '.join(sorted(prod['jobs'])) or '(nenhum)'}")
        print(f"  buckets de produção proibidos:  {', '.join(sorted(prod['buckets'])) or '(nenhum)'}")
        return 0

    problemas: list[str] = []
    conferir_alvo(env, prod, problemas)
    conferir_api(env, prod, problemas, sem_rede)

    if problemas:
        print("\nPARE: a trava de isolamento recusou — risco de tocar em produção:", file=sys.stderr)
        for p in problemas:
            print(f"  - {p}", file=sys.stderr)
        print("\nUse projeto/job/credenciais só de DEV. Nada foi aplicado.", file=sys.stderr)
        return 1

    print("\nIsolamento ok: o deploy de dev não aponta para produção.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
