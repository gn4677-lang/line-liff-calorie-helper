# Agentic Rewrite Tech Spec v3

This tree implements the first executable slice of the v3 rewrite:

- typed agent contracts
- deterministic guardrails
- AgentState assembly
- understand -> plan -> execute_with_guardrails -> respond -> update_state
- Today / Eat / Progress / Inbox endpoints
- structured onboarding and settings mutation endpoints
- LINE webhook and async worker skeletons

The goal is to move all future product behavior into `agentic/` and keep legacy code as reference only.
