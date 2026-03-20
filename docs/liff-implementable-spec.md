# AI 減脂操作系統 — LIFF 可實作 Spec

> 本文件合併 [ux-interaction-design-report.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/ux-interaction-design-report.md) 與 [ui-design-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/ui-design-spec.md)，並以目前 repo 的 backend contract、資料模型與 LIFF 現況為基礎重寫成單一 implementation spec。
>
> 這份文件是三頁 LIFF 的 source of truth。原本兩份文件保留作設計參考，但不再各自演化。

---

## 1. 系統重新定義

這個系統不是單純的熱量記錄 app，而是由 4 個協作層組成：

1. `LINE chat`
   - 捕獲現實
   - 快速記錄食物
   - 問最少必要追問
   - 處理一句話修正
2. `LIFF Today`
   - 管理今天的真相狀態
   - 解決未完成草稿
   - 看今天剩多少
   - 處理今天相關的 async 更新
3. `LIFF Eat`
   - 幫你做下一餐決策
   - 顯示少量可行選項
   - 把 location / favorite store / golden order 納入選擇
4. `LIFF Progress`
   - 看這週是否在軌道上
   - 記體重
   - 做週級的溫和調整與補償決策

系統底層由 5 類能力支撐：

- `confirmation engine`
  - 決定 `auto_recordable / needs_clarification / needs_confirmation / correction_preview`
- `deterministic calorie math`
  - 今日剩餘、每週 drift、overlay 分配
- `memory system`
  - `preferences / memory_signals / memory_hypotheses`
- `proactivity system`
  - `saved_places / favorite_stores / golden_orders / search_jobs / notifications`
- `knowledge + refinement`
  - 菜單比對、品牌 grounding、video refinement、nutrition QA

## 2. 產品範圍

### 2.1 v1 目標

v1 要做到：

- 使用者願意每天打開
- 模糊食物能在低摩擦下收斂到可接受估算
- 使用者可以很快知道今天還剩多少
- 不知道吃什麼時，Eat 頁真的有幫助
- 大餐前後有一個溫和、可信的調整介面

### 2.2 v1 不追求

v1 不追求：

- 醫療級熱量精準度
- 完整大型餐廳資料庫
- 持續背景定位
- 商業化大眾版資訊架構
- 完整 macro / micronutrient 分析
- 把每一個動作都做成獨立 surface

## 3. 實作約束

### 3.1 必須遵守

- 以目前 backend contract 為地基，不任意重造 API。
- LIFF first，桌機瀏覽器 second。
- mobile-first，重點是單手可操作與短流程完成。
- 任何 async 精修都不能 silent overwrite 已確認紀錄。
- 三頁分工必須明確，不做 single super dashboard。

### 3.2 現有 backend 已提供

- `GET /api/day-summary`
- `POST /api/intake`
- `POST /api/intake/video`
- `POST /api/intake/{draft_id}/clarify`
- `POST /api/intake/{draft_id}/confirm`
- `PATCH /api/meal-logs/{log_id}`
- `GET /api/recommendations`
- `POST /api/recommendations/nearby`
- `POST /api/location/resolve`
- `POST /api/weights`
- `POST /api/plans/day`
- `POST /api/plans/compensation`
- `GET /api/onboarding-state`
- `POST /api/preferences/onboarding`
- `POST /api/onboarding/skip`
- `GET /api/preferences`
- `POST /api/preferences`
- `POST /api/preferences/correction`
- `GET /api/memory/profile`
- `GET /api/saved-places`
- `POST /api/saved-places`
- `GET /api/favorite-stores`
- `POST /api/favorite-stores`
- `GET /api/notifications`
- `POST /api/notifications/{id}/read`
- `GET /api/search-jobs/{job_id}`
- `POST /api/search-jobs/{job_id}/apply`
- `POST /api/search-jobs/{job_id}/dismiss`
- `POST /api/attachments`
- `POST /api/qa/nutrition`

### 3.3 目前 contract gap

以下是會影響前端資訊架構，但目前 backend 尚未完整暴露的資料：

- `day-summary` 沒有 `latest_weight` 與 `has_today_weight`
- `plans/compensation` 目前偏向「產出選項」，還沒有明確的「使用者選了哪個 option 並套用」contract
- `recommendations` 目前只有 `meal_type` query，還沒有正式支援 `style / time_context / location_context`
- `plan_events` 沒有 dedicated list / create / update API
- `favorite store / golden order` 沒有直接寫入 `meal_log` 的專用 endpoint

本 spec 會把這些地方標成：

- `v1 fallback`
- `P2 enhancement`

## 4. Surface Ownership

每個主動任務只有一個 home。其他 surface 只能做 teaser、handoff 或 read-only preview。

| Surface | 核心問題 | 是主場的任務 | 不該承擔 |
|---|---|---|---|
| `LINE chat` | 我剛剛吃了什麼？你現在要我補哪一句？ | capture、短追問、修正 preview、quick reply、未來事件 probe | 長規劃 workspace、密集瀏覽 UI |
| `Today` | 我今天吃了什麼？還剩多少？哪件事卡住？ | active draft、clarify、confirm、meal timeline、today async updates | 大量推薦瀏覽、週趨勢分析 |
| `Eat` | 我現在可以吃什麼？去哪裡拿？ | recommendation browse、location choice、nearby、favorite stores、golden orders | 週級 recovery 決策、長期 trend 解讀 |
| `Progress` | 我這週有在軌道上嗎？要不要溫和修正？ | weight trend、weekly drift、overlay、weekly recovery decision | 當餐追問、附近店家瀏覽 |

### 4.1 關於規劃的明確規則

- `Eat` 可以顯示「今日餐配 preview」，因為它直接影響下一餐選擇。
- `Eat` 不負責接受補償方案，也不負責多日規劃提交。
- `Progress` 才是 recovery / weekly adjustment 的決策 home。

### 4.2 關於記錄的明確規則

- 真正寫入餐點的 home 是 `Chat + Today intake pipeline`。
- `Eat` 上的推薦卡只能做：
  - 開外部地圖
  - 帶入 Today composer
  - 帶回 chat 作為建議輸入
- `Eat` 不直接新增 `meal_log`。

## 5. 核心資料模型

| 物件 | 目前資料來源 | 用途 |
|---|---|---|
| `users` | `backend/app/models.py` | 綁 LINE 身分與每日目標 |
| `preferences` | `preferences` table | onboarding + 明確偏好 |
| `meal_drafts` | `meal_drafts` table | intake 中間態 |
| `meal_logs` | `meal_logs` table | 已確認餐點 |
| `weight_logs` | `weight_logs` table | 體重趨勢 |
| `plan_events` | `plan_events` table | overlay 與未來事件預留 |
| `memory_signals` | `memory_signals` table | 重複模式 |
| `memory_hypotheses` | `memory_hypotheses` table | 穩定假設 |
| `saved_places` | `saved_places` table | Eat location context |
| `favorite_stores` | `favorite_stores` table | 常去店家 |
| `golden_orders` | `golden_orders` table | 穩定低風險選項 |
| `search_jobs` | `search_jobs` table | nearby、menu precision、video precision |
| `notifications` | `notifications` table | async 事件回流 UI |

### 5.1 Draft / Log 狀態

- `meal_drafts.status`
  - `draft`
  - `awaiting_clarification`
  - `ready_to_confirm`
  - `confirmed`
- `draft_context.confirmation_mode`
  - `auto_recordable`
  - `needs_clarification`
  - `needs_confirmation`
  - `correction_preview`

### 5.2 Summary 是三頁共同基礎資料

`GET /api/day-summary` 目前提供：

- `target_kcal`
- `consumed_kcal`
- `remaining_kcal`
- `logs`
- `seven_day_average_weight`
- `fourteen_day_direction`
- `target_adjustment_hint`
- `weekly_target_kcal`
- `weekly_consumed_kcal`
- `weekly_remaining_kcal`
- `weekly_drift_kcal`
- `weekly_drift_status`
- `should_offer_weekly_recovery`
- `recovery_overlay`
- `pending_async_updates_count`

這代表 Today / Eat / Progress 都應共用同一份 summary store，而不是各自重新推導。

## 6. 全域流程

### 6.1 Boot Flow

1. `GET /api/client-config`
2. 初始化 LIFF
3. `GET /api/me`
4. 平行載入：
   - `GET /api/onboarding-state`
   - `GET /api/day-summary`
   - `GET /api/recommendations`
   - `GET /api/notifications`
5. 決定首屏：
   - 有 onboarding -> onboarding modal
   - 無 onboarding -> `Today`

### 6.2 Onboarding Flow

onboarding 不負責 location，不負責所有偏好，只負責最先影響 intake / recommendation / planning 的 5 題：

1. `breakfast_habit`
2. `carb_need`
3. `dinner_style`
4. `hard_dislikes`
5. `compensation_style`

location setup 採 progressive setup，不放 onboarding。

### 6.3 Meal Logging Flow

1. 使用者在 chat 或 Today 輸入文字 / 圖片 / 音訊 / 影片
2. `POST /api/intake` 或 `POST /api/intake/video`
3. backend 回傳 `DraftResponse`
4. 前端依 `confirmation_mode` 呈現：
   - `auto_recordable`
   - `needs_clarification`
   - `needs_confirmation`
   - `correction_preview`
5. 如果需要追問 -> `POST /api/intake/{draft_id}/clarify`
6. 如果需要確認 -> `POST /api/intake/{draft_id}/confirm`

### 6.4 Async Update Flow

1. intake / nearby / video refinement 可能建立 `search_job`
2. UI 在需要時：
   - poll `GET /api/search-jobs/{job_id}`
   - 或讀 `GET /api/notifications`
3. 如果背景結果生成 `suggested_update`
4. 使用者在 Today inbox 或 inline card 上做：
   - `POST /api/search-jobs/{job_id}/apply`
   - `POST /api/search-jobs/{job_id}/dismiss`

### 6.5 Nearby Flow

1. 使用者進入 Eat
2. 先選 location context：
   - current area
   - destination
   - saved place
   - manual input
3. `POST /api/location/resolve` 或直接 `POST /api/recommendations/nearby`
4. 先顯示 heuristic shortlist
5. 若有 `search_job_id`，背景補更多 places

### 6.6 Weekly Recovery Flow

1. `day-summary.should_offer_weekly_recovery = true`
2. Progress 顯示 `WeeklyRecoveryCard`
3. `POST /api/plans/compensation` 先取得 options 與 coach message
4. v1 把它當成 decision support preview
5. P2 再補「依使用者選項套用 overlay」的明確 contract
6. overlay 實際建立後，Today / Progress 從 `recovery_overlay` 呈現「補償中」

## 7. 全域 UI 規格

### 7.1 視覺方向

採用暖色暗底，不做科技 demo 風。

### 7.2 Design Tokens

建議 tokens：

| Token | Value | 備註 |
|---|---|---|
| `--bg-primary` | `#12131a` | 主背景 |
| `--bg-card` | `#1c1f2a` | 卡片背景 |
| `--bg-card-elevated` | `#232738` | draft / modal / overlay |
| `--accent-warm` | `#f0a030` | 主要 CTA |
| `--accent-warm-soft` | `rgba(240,160,48,0.14)` | glow / selected bg |
| `--text-primary` | `#f4f5f8` | 主文字 |
| `--text-secondary` | `#b2b7c8` | 次文字 |
| `--text-muted` | `#8a90a6` | 佔位與輕標註，避免過低對比 |
| `--success` | `#39c58d` | on-track / confirmed |
| `--warning` | `#f4be3d` | rough / pending |
| `--danger` | `#ef6d6d` | over target |
| `--info` | `#6fb2ff` | nearby / async info |

### 7.3 字型

- 主字型：`Inter`, `Noto Sans TC`, `sans-serif`
- 數字：`DM Mono`, `JetBrains Mono`, `monospace`
- 最小可見字級：
  - 正文 `14px`
  - caption `12px`
  - 不使用 `10px` 作主要資訊

### 7.4 全域元件

- `BottomTabBar`
  - 順序：`Today / Eat / Progress`
- `CoachBanner`
  - 顯示最近一次 `coach_message`
- `InboxButton`
  - 顯示 `pending_async_updates_count`
  - 點開 `NotificationsSheet`
- `NotificationsSheet`
  - 讀 `GET /api/notifications`
  - 顯示 unread first
- `Loading`
  - skeleton，不用 spinner 當主狀態
- `Error`
  - 溫和文案 + retry
- `Offline`
  - 顯示 cache 與同步提示

### 7.5 互動規則

- 任何 chip 都必須可 wrap，不做橫向 scroll 當主要交互。
- 任何只有一個最合理動作的情境，只顯示一個主 CTA。
- 任何會覆寫資料的動作都要讓使用者明確按一次。
- Animation 只做：
  - page enter
  - card reveal
  - chip select
  - confirm success

## 8. Today Spec

### 8.1 頁面目標

回答：

- 我今天吃了什麼？
- 還剩多少？
- 哪件事還沒處理完？
- 下一步最該做什麼？

### 8.2 資料依賴

- `GET /api/day-summary`
- `draft` local state
- `GET /api/notifications`
- `GET /api/search-jobs/{job_id}` when needed

### 8.3 版面順序

| 區塊 | 顯示條件 | 內容 | 動作 | 資料來源 |
|---|---|---|---|---|
| `TodayTopStrip` | 永遠 | consumed / remaining / target / weekly drift / overlay badge | 開 inbox | `summary` |
| `ActiveDraftCard` | 有 draft 時 | kcal、range、uncertainties、追問、chips、confirm buttons | clarify / confirm / force confirm | `draft` |
| `QuickAddComposer` | 沒 draft 時 | 文字輸入、附件上傳、meal type、mode | create intake | `/api/intake`, `/api/attachments`, `/api/intake/video` |
| `PendingAsyncUpdatesCard` | 有 unread async update 時 | update count、最近一筆建議摘要 | open inbox 或直接 apply/dismiss | `/api/notifications`, `/api/search-jobs/*` |
| `MealTimeline` | 永遠 | 今日 log list | edit log | `summary.logs`, `PATCH /api/meal-logs/{id}` |
| `RecoveryOverlayBar` | overlay active | 今日調整後預算、到期日、原因 | 跳 Progress | `summary.recovery_overlay` |
| `NextStepCard` | 永遠 | 只顯示一個最合理下一步 | open Eat / open Progress / scroll to draft | local decision from `summary + draft + notifications` |

### 8.4 Top Strip 與 Hero 規則

Today 不做固定大型 hero ring。

改成雙態：

- `有未解決草稿或 pending async update`
  - 只顯示 compact sticky `TopStrip`
- `沒有未解決狀態`
  - 可以在 `TopStrip` 下顯示中型 hero summary

原因：

- Today 首屏優先級應該是解決未完成任務，不是看大視覺裝飾。
- 在 LIFF webview 中，草稿卡與追問卡要優先占首屏。

### 8.5 Active Draft Card

必備元素：

- `meal_type`
- `parsed_items`
- `estimate_kcal`
- `kcal_low / kcal_high`
- `primary_uncertainties`
- `confirmation_mode`
- `followup_question`
- `answer_mode`
- `answer_options`

互動規則：

- `needs_clarification`
  - 顯示一題問題
  - 如果 `answer_mode = chips_first_with_text_fallback`，先顯示 chips，再提供自由輸入
- `needs_confirmation`
  - 不再問更多題
  - 主文案明確說明是 generic portion estimate
- `auto_recordable`
  - 如果 backend 已經回傳 `log`，Today 直接顯示成功狀態，不再卡在草稿卡
- `correction_preview`
  - 顯示 old kcal / new kcal / overwrite 說明

### 8.6 Meal Timeline

每筆 log 必顯示：

- `meal_type`
- `description_raw`
- `kcal_estimate`
- `confidence` badge
- async update applied marker

v1 編輯方式：

- 點 `修改`
- 打開簡單 edit sheet
- `PATCH /api/meal-logs/{log_id}`

### 8.7 Today 不包含

- nearby 搜尋結果列表
- grouped recommendation browse
- 14 天折線圖
- weekly recovery decision buttons

## 9. Eat Spec

### 9.1 頁面目標

回答：

- 我現在可以吃什麼？
- 在哪裡拿最方便？
- 哪個選項最穩？

### 9.2 資料依賴

- `GET /api/recommendations`
- `POST /api/recommendations/nearby`
- `POST /api/location/resolve`
- `GET /api/saved-places`
- `POST /api/saved-places`
- `GET /api/favorite-stores`
- `POST /api/favorite-stores`
- `GET /api/search-jobs/{job_id}`
- `GET /api/day-summary`
- `POST /api/plans/day`

### 9.3 版面順序

| 區塊 | 顯示條件 | 內容 | 動作 | 資料來源 |
|---|---|---|---|---|
| `ContextChooser` | 永遠 | meal type、time context、location context、style chips | refresh recommendation state | local UI + summary |
| `FastRecommendationRail` | 有推薦時 | 3-5 個最可行選項 | open detail / 帶去 Today | `/api/recommendations` |
| `FavoriteStoresSection` | 有資料時 | favorite stores + golden orders | open maps / save store / 帶去 Today | `/api/favorite-stores` |
| `NearbySection` | 啟動後 | heuristic items + search state | search nearby / open maps / save place | `/api/recommendations/nearby`, `/api/search-jobs/{id}` |
| `RecommendationGroups` | 有資料時 | grouped recommendations | 展開查看理由 | `/api/recommendations` |
| `DayBudgetPreview` | 可選 | breakfast / lunch / dinner / flex allocation | 前往 Progress 調整 | `/api/plans/day`, `summary.recovery_overlay` |

### 9.4 ContextChooser

v1 支援：

- `meal_type`
  - breakfast / lunch / dinner / snack
- `time_context`
  - now / later
- `location_context`
  - current area
  - destination
  - saved place
  - manual input
- `style`
  - 最穩
  - 最方便
  - 想吃爽一點
  - 高蛋白優先

contract 說明：

- `meal_type` 是目前唯一直接進 `/api/recommendations` 的 filter
- `location_context` 主要用於 `/api/recommendations/nearby`
- `time_context` 與 `style` 在 v1 可先作為前端排序 / 分組偏好，不要求 backend 立即新增參數
- 若未來要讓 style 真正改變推薦候選，需要擴 `GET /api/recommendations`

location setup 是 progressive：

- 第一次 nearby 時，如果沒有 saved place，就引導建立
- 不把住家 / 公司放進 onboarding

### 9.5 FastRecommendationRail

只顯示前 3-5 個最可行項。

每張卡至少顯示：

- name
- kcal low-high
- group
- 1 句短 reason
- `favorite` / `golden` marker

卡片 CTA：

- `看細節`
- `帶去 Today`
- `打開地圖` 如果有 external link

不直接寫 `meal_log`。

### 9.6 Favorite Stores / Golden Orders

這一區是 Eat 的一級區塊，不藏在設定。

顯示來源：

- `favorite_stores`
- `golden_orders`

每筆至少顯示：

- 店名
- 穩定點餐組合或標題
- kcal range
- 最近使用感
- Maps link

v1 CTA：

- `帶去 Today`
- `打開地圖`

若未來要做「一鍵記錄」，需要新增專用 endpoint 或明確的 client-side prefill contract；本 spec 先不假設後端已存在。

### 9.7 Nearby

Nearby 是雙階段：

1. 即時 heuristic shortlist
2. 背景 `nearby_places` job 補更完整結果

呈現規則：

- loading 時先顯示 heuristic items，不等 Places 完整回來
- 結果 item 顯示：
  - store name
  - distance / travel minutes
  - open status
  - suggested item
  - kcal range
  - reason_factors
  - external link
- 如果 job 完成並有更好結果，更新列表或發通知

### 9.8 Day Budget Preview

Eat 只做 read-only preview：

- breakfast allocation
- lunch allocation
- dinner allocation
- flex
- overlay aware target

CTA 只有：

- `去 Progress 調整`

Eat 不顯示補償方案選項按鈕。

### 9.9 Eat 不包含

- active draft clarify UI
- full meal timeline
- weekly recovery decision list
- 14 天體重趨勢圖

## 10. Progress Spec

### 10.1 頁面目標

回答：

- 我這週有在正確軌道上嗎？
- 是否需要微調？
- 現在要不要啟動溫和 recovery？

### 10.2 資料依賴

- `GET /api/day-summary`
- `POST /api/weights`
- `POST /api/plans/compensation`
- `GET /api/memory/profile`

### 10.3 版面順序

| 區塊 | 顯示條件 | 內容 | 動作 | 資料來源 |
|---|---|---|---|---|
| `WeeklyStatusHero` | 永遠 | 7d avg、14d direction、weekly drift、status，若未來有 latest weight 一併顯示 | 無 | `summary` |
| `WeightCaptureCard` | v1 fallback：永遠顯示；P2：只在當日未記體重時顯示 | number input | log weight | `/api/weights` |
| `TrendCard` | 永遠 | 體重與熱量趨勢摘要、coach hint | 無 | `summary` |
| `WeeklyRecoveryCard` | `should_offer_weekly_recovery = true` 或 overlay active | compensation options preview / current overlay | request compensation | `/api/plans/compensation` |
| `LoggingQualityCard` | 可選 | 為什麼最近可能多問幾題 | open detail 不必要 | `memory_profile.reporting_bias` |

### 10.4 WeeklyStatusHero

顯示：

- `seven_day_average_weight`
- `fourteen_day_direction`
- `weekly_target_kcal`
- `weekly_consumed_kcal`
- `weekly_drift_kcal`
- `weekly_drift_status`

若未來 backend 補 `latest_weight`，則加到 hero 第一順位。

狀態標籤：

- `on_track`
- `slightly_over`
- `meaningfully_over`
- `meaningfully_under`

### 10.5 Weight Capture

目前 `day-summary` 沒有 `has_today_weight`，因此 v1 fallback 採：

- Progress 永遠顯示簡潔 weight input
- 使用者提交後用成功狀態與 banner feedback 降低重複輸入

P2 若 backend 補 `has_today_weight` 或 latest weight contract，再改成條件式顯示。

輸入卡內容：

- 單欄數字輸入
- 主 CTA `記錄`

記錄後刷新 `summary`。

### 10.6 TrendCard

v1 不要求重圖表庫也能上線。

最少要有：

- 14 天體重方向摘要
- 7 天平均
- 一段 `target_adjustment_hint`

如果要畫圖：

- 體重：14 天折線
- 熱量：7 天 adherence / drift 標示

但文字摘要優先於炫圖。

### 10.7 WeeklyRecoveryCard

這是 Progress 的主決策卡。

顯示條件：

- `summary.should_offer_weekly_recovery = true`
- 或 `summary.recovery_overlay != null`

v1 實作方式：

1. `POST /api/plans/compensation` 取得 options 與 coach message
2. 先把它當成 preview / recommendation UI
3. 若要真正依照使用者所選 option 套用 overlay，需要新增明確 apply contract

P2 enhancement：

- 新增 `selected_option` 或 dedicated apply endpoint
- 讓使用者真的能選 `回到正常 / 小幅回收 / 分 2-3 天`
- 套用後由 Today / Progress 從 `summary.recovery_overlay` 反映「補償中」

### 10.8 LoggingQualityCard

這張卡不是責備，而是 explainability：

- 最近紀錄較完整 -> 系統可少問
- 最近紀錄偏模糊 -> 系統可能多問一題

顯示來源：

- `GET /api/memory/profile`
  - `reporting_bias`
  - `communication_profile`

v1 只顯示溫和描述，不顯示 raw score。

### 10.9 Progress v1 不包含

- nearby 搜尋
- grouped recommendations
- active clarification card
- future event CRUD UI

## 11. Async Jobs 與通知回流

### 11.1 支援的 job types

- `nearby_places`
- `menu_precision`
- `brand_lookup`
- `external_food_check`
- `video_precision`

### 11.2 通知類型

- `async_update`
- `nearby_update`
- `video_update`

### 11.3 UI 呈現規則

| 類型 | 首要 surface | 呈現方式 |
|---|---|---|
| meal precision / video refinement | `Today` | inline update card + inbox |
| nearby update | `Eat` | nearby 區塊刷新 + inbox |
| 其他系統通知 | 全域 inbox | sheet 列表 |

### 11.4 Apply / Dismiss 規則

- 任何 `suggested_update` 都必須顯示：
  - 原 kcal
  - 建議 kcal
  - 差值
  - reason
  - sources
- `Apply`
  - `POST /api/search-jobs/{job_id}/apply`
- `Dismiss`
  - `POST /api/search-jobs/{job_id}/dismiss`

## 12. API 與畫面對應表

| 功能 | Endpoint | 主要畫面 |
|---|---|---|
| 載入今日狀態 | `GET /api/day-summary` | Today / Eat / Progress |
| 建立 intake draft | `POST /api/intake` | Today / chat handoff |
| 建立 video intake | `POST /api/intake/video` | Today |
| 追問回答 | `POST /api/intake/{draft_id}/clarify` | Today / chat |
| 確認草稿 | `POST /api/intake/{draft_id}/confirm` | Today |
| 修改既有 log | `PATCH /api/meal-logs/{log_id}` | Today |
| 記體重 | `POST /api/weights` | Progress |
| 一般推薦 | `GET /api/recommendations` | Eat |
| 附近推薦 | `POST /api/recommendations/nearby` | Eat |
| 解析 location | `POST /api/location/resolve` | Eat |
| 今日餐配 preview | `POST /api/plans/day` | Eat |
| 週補償方案 | `POST /api/plans/compensation` | Progress |
| onboarding | `GET /api/onboarding-state` / `POST /api/preferences/onboarding` / `POST /api/onboarding/skip` | boot modal |
| preferences | `GET /api/preferences` / `POST /api/preferences` / `POST /api/preferences/correction` | settings / chat correction |
| memory profile | `GET /api/memory/profile` | Progress / settings |
| saved places | `GET/POST /api/saved-places` | Eat |
| favorite stores | `GET/POST /api/favorite-stores` | Eat |
| async inbox | `GET /api/notifications` / `POST /api/notifications/{id}/read` | global inbox |
| search job detail | `GET /api/search-jobs/{job_id}` | Today / Eat |
| apply/dismiss async update | `POST /api/search-jobs/{job_id}/apply` / `dismiss` | Today / Eat |
| upload attachment | `POST /api/attachments` | Today |
| nutrition QA | `POST /api/qa/nutrition` | chat first，LIFF secondary |

## 13. 實作優先級

### P0

- LIFF boot + auth + onboarding modal
- Today:
  - TopStrip
  - QuickAddComposer
  - ActiveDraftCard
  - MealTimeline
  - NextStepCard
- Eat:
  - ContextChooser
  - FastRecommendationRail
  - RecommendationGroups
- Progress:
  - WeeklyStatusHero
  - WeightCaptureCard
  - TrendCard 文字摘要版

### P1

- NotificationsSheet
- PendingAsyncUpdatesCard
- NearbySection
- FavoriteStoresSection + GoldenOrders
- RecoveryOverlayBar
- WeeklyRecoveryCard preview 版
- LoggingQualityCard
- video upload + pending refinement state

### P2

- richer chart rendering
- place management UI polish
- correction preview 專用 sheet
- nutrition QA LIFF 入口
- memory profile 設定頁
- exact compensation apply contract

### P3

- plan events CRUD UI
- future event calendar-style planning
- direct golden-order auto-log API

## 14. 明確不採用的設計

- 不把 Today 做成固定大型 hero ring 首屏。
- 不在 Eat 放 recovery 決策按鈕。
- 不在 onboarding 問住家 / 公司 / 常去地點。
- 不假設 favorite store / golden order 已可直接寫入 `meal_log`。
- 不在任何 async refinement 中 silent overwrite。

## 15. 與現有 prototype 的主要差異

目前 [App.tsx](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/frontend/src/App.tsx) 還是 prototype shell，與本 spec 的差異如下：

- tabs 順序應改為 `Today / Eat / Progress`
- Eat 目前混入補償決策；正式版要移到 Progress
- Today 目前還沒有 inbox / async update UI
- Progress 目前只有基本體重與提示；正式版要補 weekly control 結構
- favorite stores、saved places、nearby search、notifications、video intake 雖然 backend 已存在，但 frontend 尚未接上

---

> 一句話總結：
> `Chat` 負責捕獲與問一句，`Today` 負責把今天收斂成可執行真相，`Eat` 負責做下一餐選擇，`Progress` 負責週級校正。這份 spec 的目的是讓 frontend、backend、interaction 不再各講各的版本。
