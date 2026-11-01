---
title: Versioned data pipelines
summary: Twelve spreadsheet routines became tested, scheduled and monitored pipelines.
skills: [python, pandas, postgres, docker, github-actions]
tags: [data, devops]
featured: true
order: 3
year: 2022
---
## Problem

Monthly reports depended on manual spreadsheets, which were error-prone and impossible to audit.

## Solution

Each routine became a Python pipeline with schema validation on inputs and outputs, versioned in Git and run on a schedule inside containers.

## Architecture

Small, pure steps (extract, validate, transform, load) make testing easy. Validation failures stop the pipeline and produce a readable report.

## Results

- About 30 hours a month saved.
- Full audit trail: every number has an origin and a code version.

## Lessons learned

Validating data at the entrance prevents most of the problems that used to surface only in the final report.
