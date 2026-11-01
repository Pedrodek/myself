---
title: Report automation CLI
summary: A command line tool that builds reports from several sources with a single command.
skills: [python, pytest, git]
tags: [cli]
order: 4
year: 2019
---
## Problem

The support team assembled reports by copying data from three different systems, every month.

## Solution

A Python CLI that queries the sources, consolidates the data and produces the final report in one command.

## Results

- From 2 hours of manual work to 1 minute.
- Shipped as an internal package, with automated tests.

## Lessons learned

A good error message is worth more than a lot of documentation: most support tickets disappeared after I improved the messages.
