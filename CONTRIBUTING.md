# Guia de contribuição e de documentação

Este guia explica **como o código é documentado** e como estender o projeto sem quebrar as
convenções. Para rodar o site, veja o [README](README.md); para o escopo e as decisões, o
[plano de implementação](PLANO_DE_IMPLEMENTACAO.md).

## Mapa para se orientar

| Quero entender... | Comece por |
|---|---|
| Como a aplicação é montada | `app/main.py` (`create_app`): ordem dos middlewares, rotas e o que fica em `app.state` |
| Como o conteúdo é lido e validado | `app/content/models.py` (formato), `app/content/loader.py` (validação e regras entre arquivos) |
| Como uma página é renderizada | `app/routers/pages.py`, depois `app/core/templating.py` (`Renderer`) e `app/web/templates/base.html` |
| Navegação sem recarregar (HTMX) | `app/core/htmx.py`, `app/web/templates/fragment.html` e `app/web/static/js/app.js` |
| Segurança (CSP e cabeçalhos) | `app/core/security.py` |
| Pipeline de assets | `app/cli/assets.py` e `assets.lock.json` |
| Tradução | `app/core/i18n.py`, `app/cli/i18n.py` e `app/locales/` |

Cada módulo Python começa com uma docstring que diz **qual é a responsabilidade dele**; leia-a
antes do código.

## Política de documentação do código

### Python

- **Idioma:** docstrings e comentários em **inglês**, como no restante do código. Conteúdo
  voltado ao visitante (textos do currículo, README e este guia) fica em **português do Brasil**.
- **Estilo:** [Google](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).
  Primeira linha curta, no imperativo ou descritiva, terminando em ponto; depois, se preciso, um
  parágrafo e as seções `Args:`, `Returns:`, `Raises:` e `Attributes:`.
- **Obrigatório em `app/`:** módulo, classe, função e método públicos têm docstring. O ruff
  (regras `D`, convenção Google) **falha** quando falta uma, tanto no `pre-commit` quanto no CI.
  Os testes são isentos: o nome descritivo do teste faz esse papel.
- **Escreva o *porquê*, não o óbvio.** Não repita o nome da função. Registre o que o código não
  mostra: uma restrição de segurança, uma armadilha, uma decisão. Exemplo real: o
  `RequestContextMiddleware` só reaproveita um `X-Request-ID` válido, o que evita injeção em logs.
- **Use `Args:`/`Returns:`/`Raises:` só quando agregarem.** Em funções de uma linha de lógica, a
  primeira linha basta.
- **Tipos ficam nas assinaturas**, não nas docstrings. O `mypy --strict` é a fonte da verdade.
- **Comentários `#`** explicam o motivo de uma linha ou bloco não óbvio, nunca o que ela faz.
- **Rotas da API** (`app/routers/api.py`): a docstring vira a descrição no OpenAPI
  (`/api/docs`). Escreva para quem consome a API e não use `Args:`.

### Templates Jinja

- Cada macro em `components/macros.html` tem um comentário `{# ... #}` acima dele com o uso, os
  parâmetros e qualquer detalhe de acessibilidade.
- Comente decisões que dependem da CSP ou do HTMX; elas não são óbvias para quem lê só o HTML.

### JavaScript e CSS

- Cabeçalho de arquivo explicando o papel e a ordem de carga. Sem scripts inline: a CSP proíbe.
- Em `app.css`, agrupe as regras por seção com um comentário (`/* Header */`).

## Como estender o projeto

### Adicionar uma página

1. Crie o template em `app/web/templates/pages/` estendendo `{% extends layout %}`.
2. Crie a rota em `app/routers/pages.py` com o decorador `@page(...)` e uma docstring.
3. Adicione o item em `NAV` (`app/core/templating.py`) e o caminho em `SITEMAP_SECTIONS`
   (`app/routers/seo.py`), se a página deve aparecer no menu e no sitemap.
4. Marque os textos com `_("...")` e rode `python -m app i18n update`; depois traduza o `.po` de
   `pt_BR`. O CI roda `python -m app i18n check` e falha com texto sem tradução.
5. Escreva um teste de integração em `tests/integration/`.

### Alterar ou acrescentar conteúdo

Edite `content/<pt|en>/` e rode `python -m app content validate`. A validação cobre formato,
referências entre arquivos e **paridade pt/en**. Para o formato de cada arquivo, veja os modelos
documentados em `app/content/models.py`.

### Criar um perfil de CSP

Acrescente o nome em `PROFILES` e um ramo em `csp_for` (`app/core/security.py`). A rota escolhe o
perfil ao chamar `renderer.render(..., csp="nome")`. Explique na docstring do módulo **por que**
a política precisa de uma exceção.

## Qualidade antes de abrir o PR

```powershell
ruff check . ; ruff format --check .      # estilo, imports e docstrings
mypy                                      # tipos estritos
djlint app/web/templates --check          # templates
python -m app content validate --strict   # conteúdo real, sem marcador de exemplo
python -m app i18n check                  # traduções completas
pytest                                    # unitários e integração (cobertura mínima: 85%)
pytest -m e2e tests/e2e                   # navegador real (requer o Chromium do Playwright)
```

`pre-commit install` roda os mesmos checks de lint a cada commit.

### Testes

- Os testes usam o **conteúdo fictício** de `tests/fixtures/content/`, para não depender dos seus
  dados reais. Só `test_content_validate_accepts_the_real_content` lê a pasta `content/`.
- Prefira nomes que descrevam o comportamento esperado
  (`test_projects_filter_without_javascript`).

## Commits e Changelog

- Siga o [Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/):
  `tipo(escopo): descrição`. O tipo (`feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`,
  `chore`) e o escopo ficam em inglês; a descrição fica em português, no imperativo, em
  minúsculas e sem ponto final, com até ~72 caracteres.
- Use o corpo da mensagem para explicar **o porquê** da mudança, não o que o diff já mostra.
- Faça commits atômicos: cada um deve passar nos testes e no lint sozinho.
- Registre mudanças relevantes para quem usa o projeto em [CHANGELOG.md](CHANGELOG.md), na seção
  `Unreleased`, no formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
