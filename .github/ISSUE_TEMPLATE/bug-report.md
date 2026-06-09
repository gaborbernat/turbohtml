---
name: Bug report
about: Create a report to help us improve
title: ""
labels: bug
assignees: ""
---

## Issue

<!-- Describe the expected behavior and what you observe instead. -->

## Environment

- OS:
- Python version (`python --version`):
- turbohtml version (`python -c "import turbohtml; print(turbohtml.__version__)"`):

## Minimal reproducer

<!-- The exact input, the output you got, and the output you expected. Where it matters, show what
`html.escape`/`html.unescape` returns for the same input, since turbohtml aims to match them. -->

```pycon
>>> import turbohtml
>>> turbohtml.unescape("...")
```
