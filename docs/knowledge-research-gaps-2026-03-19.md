# Knowledge Research Gaps

Date: 2026-03-19

## Current Coverage Is Strong On

- 台灣外食口語與模糊說法
- 份量錨點與比較法
- 外食減脂決策規則
- 熱量、蛋白質、飽足感、油糖風險的基本判斷
- 台北高頻外食場景與捷運/商圈節點

## Highest-Priority Missing Research

### P0: Chain- and Menu-Level Nutrition Cards

You already have strong generic knowledge, but still lack enough **current brand/menu cards** for the app's most practical use cases.

Best next targets:

- 早餐連鎖
  - `Q Burger`
  - `麥味登`
  - `弘爺`
- 便利商店
  - `FamilyMart`
  - `Hi-Life`
  - `OKmart`
- 速食/快餐
  - `Subway`
  - `KFC`
  - `八方雲集`
  - `四海遊龍`
- 手搖飲
  - `50嵐`
  - `清心`
  - `CoCo`
  - `麻古`
  - `可不可`
  - `迷客夏`

What to research for each brand:

- current core menu
- common sizes
- official calories if available
- sugar / topping rules if drinks
- 3-5 stable "safe order" examples

### P0: Convenience Store Product Archetypes

Current research is strong on convenience stores as a scene, but still thin on **structured SKU-level cards**.

Most useful next research:

- high-protein convenience meals
- common rice bowl / pasta / curry SKUs
- tea eggs, salads, sweet potatoes, chicken breast packs
- dessert and drink traps

Needed fields:

- product name
- brand
- serving size
- kcal
- protein
- sugar
- sodium
- why it is stable or risky

### P0: Drink Chain Sugar/Size Maps

This app will be asked about drinks a lot.

Still missing:

- standardized mapping across major drink chains for:
  - medium / large sizes
  - no sugar / light / half / full sugar
  - default topping portions

This is especially valuable for:

- fast heuristic estimates
- reducing unnecessary clarification
- better nearby recommendation ranking

## Medium-Priority Missing Research

### P1: Taipei District / MRT Safe-Order Maps

The current Taipei scene pack is good at **where** people eat, but still weak at **what is usually a stable option there**.

Useful next research:

- 台北車站附近常見穩定午餐類型
- 信義區百貨商場常見低風險選項
- 西門 / 中山 / 南京復興 / 松江南京的高頻午晚餐模式
- 夜市節點的較穩選項與高風險選項

This helps:

- nearby recommendation
- proactive saved-place setup
- faster place-based prompts

### P1: Golden Orders By Context

You already have generic decision rules, but still need more **context-specific golden orders**:

- 公司附近午餐最穩
- 家附近晚餐最穩
- 聚餐前白天怎麼吃
- 爆卡後隔天怎麼排
- 宵夜嘴饞但不想爆時的店家型選法

This research should produce:

- situation
- candidate order
- estimated kcal range
- why it is stable

### P1: Visual Portion Anchors

You already have verbal anchors. What is still missing is better **container-based and visual anchor data**:

- 早餐店中杯 / 大杯
- 手搖飲 500 / 700 ml 視覺差異
- 便當一格飯 vs 半格飯
- 常見飯碗 / 麵碗 / 湯碗 / 湯匙 / 茶匙

This will help:

- comparison mode
- LIFF UI
- photo-to-portion clarification

## Lower-Priority But Valuable Later

### P2: Alcohol and Social Dining Cards

Current research mentions alcohol, but still lacks enough structured examples for:

- 啤酒
- highballs
- cocktails
- 下酒菜組合
- 居酒屋 / 熱炒 / 桌菜聚餐

### P2: Special-Diet and Constraint Packs

Not necessary for v1, but useful later:

- vegetarian
- lactose sensitivity
- low-sodium preference
- diabetes-aware general guidance

These should remain general and non-medical unless you intentionally expand scope.

## Best Research Format To Give Me Next

If you keep using deep research, the best handoff format is:

### Best

- one markdown per topic
- one csv/json per brand or menu set

### For brand research

Please include:

- brand name
- source URL
- item name
- serving size
- kcal
- protein
- sugar
- sodium
- notes on size / toppings / uncertainty

### For location research

Please include:

- district or MRT station
- common meal windows
- common store types
- low-risk options
- high-risk traps

## Recommendation

If you only continue 3 research tracks next, do these first:

1. major drink chains
2. convenience store SKUs
3. breakfast and fast-casual chain menu cards
