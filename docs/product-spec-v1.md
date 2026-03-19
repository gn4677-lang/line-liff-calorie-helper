# AI 減脂操作系統 v1 Spec Snapshot

- Source: user-authored working spec from this thread
- Date captured: 2026-03-19
- Status: draft baseline for implementation reviews

## Builder Space context

```bash
codex mcp add ai-builders-coach --env AI_BUILDER_TOKEN=sk_live_your_actual_token_here -- npx -y @aibuilders/mcp-coach-server@latest
```

## AI 減脂操作系統

### 自用完美版 v1 Final Spec

#### 1. 產品定位

這不是一般的熱量記錄 app。  
它是你的 AI 減脂操作系統。

核心任務只有三件事：

1. 幫你把真實世界很模糊的飲食，收斂到「足以估算」
2. 幫你記住你自己真正願意吃的黃金選項
3. 在你要做飲食決策的時候，主動幫你規劃、提醒、推薦

它不是要給很多選項。  
而是要幫你找到、記住、重用那幾個你真的會吃、又不容易破功的選項。

#### 2. v1 產品目標

這版先只追求一件事：

比你現在的 MyFitnessPal + ChatGPT workflow 更順、更可信、更能幫你做決策。

成功標準：

- 你願意每天打開
- 模糊食物能估到你信任的程度
- 你看得到今天還剩多少熱量
- 你不知道吃什麼時，真的會看它
- 聚餐前後、爆卡後，你真的會拿它來討論安排

#### 3. v1 不做什麼

這版先不做：

- 大眾化商業版最佳化
- 大型餐廳資料庫
- 深度 Google Maps / Foodpanda API 整合
- 多人使用
- 完整 macro / micronutrient 分析
- 醫療級精準估算
- 社群功能
- Marketplace

這版只做：你自己真的會用的版本。

#### 4. 核心產品原則

##### 原則 1：自然輸入，逐步確認，到可估算為止

使用者不用先結構化輸入。  
可以先用照片、語音、自然語言描述。

系統要自己判斷：

- 現在可不可以估
- 還差哪個資訊
- 最少要問哪一題

##### 原則 2：不是要求精準回報，而是收斂到夠用

不追求營養師等級。  
追求的是：夠可信、夠穩定、夠能支援減脂決策。

##### 原則 3：先排除不可能，再呈現可行選項

推薦頁不靠複雜排序。  
主要先用：

- 熱量限制
- 餐別
- 可得性 / 地點
- 個人接受度

把候選縮到少量可行選項。

##### 原則 4：重點不是資料庫大，而是記住使用者自己會吃的東西

第一版最重要的是「黃金選項」，不是全世界食物。

##### 原則 5：允許真實世界的不完美

支援：

- 沒吃完
- 分食
- 合菜
- 預支
- 補償
- 今天爆了
- 後天要吃到飽

#### 5. 頁面架構

v1 只有 3 頁。

##### Page 1：體重與熱量目標

處理：

- 今日體重
- 體重趨勢
- 每日熱量目標
- 是否該微調熱量
- 長期方向是否正確

這頁回答：  
我現在有沒有在正確軌道上？

##### Page 2：規劃與熱量紀錄

這是 daily cockpit。

處理：

- 新增食物
- 食物估算
- 模糊食物追問
- 今日已吃 / 剩餘熱量
- 三餐規劃
- 聚餐前預支
- 爆卡後補償

這頁回答：  
我今天怎麼吃？我剛剛吃的怎麼記？接下來怎麼安排？

##### Page 3：食物推薦

處理：

- 現在可以吃什麼
- 黃金選項
- 當前餐別可行選項
- 不同情境分組
- 一鍵打開外部連結

這頁回答：  
我現在可以吃什麼？

#### 6. 功能模組

##### 模組 A：食物輸入與熱量估算

輸入方式支援：

- 單張照片
- 前後照片
- 語音
- 自然語言文字
- 常用選項快速點選

系統任務：

- 辨識食物名稱
- 辨識主要高熱量項
- 辨識份量線索
- 辨識沒吃完線索
- 辨識分食線索
- 辨識合菜線索

估算流程：

1. 先初估
2. 判斷是否已達可估算程度
3. 若不足，補最少必要問題
4. 收斂到可估算
5. 存入今日紀錄

系統內部狀態：

- 可直接估
- 可粗估，但建議補一題
- 不可估，要先收斂

每筆輸出至少要有：

- 食物名稱
- 熱量估值
- 熱量範圍
- 信心程度
- 主要不確定因素
- 是否存成常用選項

##### 模組 B：三段式精度模式

###### 1. 快速模式

用途：

- 快速記下來
- 不想花太多時間
- 接受粗估

特性：

- 最多不問或只問 1 題
- 優先讓你記得下來

###### 2. 標準模式

主模式。

特性：

- 會補 1–2 題最關鍵問題
- 讓估算達到可信程度

###### 3. 精細模式

適合：

- 吃到飽
- 合菜
- 分食很多樣
- 特別想算準一點

特性：

- 可多問幾題
- 可搭配前後照片

##### 模組 C：沒吃完 / 分食 / 合菜處理

核心原則：  
不要要求使用者回答克數。  
只要求他回答生活中本來就會回答的問題。

可用的抽象輸入方式：

- 吃幾成
- 哪些有吃完
- 幾人分
- 我吃比較少 / 一半 / 比較多
- 幾口 / 幾塊 / 幾片 / 幾顆

場景 1：沒吃完

系統優先抓高影響部位：

- 主食吃多少
- 主菜吃多少
- 配菜吃多少
- 飲料 / 湯有沒有喝

場景 2：分食

系統可問：

- 幾人分
- 你吃比較少 / 一半 / 比較多 / 幾口

場景 3：合菜

系統先抓：

- 主要有吃哪些高熱量菜
- 白飯有沒有吃
- 炸物 / 肉類大概吃多少

前後照片模式適用於：

- 沒吃完
- 分食
- 合菜
- 自助餐
- 吃到飽

目的：

- 降低手動回報負擔
- 幫系統判斷實際攝取比例

##### 模組 D：體重記錄與趨勢

輸入：

- 每日體重

顯示：

- 今日體重
- 7 日平均
- 趨勢圖
- 近 14 日方向

原則：

- 不過度解讀單日波動
- 重點看趨勢

##### 模組 E：每日熱量目標與校正

初始目標：  
先設定一個初始每日熱量目標。

動態校正根據：

- 近 14–21 天攝取
- 體重趨勢
- 記錄完整度
- 使用者回報品質

給出建議：

- 維持
- 小降 100 kcal
- 小升 100 kcal
- 暫不調整

輸出形式：  
不是假裝精準的數字，而是教練式建議。

##### 模組 F：每日餐次規劃

功能：

- 先規劃今天三餐
- 分配每餐熱量
- 從黃金選項中挑候選

例如：

- 早餐 350
- 午餐 600
- 晚餐 650
- 彈性 200

支援：

- 正常日規劃
- 高風險日規劃
- 保留彈性

##### 模組 G：預支與補償調度

事前規劃例如：

- 後天吃到飽
- 明天聚餐

系統幫你規劃：

- 今明後幾天怎麼吃比較合理

事後補償例如：

- 今天已經爆了
- 晚上多吃很多

系統提供：

- 不補償
- 小幅回收
- 分 2–3 天攤平

原則：

- 不鼓勵激烈報復性節食
- 更重視多日穩定，而不是單日完美

##### 模組 H：食物推薦

這是 action layer。

核心目標：  
不是告訴你剩多少熱量，而是把它變成：  
現在真的能吃、而且你會願意吃的選項。

推薦來源先從：

- 你的常用食物
- 你的黃金選項
- 你的常見午餐 / 晚餐選擇

推薦邏輯先硬篩：

- 熱量
- 餐別
- 可得性
- 使用者明確排斥

再情境分組：

- 最穩
- 最方便
- 想吃爽一點
- 高蛋白優先
- 聚餐前適合
- 爆卡後適合

推薦頁不以精密排序為核心，因為熱量與可得性已經排掉大部分選項。

#### 7. 兩層記憶模型

##### 第一層：foods

最小欄位：

- 名稱
- 類型
- 餐別
- 熱量範圍
- 飽足感
- 爽感 / 滿足感
- 便利性
- 可得性
- 外部連結
- 常見變因
- 是否為常用選項

##### 第二層：preferences

最小欄位：

- 喜歡的類型
- 不喜歡的類型
- 是否需要主食
- 多量少餐 / 少量多餐
- 晚餐偏好
- 可接受的補償方式
- 容易膩的類型
- 常見怪癖
- 常見搭配邏輯
- 壓力 / 聚餐 / 爆卡時的傾向

#### 8. 新增：回報品質 / 報量偏差模型

因為有些人會：

- 習慣少報
- 習慣多報
- 常常描述很隨便
- 覺得自己吃很少，但其實不是
- 或反過來太保守估高

系統應該有一個輕量的 reporting bias profile。

可觀察維度：

- 是否常用模糊詞
- 是否常漏報高熱量細節
- 是否常在後續修正時出現明顯差異
- 估算攝取與體重趨勢長期是否對不太起來
- 是否經常記錄不完整

系統可形成的判斷：

- 這個人傾向少報
- 這個人傾向保守高估
- 這個人回報品質不穩
- 這個人需要多問一題才比較可信

用途：

- 決定是否要多追問
- 在熱量目標調整時降低過度相信紀錄
- 在推薦與補償時給更穩健建議

呈現方式：

- 不直接對使用者說「你都少報」
- 內部使用，或溫和表達：
  - 最近紀錄較模糊，暫不建議大幅調整目標
  - 若想讓熱量建議更準，這幾天可多補充份量資訊

#### 9. 外部平台策略

這版不做整合。  
只做：

- 記住你常用的 Google Maps / Foodpanda / Uber Eats 連結
- 在需要時一鍵打開

核心價值是：  
讓黃金選項在對的時刻被想起來並被執行。

#### 10. LLM 與確定性系統分工

LLM 負責：

- 食物理解
- 模糊輸入轉結構
- 判斷要不要追問
- 產生追問
- 推薦理由
- 預支 / 補償方案討論
- 從自然語言更新偏好

確定性系統負責：

- 今日總熱量
- 剩餘熱量
- 體重趨勢
- 熱量目標計算
- 候選篩選
- foods / preferences 存取
- 報量偏差 profile 更新

#### 11. v1 最重要的使用流程

日常流程：

1. 記體重
2. 記吃了什麼
3. 系統必要時補問
4. 更新今日剩餘熱量
5. 晚餐 / 宵夜時看推薦
6. 必要時做當日規劃

特殊流程：

- 有聚餐 / 吃到飽 -> 先做多日規劃
- 今天爆卡 -> 啟動補償討論

#### 12. 驗收標準

這版成功只看：

- 你有沒有連續 7–14 天願意用
- 食物紀錄是否比現在更順
- 模糊食物追問是否真的有幫助
- 你是否真的會用它看晚餐建議
- 聚餐 / 爆卡時你是否真的會跟它討論
- 它是否開始記住你的黃金選項與偏好
- 它是否開始知道你記錄品質穩不穩

#### 13. 一句話最終版

這是一個會把自然語言飲食描述收斂到可估算程度、記住你真正願意吃的黃金選項、理解你的吃法與回報偏差，並在日常與特殊情境下幫你規劃與決策的 AI 減脂操作系統。

### Tech Spec v0.1

範圍：Builder Space 第一版

#### 1. 這版要解的問題

做出一個可用的 LINE + LIFF 產品原型，完成這條閉環：

1. 用 LINE 傳照片 / 語音 / 文字記錄食物
2. 系統判斷能不能估熱量
3. 不夠就補最少問題
4. 記入今天總熱量
5. 顯示剩餘熱量
6. 提供少量可行的食物推薦
7. 支援簡單的預支 / 補償規劃
8. 記住常吃選項與偏好

#### 2. 這版的產品目標

成功標準：

- 一筆食物記錄 30 秒內完成
- 模糊食物也能靠追問收斂到可估算
- 每天能看見剩餘熱量
- 晚餐猶豫時真的會看推薦
- 聚餐前後會拿它來討論安排

這版不追求：

- 大量用戶
- 完整商業化
- 大型餐廳資料庫
- 深度平台整合
- 超精密營養分析
- 完整 infra 最佳化

#### 3. 第一版技術定位

Builder Space 在這版的角色：

- 模型使用環境
- 開發 / 展示環境
- staging / demo 入口

不要把產品核心綁死在 Builder Space。

核心原則：

- LINE webhook 處理邏輯是你的
- LIFF 前端是你的
- 資料結構是你的
- prompt / tool schema 是你的
- orchestration 是你的

之後離開 Builder Space，只是換 deployment / model provider，不是重做產品。

#### 4. 系統總覽

架構分四層：

##### A. LINE 層

負責低摩擦輸入：

- 文字
- 語音
- 圖片
- quick replies
- rich menu 入口

##### B. LIFF 層

負責視覺頁面：

- 體重與熱量目標
- 規劃與熱量紀錄
- 食物推薦

##### C. App Backend 層

負責：

- intent routing
- meal draft 管理
- 熱量估算 orchestration
- clarifying question
- recommendation
- planning
- memory update

##### D. Data / Memory 層

負責：

- foods
- preferences
- meal logs
- weight logs
- drafts
- reporting bias

#### 5. 前端架構

##### 5.1 LINE Chat 用途

只做高頻低摩擦任務：

- 新增一餐
- 回答追問
- 記體重
- 快速看今天還剩多少
- 快速叫出推薦
- 快速確認 / 修改 / 存成常用選項

不要在聊天室裡做：

- 一週規劃
- 長清單比較
- 圖表
- 大量食物管理

##### 5.2 LIFF 頁面

前端建議：React + Vite

理由：

- LIFF 本質上就是 web app
- 不需要 Next.js 的 SSR 優勢
- 三頁而已，React + Vite 更輕更快

頁面 1：Progress

顯示：

- 今日體重
- 7 日平均
- 趨勢圖
- 每日熱量目標
- 是否該微調目標

頁面 2：Today

顯示：

- 今日已吃 / 剩餘熱量
- 食物紀錄列表
- 新增食物入口
- 今日三餐規劃
- 聚餐前 / 爆卡後調度入口

頁面 3：Eat

顯示：

- 現在可吃什麼
- 黃金選項清單
- 依情境分組的建議
- 外部連結按鈕

#### 6. 後端系統設計

這版先不做 multi-agent graph。  
先做單一 orchestrator + 多個 task modules。

##### 6.1 核心模組

###### 1. Intent Router

輸入：LINE 訊息或 LIFF 請求  
輸出：這次任務類型

任務類型：

- food_log_new
- food_log_edit
- weight_log
- get_remaining_calories
- get_recommendations
- meal_plan
- compensation_plan
- save_preference
- general_chat

###### 2. Meal Draft Manager

處理所有餐點草稿狀態。

每餐都可以有 draft：

- 早餐
- 午餐
- 晚餐
- 宵夜

draft 狀態：

- draft
- awaiting_clarification
- confirmed
- archived

用途：

- 解決聊天跳來跳去
- 支援「早餐改一下」「晚餐先討論」這種真實場景

###### 3. Food Estimator

功能：

- 解析文字 / 語音轉文字 / 圖片
- 抽出食物與份量線索
- 做初步熱量估算
- 判斷是否已達可估算程度

輸出：

- parsed_items
- kcal_estimate
- kcal_range
- confidence
- missing_slots

###### 4. Clarifier

功能：

- 根據缺失資訊補問最少必要問題

原則：

- 只問高影響問題
- 以生活語言提問
- 最多 1–2 題為主

支援三段式：

- 快速模式
- 標準模式
- 精細模式

###### 5. Planner

功能：

- 今日三餐規劃
- 聚餐前預支
- 爆卡後補償
- 多日調度

輸出：

- 每日熱量安排
- 每餐建議配額
- 方案說明

###### 6. Recommender

功能：

- 根據剩餘熱量與偏好給少量可行選項

不做複雜 ranking，先做 eligibility filtering：

- 熱量範圍
- 餐別
- 地點 / 可得性
- 使用者排斥
- 黃金選項優先

輸出分組：

- 最穩
- 最方便
- 想吃爽一點
- 高蛋白優先
- 聚餐前適合
- 爆卡後適合

###### 7. Memory Updater

功能：

- 更新常吃食物
- 更新 preferences
- 更新 reporting bias

#### 7. 資料模型

##### 7.1 foods

欄位：

- id
- user_id
- name
- aliases
- category
- meal_types
- kcal_low
- kcal_high
- satiety_level
- comfort_level
- convenience_level
- availability_context
- external_links
- common_variants
- is_favorite
- is_golden
- usage_count
- last_used_at
- notes

##### 7.2 preferences

欄位：

- user_id
- likes
- dislikes
- must_have_carbs
- meal_style
- dinner_style
- compensation_style
- easy_to_get_bored_with
- quirks
- common_pairings
- stress_eating_tendency
- social_meal_tendency
- notes

##### 7.3 meal_logs

- id
- user_id
- date
- meal_type
- description_raw
- kcal_estimate
- kcal_low
- kcal_high
- confidence
- source_mode
- confirmed

##### 7.4 meal_drafts

- id
- user_id
- date
- meal_type
- status
- raw_input
- attachments
- parsed_items
- missing_slots
- followup_question
- draft_context

##### 7.5 weight_logs

- id
- user_id
- date
- weight

##### 7.6 plan_events

- id
- user_id
- date
- event_type
- expected_extra_kcal
- notes

##### 7.7 reporting_bias

欄位：

- user_id
- underreport_score
- overreport_score
- vagueness_score
- missing_detail_score
- log_confidence_score
- notes

用途：

- 判斷是否該多追問
- 熱量目標調整時降低過度相信紀錄
- 提醒資料品質不穩時不要大調目標

#### 8. 食物紀錄模式

##### 8.1 支援輸入模式

- 文字
- 語音
- 單張照片
- 前後照片
- 常用選項點選

##### 8.2 支援場景

一般單餐、便當、早餐、超商、飲料。

沒吃完輸入語言：

- 吃幾成
- 哪些吃完
- 哪些沒吃完

分食輸入語言：

- 幾人分
- 我吃比較少 / 一半 / 比較多
- 幾口 / 幾塊 / 幾片

合菜輸入語言：

- 主要吃哪幾道
- 白飯有沒有吃
- 肉類 / 炸物吃多少
- 青菜大概有沒有吃

前後照片模式適用於：

- 分食
- 合菜
- 沒吃完
- 吃到飽
- 自助餐

#### 9. 模型層設計

##### 9.1 主模型

Builder Space 第一版先用一個主模型即可。

主模型負責：

- 食物理解
- 初估熱量
- 判斷是否可估算
- 補問生成
- 推薦理由
- 規劃討論

##### 9.2 小模型 / 輕任務

若 Builder Space 支援分模型，可將 router 類任務放較便宜模型：

- intent routing
- 小型分類
- 文字正規化

但 v1 不強求。

#### 10. Orchestration 設計

核心定義：  
把使用者輸入分流成明確 task，讀取最小必要上下文，調用對的工具與資料，最後回到單一使用者體驗。

核心原則：  
不要把整串 LINE 對話當上下文。真正的上下文來自：

- draft state
- foods
- preferences
- meal logs
- weight logs
- plan events
- reporting bias

任務化處理：

food estimation task 讀：

- 這餐 draft
- 這次輸入
- foods 相關資料
- preferences 的吃法偏好

recommendation task 讀：

- 今日剩餘熱量
- 餐別
- foods
- preferences
- availability

planning task 讀：

- 近 14–21 天熱量與體重
- 未來事件
- compensation_style

#### 11. API / Tool 清單

- `POST /line/webhook`
- `POST /food/intake`
- `POST /food/clarify`
- `POST /food/confirm`
- `POST /weight/log`
- `GET /day/summary`
- `POST /plan/day`
- `POST /plan/compensation`
- `GET /recommendations`
- `POST /foods/favorite`
- `POST /preferences/update`

#### 12. 背景任務

每晚整理：

- 更新 usage_count
- 更新 favorite / golden candidate
- 更新 reporting bias

每週整理：

- 更新偏好摘要
- 更新補償風格判斷
- 更新常用選項

這版先不做太多自動化，避免複雜度爆掉。

#### 13. Builder Space 第一版的部署思維

假設：

- Builder Space 幫你處理模型與 demo 環境
- LINE + LIFF 跑起來
- 你的 code 結構保持可搬遷

關鍵要求：

- 不把 memory 寫死在 Builder Space 特有格式
- 不把 prompt 邏輯綁死在平台
- 不把資料表依賴寫死在平台 magic

#### 14. Builder Space 第一版的開發優先順序

##### Phase 1：最低可用閉環

- LINE webhook 接通
- LIFF 3 頁骨架
- food intake → estimate → clarify → confirm
- 今日剩餘熱量

##### Phase 2：記憶層

- foods
- preferences
- favorite / golden option
- reporting bias

##### Phase 3：決策層

- 晚餐推薦
- 三餐規劃
- 聚餐前 / 爆卡後規劃

#### 15. 這版最重要的驗收點

這版成功只看：

- 你自己能不能每天用
- 一筆食物記錄是不是比現在更順
- 追問是不是有幫助而不煩
- 推薦是不是少但有用
- 你是不是開始相信它記得你的常用選項
- 你是不是開始覺得它懂你會不會亂報 / 少報

#### 16. 一句話總結

Builder Space 第一版的核心，不是做出最完整的 app，而是做出一個能在 LINE 裡低摩擦捕獲、在 LIFF 裡做決策、在後端累積記憶與規劃能力的 AI 減脂操作系統。
