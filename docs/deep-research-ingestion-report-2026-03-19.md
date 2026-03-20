# Deep Research Ingestion Report

Date: 2026-03-19

## Source Folder

- `C:\Users\exsaf\Desktop\新增資料夾`

## Source Files Reviewed

| File | Main Theme | Best Target in Knowledge Pack |
| --- | --- | --- |
| `deep-research-report.md` | 份量語彙、熱量估算思維、追問模板 | `portion_anchors.json`, `dialogue_policies.md` |
| `deep-research-report (1).md` | 台灣口語、句型、模糊說法、alias 與標註欄位 | `food_language_tw.md`, `food_catalog_tw.json` aliases |
| `deep-research-report (2).md` | 外食減脂決策、情境判斷、可偶爾吃清單 | `external_eating_decision_rules.md`, `nutrition_rules.md`, `nutrition_faq.md` |
| `deep-research-report (3).md` | 減脂營養指標、蛋白質/飽足/油糖風險、知識治理 | `nutrition_rules.md`, `knowledge-pack-spec.md` |
| `deep-research-report (4).md` | 高頻外食品項、熱量區間、代換與公式 | `food_catalog_tw.json`, `portion_anchors.json` |
| `deep-research-report4.md` | 台北場景、商圈/站點、店家類型、產品優先順序 | `taipei_eating_scenarios.md`, proactive recommendation logic |

## What Was Converted

### Structured Data

- Expanded [food_catalog_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/food_catalog_tw.json)
  - Added high-frequency Taiwanese foods, drinks, bento items, and hotpot templates
  - Added aliases, category, serving size, risk flags, and notes
- Expanded [portion_anchors.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/portion_anchors.json)
  - Added rice, protein, oil, drink, dumpling, bento, and soup anchors

### Rule Docs

- Rewrote [nutrition_rules.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/nutrition_rules.md)
- Rewrote [nutrition_faq.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/nutrition_faq.md)
- Rewrote [dialogue_policies.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/dialogue_policies.md)
- Added [food_language_tw.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/food_language_tw.md)
- Added [external_eating_decision_rules.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/external_eating_decision_rules.md)
- Added [taipei_eating_scenarios.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/taipei_eating_scenarios.md)

### Brand Cards

- Added [7-eleven.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/brand_cards/7-eleven.md)
- Added [mcdonalds-taiwan.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/brand_cards/mcdonalds-taiwan.md)
- Added [mos-burger-taiwan.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/brand_cards/mos-burger-taiwan.md)
- Added [chun-shui-tang.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/brand_cards/chun-shui-tang.md)
- Added [pizza-hut-taiwan.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/brand_cards/pizza-hut-taiwan.md)

## How The App Uses This Pack

### 1. Structured Food Lookup

- [knowledge.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/knowledge.py) now tries `food_catalog_tw.json` first.
- This is best for:
  - `滷肉飯大概多少卡`
  - `珍奶會不會爆`
  - `雞腿便當穩不穩`

### 2. Local BM25 Retrieval

- All `knowledge/*.md` and `knowledge/*.json` are loaded into the local document index.
- This is best for:
  - rule-based QA
  - Taiwan food language understanding
  - Taipei scene and recommendation context
  - policy and coaching wording

### 3. Suggested Update / Async Research Support

- `build_suggested_update_packet()` can now use richer food cards as local anchors before falling back to web search.
- This helps:
  - brand/menu precision
  - smarter provisional update suggestions
  - tighter local-first answers

## Recommended Future Ingestion Rule

When you do more deep research, do not paste the raw dump directly into `knowledge/`.

Instead, convert each finding into one of these buckets:

- Food cards
- Portion anchors
- Nutrition rules
- FAQ
- Dialogue policies
- Brand cards
- Taipei/location scene docs

If a finding is:

- stable
- reusable
- not tied to a single temporary menu item

then it belongs in the permanent knowledge pack.

If it is:

- brand-new
- highly time-sensitive
- tied to one specific campaign or post

then it should stay in search fallback or become a short-lived brand card update.
