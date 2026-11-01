---
title: Hub-currículo interativo
summary: Este próprio site, um currículo em que cada seção demonstra uma habilidade com Python.
repo: octocat/Hello-World
skills: [python, fastapi, pydantic, htmx, tailwind, pytest, docker, github-actions]
tags: [web, testing, devops]
featured: true
order: 1
year: 2026
---
## Problema

Um currículo em PDF lista tecnologias, mas não prova nada. Eu queria que quem avalia pudesse *usar* o que construí, ler o código e conferir a qualidade em vez de confiar na minha palavra.

## Solução

Um site renderizado no servidor com FastAPI e Jinja2, com HTMX para navegação fluida e Alpine.js para pequenos detalhes de interface. O conteúdo vive em arquivos YAML e Markdown validados por Pydantic, em português e inglês.

## Arquitetura

O núcleo é uma aplicação assíncrona com uma única responsabilidade por módulo. A validação do conteúdo acontece na inicialização, então um erro de digitação nunca chega à produção:

```python
class Skill(BaseModel):
    slug: str
    name: str
    level: int = Field(ge=1, le=5)
```

A política de segurança de conteúdo (CSP) é estrita: sem scripts inline e sem `eval`.

## Resultados

- Páginas funcionam sem JavaScript e melhoram com HTMX.
- Cobertura de testes acima de 85%, com verificação de tipos em modo estrito.
- Pipeline de integração contínua em Linux e Windows.

## Aprendizados

Restringir a CSP desde o primeiro dia custou pouco e evitou retrabalho. Já adotar bibliotecas visuais pesadas exigiu perfis de política específicos por página.
