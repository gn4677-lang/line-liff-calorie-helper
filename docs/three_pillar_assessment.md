# 三大智慧支柱評估報告

> 基於對所有 12 個後端服務（約 5,500 行）、AI Provider 層（Builder Space + Heuristic）、3 個前端頁面、知識層的深度審計。

---

## 第一支柱：無縫交互 — 9.0 / 10

> *"以思維速度運行的系統。"*

### 已完成

| 功能 | 檔案 | 狀態 |
|---|---|---|
| LINE 文字/圖片/音訊/影片輸入 | [routes.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/api/routes.py), [line.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/line.py) | 已完成 |
| LIFF 身份驗證與 Token 引導 | [AppContext.tsx](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/frontend/src/AppContext.tsx) | 已完成 |
| 多模態輸入歸一化 | [intake.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/intake.py) | 已完成 |
| 自動確認 + 智慧澄清預算 (quick=1, standard=2, fine=4) | [confirmation.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/confirmation.py) | 已完成 |
| 生活化提問模板 + 份量對比按鈕 | [confirmation.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/confirmation.py) | 已完成 |
| Builder Space 視覺估算 / 語音轉錄 / 混合路由 / LRU 快取 / 自動回退 | [builderspace.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/builderspace.py) | 已完成 |
| Rich Menu 腳本 | [create_line_rich_menu.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/scripts/create_line_rich_menu.py) | 已完成 |

### 差距

| 差距 | 影響 | 難度 |
|---|---|---|
| Rich Menu 未部署至正式 LINE 帳號 | 高 | 低 |
| 語音高置信度 (>0.82) 直接自動記錄 | 中 | 低 |
| LINE Flex Message 確認卡片（取代純文字回覆） | 中 | 中 |

---

## 第二支柱：情境智慧 — 9.5 / 10

> *"將 AI 轉化為你的數位雙生。"*

### 已完成

| 功能 | 檔案 | 狀態 |
|---|---|---|
| L1 信號 / L2 假設 / L3 偏好（三層記憶） | [memory.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/memory.py) | 已完成 |
| 新手引導種子 / 對話修正 / 反對證據處理 | [memory.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/memory.py) | 已完成 |
| 記錄偏差感應 (Reporting Bias) | [intake.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/intake.py) | 已完成 |
| BM25 知識檢索 + 台灣食品目錄 + 品牌卡片 + 包裝啟發式 | [knowledge.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/knowledge.py) | 已完成 |
| 網頁搜尋回退 (DuckDuckGo) | [knowledge.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/knowledge.py) | 已完成 |
| TDEE 自動標定 + 每週偏離檢測 | [body_metrics.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/body_metrics.py), [confirmation.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/confirmation.py) | 已完成 |
| 最愛店家 / 黃金組合 / Google Places | [proactive.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/proactive.py), [google_places.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/google_places.py) | 已完成 |
| Builder Space 落地式估算 / OCR / 混合路由 | [builderspace.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/builderspace.py) | 已完成 |

### 差距

| 差距 | 影響 | 難度 |
|---|---|---|
| 店家專屬份量記憶 ("巷口雞肉飯比連鎖店大 20%") | 高 | 中 |
| 時段模式學習 (週間不吃早餐 / 週末吃大餐) | 中 | 中 |
| 知識包自動更新管線 | 中 | 高 |

---

## 第三支柱：主動智慧 — 7.5 / 10

> *"能預測需求的戰略顧問。"*

### 已完成

| 功能 | 檔案 | 狀態 |
|---|---|---|
| Eat Feed 推薦引擎（多重信號排序 + Smart Chips） | [eat_feed.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/eat_feed.py) | 已完成 |
| 推薦 Profile 自調優 + 歸因追蹤 | [eat_feed.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/eat_feed.py) | 已完成 |
| 硬性厭惡過濾 + 記憶優先推薦 | [eat_feed.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/eat_feed.py) | 已完成 |
| SearchJob 異步精度優化 + 通知系統 | [proactive.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/proactive.py) | 已完成 |
| 附近啟發式 + 快取回退 | [proactive.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/proactive.py) | 已完成 |
| 熱量預算感知推薦 + 解釋因子 | [recommendations.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/recommendations.py), [memory.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/memory.py) | 已完成 |

### 差距

| 差距 | 影響 | 難度 |
|---|---|---|
| **每日一次 LINE 溫和提醒** (整天沒記錄才發一則) | 高 | 低 |
| **大餐事件行事曆** (在頁面上預記錄 → 觸動態調整) | 高 | 中 |
| **爆卡自動偵測 → 事件式恢復建議** (非常駐，觸發才執行) | 高 | 中 |
| **頁面內嵌每週摘要** (在 Progress 頁呈現，不推播打擾) | 中 | 低 |

---

## 總結

| 支柱 | 評分 | 核心優勢 |
|---|---|---|
| 無縫交互 | **9.0/10** | 多模態 + Builder Space 視覺/語音 + 智慧澄清 |
| 情境智慧 | **9.5/10** | L1/L2/L3 記憶 + 深層知識檢索 + TDEE 自動感知 |
| 主動智慧 | **7.5/10** | Eat Feed 排序引擎 + 自調式 Profile |
| **總體** | **8.7/10** | |

---

## 邁向 10 分的改善計畫

### 第一階段：快速獲勝 (各 1-2 天)

1. **部署 Rich Menu** 至正式 LINE 帳號
   - 運行 [create_line_rich_menu.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/scripts/create_line_rich_menu.py)，驗證 LIFF URL 連通性

2. **LINE Flex Message 確認卡片**
   - 將純文字確認改為視覺化 Flex 卡片（解析項目 + 熱量區間 + 確認/編輯按鈕）
   - 修改 [line.py](file:///C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/line.py)，新增 `send_flex_confirm_card`

3. **語音自動記錄捷徑**
   - Webhook 端：`confidence >= 0.82` 且來源為語音 → 跳過澄清直接確認

4. **Progress 頁內嵌每週摘要**
   - 在現有 ProgressPage 新增「本週回顧」區塊
   - 資料：7 天平均熱量、體重差、趨勢、1 個洞察
   - **不推播、不打擾**，用戶自己打開頁面才看到

### 第二階段：事件驅動的主動策略 (各 3-5 天)

5. **每日一次溫和 LINE 提醒**
   - 晚間 8 點檢查：若當天完全沒有任何記錄 → 發一則 LINE 訊息
   - 語氣溫和："今天好像還沒記錄，要補一下嗎？"
   - **一天最多一則，不重複打擾**
   - 新增 `services/daily_nudge.py`

6. **大餐事件行事曆（輕量版）**
   - 在三個頁面（Today / Eat / Progress）擇一新增「預記錄大餐」入口
   - 用戶可預先標記某天有大餐（例：週五晚餐聚餐）
   - 系統自動觸發動態調整：計算當天前後的熱量分配建議
   - 新增 `MealEvent` Model + 前端簡易日期選擇器
   - **不是完整行事曆，只紀錄「大餐事件」**

7. **爆卡自動偵測 → 事件式恢復建議**
   - 偵測條件：當日攝取超過目標 40% 以上
   - 觸發行為：生成溫和的 2 天補償 Overlay
   - 在 Today 頁面顯示："昨天多了 400 卡，接下來兩天各減 200 即可"
   - **非常駐功能，觸發才顯示、2 天後自動消逝**

### 第三階段：深度個人化 (各 5-7 天)

8. **店家專屬份量記憶**
   - `Food` 模型新增 `store_context`
   - 同一店家記錄兩次以上 → 建立店家專屬錨點
   - 未來估算優先參考此錨點

9. **時段模式學習**
   - 聚合 L1 信號 by 星期 × 餐別
   - 生成 L2 假設（"平日不吃早餐型" / "週末早午餐愛好者"）
   - 回饋至 Smart Chip 排序與提醒時機

10. **知識包自動更新管線**
    - 定期爬取超商官網商品頁
    - 自動更新 JSON Pack + 失效 lru_cache
