---
title: API de pedidos de alta vazão
summary: API assíncrona que processa milhares de pedidos por minuto com latência previsível.
repo: octocat/Spoon-Knife
skills: [python, fastapi, asyncio, sqlalchemy, postgres, pytest, docker]
tags: [api, async, data]
featured: true
order: 2
year: 2024
---
## Problema

O monólito anterior travava em horários de pico: filas de pedidos cresciam e o p95 passava de 480 ms.

## Solução

Reescrevi o fluxo crítico como uma API assíncrona com FastAPI, SQLAlchemy 2 em modo async e PostgreSQL, isolando operações lentas em tarefas de segundo plano.

## Arquitetura

As rotas são finas e delegam a serviços testáveis. Operações idempotentes usam chaves de idempotência para que reenvios do cliente não dupliquem pedidos.

## Resultados

- p95 de 480 ms para 130 ms.
- Zero pedidos duplicados após a adoção das chaves de idempotência.
- Cobertura de testes de 40% para 88%.

## Aprendizados

Medir antes de otimizar economizou semanas: o gargalo estava em duas consultas, não no framework.
