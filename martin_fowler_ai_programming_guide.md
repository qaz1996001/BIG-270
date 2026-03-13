# Martin Fowler 軟體開發哲學 - AI 程式設計統一指引

## 前言:核心信念

> "Any fool can write code that a computer can understand. Good programmers write code that humans can understand."  
> — Martin Fowler

這句話是整個指引的基石。**程式碼的首要讀者是人類**,不是編譯器或解釋器。所有設計決策都應以此為出發點。

---

## I. 核心哲學原則

### 1.1 軟體是活的有機體

軟體不是靜態實體。它需要定期修訂,就像優秀的散文一樣,隨著程式設計師對產品需求和最佳設計方式的理解加深而演化。

**對 AI 的意義:**
- 不要期望一次就寫出完美的程式碼
- 預期程式碼會被多次修改和改進
- 設計時考慮「可變更性」而非「完美性」

### 1.2 架構的定義

軟體架構是那些既重要又難以改變的決策。

**對 AI 的意義:**
- 謹慎對待難以改變的決策(如程式語言、資料庫選擇、核心框架)
- 其他設計決策應保持靈活,可隨需求演化
- 不是所有設計決策都是架構決策

### 1.3 可變更性是核心品質

軟體的價值在於「soft」(柔軟),意味著它應該容易改變。程式碼品質的最重要指標是**修改的容易程度**。

---

## II. 基本設計原則

### 2.1 YAGNI (You Aren't Gonna Need It)

YAGNI 是「你不會需要它」的縮寫。這是 Extreme Programming 的口號,指出某些我們認為軟體未來需要的能力,現在不應該建構。

**核心規則:**
1. **不要**為預測的未來功能增加程式碼
2. **不要**建立現在不需要的抽象層
3. **不要**實作「可能有用」的功能

**例外情況:**
YAGNI 只適用於支援預期功能的能力,不適用於使軟體更易修改的努力。重構不違反 YAGNI,因為它使程式碼更具可塑性。

**對 AI 的具體指導:**
```
✅ 正確:實作當前 story 需要的功能
✅ 正確:重構以改善程式碼結構
✅ 正確:撰寫測試以確保正確性

❌ 錯誤:「未來可能需要多個資料庫,所以現在就抽象化」
❌ 錯誤:「可能會有 API,所以先寫服務層」
❌ 錯誤:「可能要支援更多格式,所以建立複雜工廠模式」
```

### 2.2 Simple Design (簡單設計)

Kent Beck 的四個規則,按優先順序:

1. **通過所有測試** - 程式碼必須正確運作
2. **表達意圖** - 程式碼清楚表達它在做什麼
3. **沒有重複** - DRY (Don't Repeat Yourself)
4. **元素最少** - 最少的類別、方法、變數

**實踐方式:**
```python
# ❌ 不符合簡單設計:過度抽象
class AbstractDataProcessorFactory:
    def create_processor(self, type):
        if type == "json":
            return JSONDataProcessor()
        # 只有一種類型,不需要工廠

# ✅ 符合簡單設計:直接且清晰
class JSONDataProcessor:
    def process(self, data):
        return json.loads(data)
```

### 2.3 Evolutionary Design (演化式設計)

簡單設計的重點是不要增加當前 stories 不需要的複雜性。重構是保持設計簡單的必要手段,所以應該在能讓事情變簡單時進行重構。

**實踐循環:**
```
1. 實作當前需求的最簡單解決方案
2. 確保有測試覆蓋
3. 當需求改變或增加時,重構以適應
4. 保持設計簡單
5. 重複循環
```

---

## III. 程式碼實踐

### 3.1 人類可讀性原則

**命名:**
- 使用能表達意圖的名稱
- 避免縮寫和神秘代號
- 名稱應該回答「為什麼存在」、「做什麼」、「如何使用」

```python
# ❌ 不好的命名
def calc(d, m):
    return d * m * 0.8

# ✅ 好的命名
def calculate_discounted_price(original_price, discount_multiplier):
    STANDARD_TAX_RATE = 0.8
    return original_price * discount_multiplier * STANDARD_TAX_RATE
```

**函數大小:**
Kent Beck 將其稱為 Composed Method 模式:將大方法分解為命名良好的小方法,這是撰寫可維護程式碼最強大的工具之一。

**經驗法則:**
- 方法應該做一件事
- 如果需要用「和」來描述方法功能,就該拆分
- 方法長度:通常 5-15 行為佳

### 3.2 Refactoring (重構)

重構是在不改變外部行為的情況下,透過小步驟改進程式碼設計的受控技術。每個轉換都很小,但累積效果顯著。

**重構的黃金規則:**
1. **小步驟** - 每次重構都很小
2. **測試保護** - 每次重構後執行測試
3. **不改變行為** - 外部可觀察行為保持不變
4. **持續進行** - 隨時重構,而非大型重構事件

**何時重構:**
- 添加新功能前
- 修復 bug 時
- 程式碼審查時
- 發現 code smell 時

**對 AI 的指導:**
```
當你發現以下情況,應該建議重構:
1. 重複的程式碼出現 2 次以上
2. 方法超過 20 行
3. 類別有超過 7 個方法
4. 參數列表超過 3 個
5. 巢狀深度超過 3 層
6. 條件語句超過 3 個分支
```

### 3.3 Code Smells (程式碼異味)

Code smell 是表面徵兆,通常對應系統中更深層的問題。這個術語由 Kent Beck 創造。

**主要 Code Smells 清單:**

#### 1. **Long Method (過長方法)**
- **徵兆:** 方法超過 15-20 行
- **問題:** 違反單一職責原則,難以理解和修改
- **重構:** Extract Method (提取方法)

```python
# ❌ Long Method
def process_order(order):
    # 驗證訂單
    if not order.items:
        raise ValueError("Empty order")
    if not order.customer:
        raise ValueError("No customer")
    
    # 計算總價
    total = 0
    for item in order.items:
        total += item.price * item.quantity
        if item.quantity > 10:
            total *= 0.9
    
    # 處理付款
    payment = create_payment(total)
    if not payment.process():
        raise PaymentError()
    
    # 發送確認
    send_email(order.customer.email, total)

# ✅ 重構後
def process_order(order):
    validate_order(order)
    total = calculate_total(order)
    process_payment(total)
    send_confirmation(order.customer, total)
```

#### 2. **Duplicate Code (重複程式碼)**
- **徵兆:** 相同或相似的程式碼出現多次
- **問題:** 修改時需要改多處,容易漏改
- **重構:** Extract Method, Pull Up Method

#### 3. **Large Class (大類別)**
- **徵兆:** 類別有太多方法或欄位
- **問題:** 違反單一職責,難以理解
- **重構:** Extract Class, Extract Subclass

#### 4. **Long Parameter List (過長參數列表)**
- **徵兆:** 方法有超過 3-4 個參數
- **問題:** 難以理解和使用
- **重構:** Introduce Parameter Object, Preserve Whole Object

```python
# ❌ Long Parameter List
def create_user(name, email, age, address, phone, country, zip_code):
    pass

# ✅ 使用參數物件
class UserInfo:
    def __init__(self, name, email, age, contact_details):
        self.name = name
        self.email = email
        self.age = age
        self.contact = contact_details

def create_user(user_info):
    pass
```

#### 5. **Data Class (資料類別)**
- **徵兆:** 類別只有欄位,沒有行為
- **問題:** 違反物件導向原則,行為與資料分離
- **重構:** Move Method, Encapsulate Field

#### 6. **Feature Envy (特性羨慕)**
- **徵兆:** 方法對其他類別的興趣勝過所在類別
- **問題:** 方法放錯位置
- **重構:** Move Method

```python
# ❌ Feature Envy
class Order:
    def __init__(self, customer):
        self.customer = customer
    
    def get_customer_discount(self):
        # 這個方法更關心 Customer
        if self.customer.is_premium:
            return 0.1
        elif self.customer.years > 5:
            return 0.05
        return 0

# ✅ 移動方法
class Customer:
    def get_discount(self):
        if self.is_premium:
            return 0.1
        elif self.years > 5:
            return 0.05
        return 0

class Order:
    def get_discount(self):
        return self.customer.get_discount()
```

#### 7. **Primitive Obsession (基本型別偏執)**
- **徵兆:** 過度使用基本型別而非小物件
- **問題:** 失去型別安全和封裝
- **重構:** Replace Data Value with Object

```python
# ❌ Primitive Obsession
def transfer_money(from_account: str, to_account: str, amount: float):
    pass

# ✅ 使用值物件
class Money:
    def __init__(self, amount: float, currency: str):
        self.amount = amount
        self.currency = currency

class Account:
    def __init__(self, account_number: str):
        self.number = account_number

def transfer_money(from_account: Account, to_account: Account, amount: Money):
    pass
```

#### 8. **Comments (過多註解)**
- **徵兆:** 需要大量註解解釋程式碼
- **問題:** 程式碼本身不夠清晰
- **重構:** Extract Method, Rename Method

```python
# ❌ 需要註解才能理解
# 檢查是否為閏年
if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
    days = 366

# ✅ 程式碼自我說明
def is_leap_year(year):
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

days = 366 if is_leap_year(year) else 365
```

---

## IV. 測試與交付

### 4.1 Self-Testing Code (自我測試程式碼)

自我測試程式碼是指撰寫完整自動化測試與功能程式碼相結合的實踐。做得好時,可以用單一命令執行測試,並確信這些測試會揭露程式碼中的任何 bug。

**測試原則:**
1. **測試先行** - 先寫測試,再寫實作(TDD)
2. **快速測試** - 測試應該在秒級內執行完成
3. **獨立測試** - 測試間不應有依賴
4. **清晰測試** - 測試就是文件

**測試覆蓋目標:**
```
- 單元測試:覆蓋所有公開方法
- 整合測試:覆蓋關鍵流程
- 關鍵業務邏輯:100% 覆蓋
- 邊界條件:必須測試
```

**對 AI 的要求:**
```
✅ 必須做:
1. 為每個公開方法撰寫至少一個測試
2. 測試正常情況和異常情況
3. 測試邊界條件
4. 確保測試可獨立執行

❌ 禁止:
1. 沒有測試就提交程式碼
2. 依賴手動測試
3. 測試間有依賴關係
4. 忽略失敗的測試
```

### 4.2 Continuous Delivery (持續交付)

軟體只有在生產環境中才能提供價值給客戶。持續交付使用自動化和協作工作流程來移除這個瓶頸,允許團隊隨時發布軟體。

**核心實踐:**
1. **持續整合** - 每天多次整合到主分支
2. **自動化測試** - 每次提交都執行測試
3. **自動化部署** - 一鍵部署到任何環境
4. **隨時可發布** - 主分支始終處於可發布狀態

---

## V. AI 特定指導原則

### 5.1 處理非確定性

Martin Fowler 指出,這是工具首次如此廣泛應用於軟體工程卻是非確定性的。我們需要像其他工程領域一樣思考容差。

**對 AI 編程的影響:**
1. **強化測試** - AI 生成的程式碼必須有更嚴格的測試
2. **人工審查** - 所有 AI 生成的程式碼都需人工審查
3. **容差思維** - 不能過度依賴精確性
4. **版本控制** - 仔細追蹤變更

### 5.2 AI 生成程式碼的品質標準

**不因 AI 生成而降低標準:**
```
所有 AI 生成的程式碼必須符合:
✅ 通過所有 code smell 檢查
✅ 符合 YAGNI 原則
✅ 遵循 Simple Design 規則
✅ 有完整測試覆蓋
✅ 人類可讀且表達意圖清晰
✅ 沒有重複程式碼
```

### 5.3 AI 輔助重構

**利用 AI 但保持警覺:**
1. **建議重構** - AI 可以識別 code smells 並建議重構
2. **驗證結果** - 必須執行測試確保行為不變
3. **審查變更** - 人工審查重構是否真正改善設計
4. **小步驟** - 即使是 AI 也要遵循小步驟原則

---

## VI. 實施檢查清單

### 6.1 程式碼撰寫檢查清單

在生成或審查程式碼時,依序檢查:

**□ 1. 是否符合 YAGNI?**
- 每個功能都是當前需求嗎?
- 有沒有「未來可能需要」的程式碼?
- 抽象層次是否恰當?

**□ 2. 是否符合 Simple Design?**
- ✓ 通過所有測試?
- ✓ 表達意圖清晰?
- ✓ 沒有重複?
- ✓ 元素最少?

**□ 3. 是否人類可讀?**
- 命名是否表達意圖?
- 方法是否簡短(<20 行)?
- 巢狀是否太深(>3 層)?
- 參數是否太多(>3 個)?

**□ 4. 有無 Code Smells?**
- 檢查本指引列出的 8 個主要 smells
- 發現則標記並建議重構

**□ 5. 測試是否充分?**
- 每個公開方法都有測試?
- 邊界條件都測試了?
- 異常情況都覆蓋了?
- 測試可獨立執行?

**□ 6. 是否可以重構改善?**
- 有沒有更簡單的寫法?
- 可以提取方法嗎?
- 可以移除重複嗎?

### 6.2 重構決策樹

```
發現程式碼問題時:
│
├─ 是否影響外部行為?
│  ├─ 是 → 這是 bug,不是重構
│  └─ 否 → 繼續
│
├─ 改善後是否更清晰?
│  ├─ 否 → 不要重構
│  └─ 是 → 繼續
│
├─ 能分解為小步驟嗎?
│  ├─ 否 → 重新思考方法
│  └─ 是 → 繼續
│
├─ 有測試保護嗎?
│  ├─ 否 → 先寫測試
│  └─ 是 → 執行重構
│
└─ 每步之後
   ├─ 執行測試
   ├─ 確認行為不變
   └─ 提交變更
```

### 6.3 設計決策框架

當面對設計選擇時:

**簡單 vs 複雜:**
- 預設選擇簡單方案
- 只有明確需求時才增加複雜性

**現在 vs 未來:**
- 優先解決當前問題
- YAGNI:未來功能待需要時再實作

**抽象 vs 具體:**
- 在有 2-3 個實例前,保持具體
- 真正的抽象需求來自實際使用

**框架 vs 簡單程式碼:**
- 評估是否真的需要框架
- 簡單問題不要用複雜解決方案

---

## VII. 核心價值觀總結

最後,記住這些核心價值觀:

1. **程式碼首先是寫給人類讀的**
   - 清晰勝過簡潔
   - 表達意圖勝過實作細節

2. **簡單是終極的複雜**
   - 最簡單的可行方案
   - YAGNI:不要過度設計

3. **軟體必須可以改變**
   - 可變更性是核心品質
   - 重構是必要的日常活動

4. **測試是設計的一部分**
   - 沒有測試就沒有信心
   - 測試是最好的文件

5. **演化勝過預測**
   - 設計隨需求演化
   - 持續改進而非一次完美

6. **品質不是可選的**
   - 無論是人類還是 AI 寫的
   - 標準始終一致

---

## 結語

這份指引濃縮了 Martin Fowler 數十年來塑造開發者如何思考程式碼、設計和架構的智慧。遵循這些原則,無論是 AI 還是人類開發者,都能寫出清晰、可維護、可演化的軟體。

記住:「任何傻瓜都能寫出電腦能理解的程式碼。優秀的程式設計師寫出人類能理解的程式碼」這是永恆的真理。

---

## 附錄 A: 快速參考卡

### 設計原則速查
- **YAGNI**: 不要為未來需求寫程式碼
- **Simple Design**: 測試通過 → 表達意圖 → 無重複 → 最少元素
- **Evolutionary Design**: 先簡單實作,後續重構演化

### Code Smell 速查
1. Long Method (>20 行)
2. Large Class (>7 個方法)
3. Long Parameter List (>3 個參數)
4. Duplicate Code
5. Data Class (只有資料沒有行為)
6. Feature Envy (方法放錯類別)
7. Primitive Obsession (過度使用基本型別)
8. Comments (需要註解才能理解)

### 重構原則速查
- 小步驟重構
- 每步後測試
- 不改變行為
- 持續進行

### 測試原則速查
- 測試先行 (TDD)
- 快速執行 (<秒級)
- 測試獨立
- 測試即文件

---

## 附錄 B: 推薦資源

**Martin Fowler 核心著作:**
- Refactoring: Improving the Design of Existing Code (2nd Edition)
- Patterns of Enterprise Application Architecture
- Domain-Specific Languages

**線上資源:**
- Martin Fowler 官網: https://martinfowler.com
- Refactoring 目錄: https://refactoring.com
- 關鍵文章:
  - "Is Design Dead?"
  - "YAGNI"
  - "Code Smell"
  - "Continuous Integration"
  - "Microservices"

**相關重要著作:**
- Kent Beck: "Extreme Programming Explained"
- Kent Beck: "Test Driven Development: By Example"
- Eric Evans: "Domain-Driven Design"

---

## 版本資訊

**版本:** 1.0  
**最後更新:** 2024-12-19  
**基於:** Martin Fowler 思想與著作綜合整理  
**目標受眾:** AI 系統、程式設計師、軟體開發團隊  

**授權:** 本指引基於公開可得的 Martin Fowler 思想與原則整理而成,旨在教育目的。

---

*"Software development is a young profession, and we are still learning the techniques and building the tools to do it effectively."* — Martin Fowler
