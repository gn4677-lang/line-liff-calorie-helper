# Prompt For Antigravity

Use this as the starting brief for frontend and interaction work.

```md
You are working on the frontend of a LINE + LIFF app called "AI Fat Loss OS".

Repo:
https://github.com/gn4677-lang/line-liff-calorie-helper

Read these first:
- docs/product-spec-v1.md
- docs/antigravity-frontend-handoff.md
- frontend/src/App.tsx
- backend/app/schemas.py

Your task:
- redesign and refactor the LIFF frontend into a product-quality mobile-first experience
- preserve the existing backend API contracts unless there is a strong reason to change them
- preserve LIFF auth boot flow
- keep the three primary pages: Progress, Today, Eat

Important constraints:
- this is a self-use fat loss operating system, not a generic calorie tracker
- Today is the main cockpit
- meal logging and clarification must feel compact and low-friction
- Eat should show a few usable recommendations, not a giant list
- do not put secrets in frontend
- assume usage happens inside LINE LIFF on mobile first

Design goals:
- clear remaining-calorie hierarchy
- conversational draft / clarification UI
- bolder, more intentional visual identity
- not generic SaaS
- not purple-default AI styling
- preserve readability on mobile

Do:
- propose a refined information architecture inside the 3-page structure
- create reusable components
- improve empty states, loading states, and error states
- improve recommendation grouping and decision support clarity
- improve Today page so it feels like a real daily cockpit

Do not:
- break LIFF auth
- rename backend fields casually
- redesign this into a social app
- turn the recommendation area into a massive searchable catalog

Acceptance target:
- user can open LIFF and immediately understand today's status
- user can log a meal in under 30 seconds
- user can answer a clarification question without friction
- user can decide what to eat from the Eat page
- UI feels intentional and shippable
```
