# DNS do secoes na Cloudflare (conta kadu)

Esta raiz cria o endereço do site, `secoes.boralula.org`, na zona `boralula.org` da conta Cloudflare **kadu**, a de produção do
comitê. O site continua no GitHub Pages (`.github/workflows/pages.yml`); a Cloudflare só aponta o nome para ele.

| Ambiente | Conta | Onde | Endereço | Situação |
|---|---|---|---|---|
| produção | kadu | `infra/cloudflare-kadu` (`prod.tf`) | `secoes.boralula.org` | novo |
| dev | - | - | - | sem dev hoje |

## O que gerencia

| O quê | Valor |
|---|---|
| Registro `CNAME` `secoes.boralula.org` | aponta para `comite-popular-tech.github.io` (o Pages da organização; o GitHub escolhe o site pelo domínio do repositório, não pelo caminho) |
| Proxy da Cloudflare | **desligado**: o GitHub Pages emite e renova o próprio certificado e precisa ver o CNAME apontando para ele |

## O que não é daqui

| O quê | Onde |
|---|---|
| Zona `boralula.org`, configurações e DNS compartilhado | `iac-shared`, raiz `terraform/cloudflare-kadu` |
| Domínio personalizado do Pages (Settings > Pages > Custom domain) | configuração do repositório, à mão |
| Rotina de dados (Cloud Run Job) e o bucket dela | depois da eleição (25/10/2026), em outra raiz; não entra aqui |

A verificação de domínio do Pages (TXT `_github-pages-challenge-comite-popular-tech`) não é exigida para o domínio funcionar. Ela impede
que outra conta use um subdomínio de `boralula.org` que fique apontado para o Pages sem dono. Quem é dono da organização gera o valor em
*Settings > Pages > Add a domain*, e o TXT entra no `iac-shared`, junto do DNS compartilhado.

## Configuração

- Estado no bucket do Google do comitê, prefixo `secoes/cloudflare-kadu`. A conta de serviço que o `iac` cria para este
  repositório (segredo `TF_ESTADO_CONTA`) só alcança objetos sob `secoes/`.
- Segredos do repositório (só os nomes aqui; os valores ficam no gerenciador de senhas do projeto):

| Segredo | O que é |
|---|---|
| `TF_ESTADO_CONTA` | conta de serviço do estado (criada pelo `iac`) |
| `TF_ESTADO_BUCKET` | bucket do estado |
| `GCP_WIF_PROVIDER` | provedor de Workload Identity Federation que aceita este repositório |
| `CLOUDFLARE_KADU_ZONE_ID` | id da zona `boralula.org` (vira `TF_VAR_zone_id`) |
| `CLOUDFLARE_KADU_PLAN_TOKEN` | token da conta kadu só de leitura, para o plano do PR |
| `CLOUDFLARE_KADU_TOKEN` | token da conta kadu com edição, para o apply |

- Permissões dos tokens: **Zone DNS Read** (plano) e **Zone DNS Edit** (apply), só na zona `boralula.org`. Nenhuma permissão de conta.
- O workflow `.github/workflows/infra-cloudflare-kadu.yml` faz `fmt` e `validate` em todo PR, o plano como comentário em PR de ramo
  deste repositório (PR de fork não recebe segredo) e o `apply` na `main`, que recusa um plano que apague ou recrie algum recurso.
  Como no `iac-shared`, a proteção do token de apply é o acesso de escrita ao repositório.

## Publicar o endereço

1. Em *Settings > Pages > Custom domain* do repositório, informar `secoes.boralula.org`. O Pages só confere o DNS depois.
2. Mesclar o PR: o `apply` cria o CNAME.
3. Esperar o GitHub conferir o DNS e emitir o certificado (minutos, às vezes mais), e conferir que *Enforce HTTPS* está marcado.
4. Abrir https://secoes.boralula.org.

`vite.config.ts` usa `base: "./"`, então o site abre igual na raiz do domínio e no caminho antigo do Pages.

## À mão

A partir da `main` atualizada:

```bash
cd infra/cloudflare-kadu
export CLOUDFLARE_API_TOKEN=<token>
export TF_VAR_zone_id=<id da zona boralula.org>
gcloud auth application-default login
terraform init -backend-config="bucket=<bucket>" -backend-config="prefix=secoes/cloudflare-kadu"
terraform plan
```
