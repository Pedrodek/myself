# Hub-currículo interativo

Um site-currículo em que cada seção demonstra uma habilidade com Python: FastAPI + Jinja2 + HTMX, conteúdo em YAML/Markdown validado por Pydantic, pt-BR/en, tema claro/escuro, API JSON somente leitura e uma CSP estrita (sem scripts inline e sem `eval`). **Sem Node.js**: o Tailwind CSS é compilado com o binário standalone instalado pelo pip.

> **Status:** v0.1 (fases F0–F3 do [plano de implementação](PLANO_DE_IMPLEMENTACAO.md)). Contato, livro de visitas, GitHub ao vivo, terminal web e playground Pyodide (F4–F7) ainda não foram implementados.

## Rodando localmente

Requer Python 3.11+ (testado em 3.14).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements-dev.txt
playwright install chromium        # só para os testes E2E e o PDF

python -m app dev                  # http://127.0.0.1:8000 (recarrega ao salvar, recompila o CSS)
```

> No Windows o *hot reload* do uvicorn às vezes deixa de reiniciar o processo após várias mudanças seguidas (acontece também com `uvicorn --reload` puro). Se uma alteração não aparecer, pare com `Ctrl+C` e rode `python -m app dev` de novo.

No Linux/macOS, ative com `source .venv/bin/activate`.

## Colocando o seu conteúdo

Todo o texto está em `content/` e hoje é **fictício** (`sample: true`). Edite:

| Arquivo | O que é |
|---|---|
| `content/<pt\|en>/profile.yaml` | Nome, headline, resumo, contato e links |
| `content/<pt\|en>/experience.yaml` | Experiências (use números nos resultados) |
| `content/<pt\|en>/skills.yaml` | Habilidades: nível 1–5, anos, evidências (slugs de projetos) |
| `content/<pt\|en>/education.yaml` | Formação |
| `content/<pt\|en>/projects/<slug>.md` | Estudos de caso (front matter YAML + Markdown) |

Depois valide (referências cruzadas, datas, URLs e **paridade pt/en**) e remova `sample: true` do `profile.yaml`:

```powershell
python -m app content validate            # lista todos os problemas de uma vez
python -m app content validate --strict   # também falha enquanto houver conteúdo de exemplo
```

Em produção (`HUB_ENV=prod`) a aplicação **recusa subir** com conteúdo de exemplo, a menos que `HUB_ALLOW_SAMPLE_CONTENT=true`.

## Comandos úteis

```powershell
python -m app --help
python -m app assets sync            # baixa htmx, Alpine (build CSP) e xterm; confere SHA-384 em assets.lock.json
python -m app assets build           # Tailwind + fingerprint + manifest
python -m app i18n update            # extrai strings e atualiza os catálogos .po
python -m app i18n check             # falha se algo estiver sem tradução (gate de CI)
python -m app export all             # PDFs do currículo (pt/en) e imagem Open Graph em build/downloads
python -m app serve                  # servidor de produção (1 worker)

pytest                               # unitários + integração (cobertura mínima: 85%)
pytest -m e2e tests/e2e              # navegador real; falha em erro de console ou violação de CSP
ruff check . ; ruff format --check . ; djlint app/web/templates --check ; mypy
```

## Configuração

Variáveis `HUB_*` (veja [.env.example](.env.example)). As principais:

| Variável | Uso |
|---|---|
| `HUB_ENV` | `dev`, `test` ou `prod` |
| `HUB_SECRET_KEY` | **Obrigatória em prod** (≥ 32 caracteres) |
| `HUB_SITE_URL` | URL pública (canonical, Open Graph, sitemap) |
| `HUB_TRUSTED_PROXIES` | IPs do proxy reverso confiáveis para `X-Forwarded-*` |
| `HUB_HSTS_MAX_AGE` | Segundos de HSTS (ative só depois de validar o HTTPS) |
| `HUB_ALLOW_SAMPLE_CONTENT` | Permite subir em prod com o conteúdo de exemplo |

## Contêiner

```powershell
copy .env.example .env      # defina HUB_SECRET_KEY
docker compose up --build   # http://localhost:8000
```

A imagem é multi-stage (o binário do Tailwind fica só no estágio de build), roda como usuário não-root, com `HEALTHCHECK` em `/healthz`. Use **uma única instância**: rate limit e caches ficam em memória e (a partir da F4) o SQLite fica no volume `/data`.

## Segurança

- CSP estrita por padrão: `script-src 'self'`, `style-src 'self'`, sem `unsafe-eval`. Alpine.js usa o **build CSP** e o htmx roda com `allowEval=false`.
- Perfis de CSP por rota para bibliotecas que injetam `<style>` (gráficos, terminal) — ver `app/core/security.py`.
- Assets de terceiros são hospedados por nós e verificados por SHA-384 (`assets.lock.json`); a referência do Swagger UI usa SRI.
- Markdown sem HTML cru; YAML sempre com `safe_load`; corpo de requisições limitado a 16 KB.

## Estrutura

```text
app/            aplicação (core/, content/, routers/, cli/, web/)
content/        conteúdo do currículo (pt/ e en/)
tests/          unit/, integration/ e e2e/
assets.lock.json  versões e hashes dos assets vendorizados
PLANO_DE_IMPLEMENTACAO.md  decisões, fases e riscos
```

## Licença

[MIT](LICENSE)
