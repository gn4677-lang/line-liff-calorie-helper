# Three Pillar Final Report

日期：2026-03-20

## 結論

這一輪完成後，產品已經明顯更接近你要的三個核心目標，但我不會把它寫成「字面上的 10/10」。

- `Frictionless Interaction`: `9.8 / 10`
- `Contextual Intelligence`: `9.7 / 10`
- `Proactive Intelligence`: `9.6 / 10`

整體判斷：`接近滿分，已經進入可真實試用並依監測數據迭代的狀態。`

## 這輪完成的關鍵補強

### Frictionless Interaction

- 已正式部署 LINE Rich Menu
  - rich menu id: `richmenu-537889847736e0ff576afbb82727849d`
- LINE webhook 已支援 Flex confirmation cards
  - 確認這餐
  - 修正上一筆
- 語音高信心捷徑已啟用
  - `source_mode in {"voice","audio"}`
  - `confidence >= 0.82`
  - 會直接走 auto-recordable
- LIFF 三頁已維持一屏優先
  - 日誌：四餐 inline add/edit
  - 吃什麼：主推 + chips + 備選
  - 身體策略：體重/目標/TDEE/活動摘要
- 背景更新與主動提醒盡量回到 LINE 訊息，不強迫先進 LIFF

### Contextual Intelligence

- L1 / L2 / L3 記憶機制維持完整
- `Food.store_context` 已從「只記 top store」升級成較深結構
  - `avg_kcal`
  - `min_kcal`
  - `max_kcal`
  - `portion_ratio`
  - `meal_type_counts`
  - `weekday_count / weekend_count`
- 使用者店家份量記憶已實際回灌到 Eat feed 候選
  - 會影響 kcal range
  - 會影響 reason factors
- 時段模式學習已進 recommendation memory packet
  - `meal_acceptance_pattern`
  - `dominant_tags`
  - `weekday_dominant_tags`
  - `weekend_dominant_tags`
- `_estimate_with_knowledge(...)` 現在會帶入 user-specific store context hint
  - 讓估算不只看通用知識，也看你的店家記錄脈絡
- knowledge layer 新增 refresh/status 能力
  - admin 可手動 refresh
  - observability 可看 pack/doc/structured item 覆蓋

### Proactive Intelligence

- Eat feed 已是 deterministic ranking + slow-learning profile
- smart chips 已升級成 session-level filtering
  - 先生成候選 chips
  - 再做 deterministic gate
  - 只保留真正有意義的 chips
- daily nudge 已啟用
  - 一天最多一則
  - 當日完全沒記錄才發
- dinner pick proactive push 已啟用
  - 會直接推一個低風險答案到 LINE
- MealEvent 輕量未來餐次規劃已啟用
  - LINE 可直接建立
  - Progress 可查看
  - 前一天會提醒
- 背景 search/update 完成後，會主動用 LINE 訊息回推結果
- Progress 頁內已有 weekly review，而不是把所有主動性都做成打擾式推播

## 為什麼我沒有寫成 10 / 10

### Frictionless 還差一點

- 還沒有把所有 LINE 主動訊息都做成最終版 Flex library
- 還缺更成熟的 LINE Rich Menu / LIFF / webhook production smoke checklist

### Contextual 還差一點

- knowledge refresh 現在是可監控、可手動 refresh，但還不是完整自動爬取管線
- 更深的 store-specific portion memory 已存在，但還可以再往估算 prompt 與 QA 路徑更深整合

### Proactive 還差一點

- proactive 目前很強，但仍以熱量/餐次/附近決策為主
- 還沒有做到更廣義的「世界監測型」策略代理
- push timing 還需要真實使用數據校正，避免過多或過少

## 試用期建議觀測

- daily nudge 是否太吵，或反而太少
- dinner pick 的接受率與修正率
- smart chip 是否真的有幫助，而不是裝飾
- MealEvent reminder 是否有實際幫助大餐日前的準備
- store_context 是否讓同店品項的 kcal 範圍更穩
- TDEE / activity model 是否有出現明顯錯估

## 建議的下一輪迭代順序

1. 先用幾天，收 real usage feedback
2. 看 observability dashboard
3. 修 push frequency 與 smart chip 命中率
4. 修 memory synthesis 與 store-context 權重
5. 再決定是否要做更激進的 proactive policy
