# Eat Option Layer Spec

## Summary

Eat page options split into two layers:

1. `deterministic control layer`
2. `LLM-selected chip layer`

This keeps navigation and safety deterministic, while letting the model shape the actual decision framing.

## Layer 1: Deterministic Control Layer

Purpose:
- choose scope
- choose place context
- open manual location / explore controls

Examples:
- `現在附近`
- `家附近`
- `公司附近`
- `我自己輸入`

Rules:
- labels come from deterministic code
- actions come from deterministic code
- these options do not depend on LLM output
- these options should stay stable across sessions

## Layer 2: LLM-Selected Chip Layer

Purpose:
- shape the session's recommendation intent
- help the user express "what kind of choice do I want right now"

Examples:
- `高蛋白`
- `熟悉穩定`
- `快速拿了就走`
- `今天吃熱的`

Rules:
- LLM does not free-generate arbitrary chips
- deterministic code defines the bounded chip catalog
- deterministic code gates unsupported chips
- LLM selects and orders the most useful chips for this session

## Contract

Backend `EatFeedResponse` should expose:
- `control_options`
- `decision_chips`

Backward compatibility:
- keep `smart_chips` as an alias of `decision_chips` during transition

## UX Rules

- render control layer first
- render decision chips second
- control layer changes scope
- decision chips change rerank policy
- do not mix the two concepts into one rail
