---
title: Pipelines de dados versionados
summary: Doze rotinas de planilhas viraram pipelines testados, agendados e monitorados.
skills: [python, pandas, postgres, docker, github-actions]
tags: [data, devops]
featured: true
order: 3
year: 2022
---
## Problema

Relatórios mensais dependiam de planilhas manuais, sujeitas a erro e impossíveis de auditar.

## Solução

Cada rotina virou um pipeline em Python com validação de esquema nas entradas e saídas, versionado no Git e executado por agendamento em contêineres.

## Arquitetura

Etapas pequenas e puras (extrair, validar, transformar, carregar) facilitam o teste. Falhas de validação interrompem o pipeline e geram um relatório legível.

## Resultados

- Cerca de 30 horas por mês economizadas.
- Auditoria completa: cada número tem origem e versão do código.

## Aprendizados

Validar os dados na entrada evita a maior parte dos problemas que antes só apareciam no relatório final.
