# Prompt For Antigravity

Use this as the starting brief for frontend and interaction work.

```md
You are working on the frontend of a LINE + LIFF app called "AI Fat Loss OS".

Repo:
https://github.com/gn4677-lang/line-liff-calorie-helper

Read these first:
- docs/product-spec-v1.md
- docs/memory-onboarding-v2.md
- docs/antigravity-frontend-handoff.md
- frontend/src/App.tsx
- backend/app/schemas.py

Your task:
- redesign and refactor the LIFF frontend into a product-quality mobile-first experience
- preserve the existing backend API contracts unless there is a strong reason to change them
- preserve LIFF auth boot flow
- keep the three primary pages: 體重熱量 / 今日紀錄 / 食物推薦

Important constraints:
- this is a self-use fat loss operating system, not a generic calorie tracker
- 今日紀錄 is the main cockpit
- meal logging and clarification must feel compact and low-friction
- 食物推薦 should show a few usable recommendations, not a giant list
- do not put secrets in frontend
- assume usage happens inside LINE LIFF on mobile first

Design goals:
- clear remaining-calorie hierarchy
- conversational draft / clarification UI
- a short and skippable cold-start onboarding flow
- lightweight correction surfaces for preferences
- explainability that helps trust without exposing raw memory labels
- bold, intentional visual identity
- not generic SaaS
- not purple-default AI styling
- preserve readability on mobile

Output hygiene:
- final written outputs must be free of unrelated filler, repeated stock phrases, and token-loop noise
- if a report, artifact, or summary contains duplicated text that is not grounded in the task, delete it instead of preserving it
- never append repeated success markers or any other unrelated stock text to summaries, metadata, or deliverables

Do:
- propose a refined information architecture inside the 3-page structure
- create reusable components
- improve empty states, loading states, and error states
- improve recommendation grouping and decision support clarity
- improve 今日紀錄 so it feels like a real daily cockpit
- design onboarding and correction flows that feel useful rather than ceremonial

Do not:
- break LIFF auth
- rename backend fields casually
- redesign this into a social app
- turn the recommendation area into a massive searchable catalog
- expose raw L3 hypothesis labels directly to the user

Acceptance target:
- user can open LIFF and immediately understand today's status
- user can log a meal in under 30 seconds
- user can answer a clarification question without friction
- user can decide what to eat from the 食物推薦 page
- onboarding is understandable in under 20 seconds and skippable
- preference correction feels trustworthy and lightweight
- UI feels intentional and shippable
```
