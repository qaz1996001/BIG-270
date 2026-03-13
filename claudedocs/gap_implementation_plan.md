# 7 Gap 實作計畫

> 日期：2026-03-13
> 哲學框架：Ken Thompson × Donald Knuth × Linus Torvalds
> 前置文件：`gap_analysis_and_plan.md`

---

## 哲學分析框架

在規劃每個 Gap 之前，先用三位大師的視角審視：

| 大師 | 核心問題 | 應用於本專案 |
|------|---------|-------------|
| **Ken Thompson** | 「最簡單的解法是什麼？」「由下而上，從原語開始」| 每個 Gap 必須產出可組合的 primitive，不造框架 |
| **Donald Knuth** | 「數學上正確嗎？」「這是關鍵的 3% 還是可忽略的 97%？」| 頻率公式要有嚴謹推導，效能熱點要量測而非猜測 |
| **Linus Torvalds** | 「資料結構對了嗎？」「有沒有可以消除的 special case？」| 先想清楚資料如何流動，再寫程式碼；避免 if/else 分支爆炸 |

**共通原則**：
- **YAGNI**：只做研究文件明確要求的，不做「可能有用」的
- **先讓它跑 → 讓它正確 → 讓它快**（Thompson/Knuth 共識）
- **資料結構驅動行為**（Torvalds/Thompson 共識）：nullable fields 決定功能可用性，延續現有 tier 架構
- **做一件事，做到完美**（Thompson）：每個新函數只做一件事

---

## Gap 1: Kurtogram / 頻譜峭度

### 哲學審視

> **Thompson**: 「Kurtogram 的本質是什麼？」→ 在一個二維網格 (center_freq × bandwidth) 上計算 kurtosis，找最大值。核心原語是 `spectral_kurtosis(signal, fs, band)`。
>
> **Knuth**: 「Fast Kurtogram 的時間複雜度？」→ O(L × 2^L) 其中 L 為分解層數，通常 L=6。合理的計算量，不需擔心效能。但 kurtosis 的數學定義（第四中心動差/方差²）必須精確。
>
> **Torvalds**: 「資料結構是什麼？」→ 輸入：signal + fs。輸出：最佳頻帶 (center, bandwidth)。中間過程不需暴露。簡單的 tuple 回傳即可。

### 目標

自動選擇軸承包絡分析的最佳帶通濾波頻帶，取代 Tier 2 的固定頻帶或手動指定。

### 設計

```
preprocessing.py 新增：
  compute_spectral_kurtosis(signal, fs, band) → float
  compute_kurtogram(signal, fs, levels=6) → (center_freq, bandwidth, kurtosis_map)
```

**演算法**：Fast Kurtogram (Antoni, 2007)
1. 對訊號進行 L 層二元樹分解（Short-Time Fourier Transform 方法）
2. 每個節點計算頻譜峭度 = `kurt(envelope(bandpassed_signal))`
3. 找到峭度最大的節點 → 回傳其中心頻率與頻寬

**整合**：
- `Tier2Analyzer.analyze()` 中，若 `band=None` 且信號夠長（≥2048 samples），用 kurtogram 自動選擇頻帶
- 若信號太短，退回全頻帶包絡分析（消除 special case：短信號不該讓系統崩潰）

### 資料結構

```python
@dataclass
class KurtogramResult:
    center_freq: float      # Hz - 最佳頻帶中心
    bandwidth: float        # Hz - 最佳頻帶寬度
    max_kurtosis: float     # 最大峭度值
    level: int              # 分解層數
```

不需要。**Thompson 原則**：一個 tuple 就夠了，不要為一次性結果造 dataclass。
→ 回傳 `tuple[float, float, float]`：`(center_freq, bandwidth, max_kurtosis)`

### 檔案變動

| 檔案 | 變動 |
|------|------|
| `preprocessing.py` | +`compute_spectral_kurtosis()`, +`compute_kurtogram()` |
| `analyzers/tier2.py` | 修改 `analyze()` 使用 kurtogram 自動選頻帶 |
| `tests/test_preprocessing.py` | +kurtogram 測試（已知頻帶的合成信號） |
| `tests/test_tier2.py` | +自動頻帶選擇整合測試 |

### 測試策略

1. **單元測試**：合成一個在 3000-5000 Hz 帶有衝擊的信號 + 隨機噪音，驗證 kurtogram 找到的頻帶包含 3000-5000 Hz
2. **退化測試**：純噪音信號，kurtogram 不應回傳極端頻帶
3. **整合測試**：Tier 2 使用 kurtogram 頻帶後仍能偵測 BPFO

### 複雜度評估

- 新增程式碼：~80-120 行
- 新增測試：~6-8 個
- 依賴：僅 numpy + scipy（已有）

---

## Gap 2: 視覺化模組

### 哲學審視

> **Thompson**: 「做一件事，做到完美。」→ 視覺化函數應該是純函數：輸入數據 → 輸出 figure。不混合計算與繪圖。每個圖一個函數。
>
> **Knuth**: 「程式的首要讀者是人類。」→ 視覺化是讓診斷結果可被人類閱讀的關鍵。圖表的標註要精確（頻率單位 Hz、幅值單位、故障標記位置）。
>
> **Torvalds**: 「不要過度設計。」→ 不需要 dashboard 框架。matplotlib 純函數就好。不要造繪圖引擎。

### 目標

提供基礎繪圖函數，讓使用者可視化驗證診斷結果。

### 設計

```
新增 src/vibfault/visualization.py：
  plot_spectrum(freqs, amps, ...) → Figure
  plot_envelope_spectrum(freqs, amps, markers, ...) → Figure
  plot_cepstrum(quefrency, cepstrum, ...) → Figure
  plot_time_waveform(signal, fs, ...) → Figure
  plot_diagnosis_summary(result: DiagnosisResult, ...) → Figure
```

**Thompson 原則**：每個函數只畫一種圖。組合由使用者決定（subplot 排版留給使用者）。

**介面設計**（Thompson：介面小到可以記住）：
- 所有繪圖函數統一簽名：`(data, ..., ax=None, **kwargs) → matplotlib.axes.Axes`
- `ax=None` 時自動建立 figure；傳入 ax 時畫在指定 subplot 上
- 回傳 Axes 讓使用者可以進一步客製化

### 標記系統（Knuth：精確性）

故障特徵頻率標記：
```python
@dataclass
class FrequencyMarker:
    frequency: float     # Hz
    label: str           # e.g. "BPFO", "2X", "GMF"
    color: str = "red"
```

不需要。一個 `dict[str, float]` 或 `list[tuple[float, str]]` 就夠了。

→ 使用 `markers: dict[str, float] | None = None`，key 是標籤，value 是頻率。

### 檔案變動

| 檔案 | 變動 |
|------|------|
| `src/vibfault/visualization.py` | 新增，5 個繪圖函數 |
| `src/vibfault/__init__.py` | 導出 visualization 模組 |
| `tests/test_visualization.py` | 煙霧測試（函數可呼叫、回傳 Axes） |

### 測試策略

- 使用 `matplotlib.use("Agg")` backend 避免彈出視窗
- 驗證回傳型別為 `matplotlib.axes.Axes`
- 驗證標記出現在正確位置（`ax.lines`, `ax.texts`）
- 不做像素級比較（太脆弱）

### 複雜度評估

- 新增程式碼：~150-200 行
- 新增測試：~8-10 個
- 依賴：matplotlib（已在 pyproject.toml）

---

## Gap 3: STFT / CWT 時頻分析

### 哲學審視

> **Thompson**: 「核心原語是什麼？」→ `compute_stft()` 和 `compute_cwt()`。兩個獨立函數，各做一件事。不要造「通用時頻分析器」。
>
> **Knuth**: 「STFT 的時頻解析度權衡是精確的數學問題。」→ 窗長 N 決定頻率解析度 Δf = fs/N 和時間解析度 Δt = N/fs。CWT 用尺度(scale)替代固定窗長，數學上更靈活。
>
> **Torvalds**: 「這是關鍵的 3% 還是 97%？」→ 穩態診斷（目前系統主要場景）不需要時頻分析。這是為暫態/啟停機場景的擴展。先封裝 scipy/pywt 即可，不需要自己實作。

### 目標

支援非穩態訊號分析，為啟停機過程診斷和瀑布圖提供基礎。

### 設計

```
preprocessing.py 新增：
  compute_stft(signal, fs, nperseg=256, noverlap=None)
    → (times, frequencies, magnitude)

  compute_cwt(signal, fs, wavelet="morl", freq_range=None)
    → (times, frequencies, coefficients)
```

**封裝策略**（Thompson：不重複造輪子）：
- STFT：直接封裝 `scipy.signal.stft()`，回傳 magnitude（非複數）
- CWT：封裝 `pywt.cwt()`，將 scales 自動轉換為使用者友善的 frequency range

### 依賴變動

```toml
# pyproject.toml
dependencies = [
    ...,
    "pywt>=1.6",  # 新增（CWT 需要）
]
```

### 檔案變動

| 檔案 | 變動 |
|------|------|
| `preprocessing.py` | +`compute_stft()`, +`compute_cwt()` |
| `pyproject.toml` | +`pywt` 依賴 |
| `tests/test_preprocessing.py` | +STFT/CWT 形狀與邊界測試 |
| `visualization.py` | +`plot_spectrogram()`, +`plot_scalogram()` (可選) |

### 測試策略

1. **STFT 形狀測試**：輸出矩陣維度 = (n_freq, n_time)
2. **CWT 形狀測試**：輸出矩陣維度正確
3. **STFT 頻率測試**：合成 100 Hz 正弦波，STFT 在 100 Hz 處有最大能量
4. **CWT 頻率測試**：同上
5. **邊界測試**：空信號、極短信號的處理

### 複雜度評估

- 新增程式碼：~60-80 行
- 新增測試：~6-8 個
- 依賴：+pywt

---

## Gap 4: 階次追蹤 (Order Tracking)

### 哲學審視

> **Thompson**: 「由下而上。」→ 階次追蹤的核心原語是角度域重取樣 `resample_to_angular_domain(signal, fs, rpm_profile)`。有了這個 primitive，所有現有 analyzer 都可以直接在角度域上運作。
>
> **Knuth**: 「嚴謹定義問題。」→ 階次追蹤需要兩種輸入模式：(a) 恆定 RPM + 微小波動 → 不需要階次追蹤；(b) 變速 RPM profile → 需要。必須精確定義「什麼情況下觸發階次追蹤」。
>
> **Torvalds**: 「資料結構優先。」→ 需要在 `MachineParameters` 中新增 `rpm_profile` 欄位。nullable → 不影響現有 tier 系統。資料結構的改變驅動行為的改變。

### 目標

支援變速工況下的故障診斷，將時域訊號重取樣至角度域。

### 設計

**資料結構變動**（Torvalds：資料驅動行為）：

```python
# models.py - MachineParameters
rpm_profile: np.ndarray | None = None  # RPM vs time 曲線
rpm_timestamps: np.ndarray | None = None  # 對應時間戳

# 或者更簡潔的 tachometer 模式：
tach_pulses: np.ndarray | None = None  # tachometer 脈衝時刻 (秒)
tach_pulses_per_rev: int = 1  # 每轉脈衝數
```

**Thompson 原則**（選擇最簡單的模式）：
- 用 `tach_pulses`（時間戳陣列），因為這是最接近硬體感測器的原語
- RPM profile 可以從 tach_pulses 推導：`rpm_from_tach(pulses, ppr)`

```
preprocessing.py 新增：
  rpm_from_tach(tach_pulses, pulses_per_rev) → (times, rpm)
  resample_angular(signal, fs, tach_pulses, ppr, orders_per_rev=10)
    → (angular_signal, angular_fs)
```

**重取樣方法**：
1. 從 tachometer 脈衝計算瞬時角度 θ(t)
2. 在等角度間隔 Δθ 處內插振動訊號
3. 結果是角度域信號，頻率軸變為「階次」(order)

### 整合點

- `pipeline.py`：若 `params.tach_pulses is not None`，在呼叫 analyzers 之前先做角度域重取樣
- 現有 analyzers 不需修改：它們接收重取樣後的信號 + 等效 `sampling_rate`（orders/rev）
- 輸出結果中標記 `analysis_methods_used: ["order_tracking"]`

### 檔案變動

| 檔案 | 變動 |
|------|------|
| `models.py` | +`tach_pulses`, +`tach_pulses_per_rev` 欄位 |
| `preprocessing.py` | +`rpm_from_tach()`, +`resample_angular()` |
| `pipeline.py` | 在分析前插入角度域重取樣步驟 |
| `__main__.py` | +`--tach-file` CLI 參數 |
| `tests/test_preprocessing.py` | +角度域重取樣測試 |

### 測試策略

1. **RPM 提取**：合成等間距脈衝（恆速），驗證 RPM 恆定
2. **重取樣正確性**：合成變速信號（1X + 2X），重取樣後在角度域應為恆定頻率的 1 order + 2 order
3. **整合測試**：變速信號 + 不平衡特徵 → pipeline 仍能偵測 fault #1

### 複雜度評估

- 新增程式碼：~100-130 行
- 新增測試：~6-8 個
- 依賴：scipy.interpolate（已有）

---

## Gap 5: 經驗模態分解 (EMD)

### 哲學審視

> **Thompson**: 「先讓它動起來。」→ EMD 已有成熟的 Python 實作 `PyEMD`。封裝它，不要自己寫篩選算法。核心原語是 `compute_emd(signal) → list[IMF]`。
>
> **Knuth**: 「EMD 不是嚴格數學方法——它是經驗性的。」→ 沒有收斂性證明。但在工程上有效。承認其限制，不要過度聲稱。適合作為輔助方法，不適合作為主要判據。
>
> **Torvalds**: 「這解決了什麼實際問題？」→ 在包絡線分析之前，先用 EMD 分解出包含衝擊成分的 IMF，可以提升軸承早期故障偵測的信噪比。但現有包絡分析已能偵測多數故障。這是增強，不是必需。

### 目標

提供 EMD 分解功能，可選擇性地結合包絡分析提升軸承故障偵測靈敏度。

### 設計

```
preprocessing.py 新增：
  compute_emd(signal, max_imfs=None) → list[np.ndarray]
    # 回傳 IMF 列表，從高頻到低頻排列
```

**整合**（可選增強，不修改預設行為）：
- Tier 2 新增可選 flag：`use_emd=False`
- 若啟用：先 EMD 分解 → 選擇 kurtosis 最大的 IMF → 對該 IMF 做包絡分析
- 預設不啟用（Thompson：不改變已驗證的行為）

### 依賴變動

```toml
# pyproject.toml
dependencies = [
    ...,
    "EMD-signal>=1.6",  # PyEMD 新名稱
]
```

### 檔案變動

| 檔案 | 變動 |
|------|------|
| `preprocessing.py` | +`compute_emd()` |
| `pyproject.toml` | +`EMD-signal` 依賴 |
| `tests/test_preprocessing.py` | +EMD 分解測試 |

### 測試策略

1. **分解測試**：合成 50Hz + 200Hz 雙正弦波，EMD 應分解出至少 2 個有意義的 IMF
2. **IMF 性質**：每個 IMF 的均值接近零，極值數量 ≈ 零交叉數量（±1）
3. **重建測試**：所有 IMF + 殘差之和 ≈ 原信號

### 複雜度評估

- 新增程式碼：~30-40 行（主要是封裝）
- 新增測試：~4-5 個
- 依賴：+EMD-signal

---

## Gap 6: 軸向振動分析（多通道支援）

### 哲學審視

> **Thompson**: 「資料結構。」→ 目前所有函數接受 1-D `np.ndarray`。多通道 = 要嘛多個 1-D 陣列，要嘛一個 2-D 陣列。哪個更簡單？多個 1-D。不要改變現有 API。
>
> **Knuth**: 「邊界條件。」→ 軸向振動分析只影響 #2（軸彎曲）和 #9（角度不對中）的診斷。改動範圍小且明確。
>
> **Torvalds**: 「消除 special case。」→ 現在 #9 是 partial diagnosis，是一個 special case。加入軸向通道後可以消除這個 special case，讓 #9 成為完整診斷。這是「好品味」。

### 目標

支援多通道（徑向 + 軸向）振動輸入，完善 #2 和 #9 的診斷。

### 設計

**資料結構**（Torvalds：資料驅動行為）：

```python
# MachineParameters 新增：
axial_signal: np.ndarray | None = None  # 軸向加速度信號
# 主信號仍為 pipeline 的 signal 參數（徑向）
```

不，更好的方式是 **不改 MachineParameters**（Thompson：最小變動原則）。

→ `pipeline.diagnose(signal, params)` 改為 `pipeline.diagnose(signal, params, axial_signal=None)`

→ `Tier1Analyzer.analyze(signal, params)` 改為 `analyze(signal, params, axial_signal=None)`

**規則增強**：

| 故障 | 現有規則 | 增強規則 |
|------|---------|---------|
| #2 軸彎曲 | 1X + 2X/1X > 0.5 | + 軸向 1X 幅值高（axial_1x / radial_1x > 0.5） |
| #9 角度不對中 | 1X elevated (partial) | + 軸向 1X > 徑向 1X → 完整診斷（diagnosis_type: S → P → S） |

### 檔案變動

| 檔案 | 變動 |
|------|------|
| `analyzers/protocol.py` | `analyze()` 簽名加 `axial_signal=None` |
| `analyzers/tier1.py` | 修改 #2/#9 規則，使用軸向數據增強 |
| `pipeline.py` | 傳遞 `axial_signal` 至 analyzers |
| `__main__.py` | +`--axial-file` CLI 參數 |
| `tests/test_tier1.py` | +軸向增強測試 |

### 測試策略

1. **#9 完整診斷**：合成軸向 1X 顯著信號，驗證 #9 從 partial → specific
2. **#2 軸向增強**：合成軸向 1X 高 + 徑向 2X/1X > 0.5，驗證 confidence 提升
3. **向後相容**：不傳 axial_signal 時，行為與現有完全相同

### 複雜度評估

- 修改程式碼：~40-60 行
- 新增測試：~4-6 個
- 依賴：無新增

---

## Gap 7: Oil Whirl vs Oil Whip 區分

### 哲學審視

> **Thompson**: 「這個問題的最簡單解法是什麼？」→ Whirl: 次同步頻率 ≈ 0.42-0.48X 且隨轉速變化。Whip: 次同步頻率鎖定在臨界轉速。需要：(a) 臨界轉速參數 或 (b) 多轉速數據。(a) 更簡單。
>
> **Knuth**: 「數學判據要精確。」→ Whirl: f_sub / f_shaft ∈ [0.40, 0.48] 且 f_sub ≈ 0.43×RPM。Whip: f_sub ≈ f_critical（一階臨界）且 f_sub / f_shaft < 0.40（因為轉速已超過 2× 臨界）。
>
> **Torvalds**: 「這是 Tier 5 的功能。」→ 現在的架構中，`critical_speed` 已在 MachineParameters 中（Tier 5 欄位）。`tier` property 已處理 `critical_speed is not None → tier = 5`。不需要改架構，只需要實作 Tier 5 analyzer。

### 目標

區分 Oil Whirl (#11) 和 Oil Whip (#12)，從 merged group 拆分為個別診斷。

### 設計

**方案 A：使用 critical_speed 參數**（最簡單）

```python
# 在 Tier 1 analyzer 中（或新增 Tier 5 analyzer）：
# 現有：merged #11/#12 → sub-sync peak in 0.35-0.50X
# 增強：
if params.critical_speed is not None:
    f_critical = params.critical_speed / 60.0  # Hz
    if frequency_match(f_sub, f_critical, tolerance=0.05):
        → Oil Whip (#12), unmerge
    else:
        → Oil Whirl (#11), unmerge
```

**方案 B：多轉速瀑布圖分析**（複雜，需要全新資料模型）

→ **選擇方案 A**（Thompson：暴力法。Torvalds：修眼前的坑洞）

### 實作位置

不新增 Tier 5 analyzer。在 Tier 1 中增加判斷：
- 若 `critical_speed is None`：維持 merged #11/#12（現有行為）
- 若 `critical_speed is not None`：嘗試區分

這符合系統哲學：**tier 是 derived property，每個 analyzer 檢查自己的 prerequisites**。

### 檔案變動

| 檔案 | 變動 |
|------|------|
| `analyzers/tier1.py` | 修改 oil whirl/whip 判斷，利用 critical_speed |
| `pipeline.py` | 修改 merge group 邏輯：若已區分則不再 merge |
| `tests/test_tier1.py` | +whirl vs whip 區分測試 |
| `tests/test_pipeline.py` | +已區分時不 merge 的測試 |

### 測試策略

1. **Whirl 偵測**：sub-sync peak at 0.45X，critical_speed 遠高 → Oil Whirl
2. **Whip 偵測**：sub-sync peak ≈ critical_speed → Oil Whip
3. **向後相容**：無 critical_speed 時維持 merged 行為

### 複雜度評估

- 修改程式碼：~30-40 行
- 新增測試：~4-6 個
- 依賴：無新增

---

## 總覽：實作順序與依賴關係

```
           無依賴關係，可平行          有依賴
           ──────────────           ────────
Phase A:   Gap 1 (Kurtogram)  ──→  整合至 Tier 2
           Gap 3 (STFT/CWT)   ──→  供 Gap 2 使用
           Gap 5 (EMD)        ──→  可選整合至 Tier 2

Phase B:   Gap 2 (視覺化)     ←──  使用 Phase A 的 STFT/CWT 輸出
           Gap 7 (Whirl/Whip) ──→  獨立，僅修改 Tier 1

Phase C:   Gap 4 (階次追蹤)   ──→  需要 pipeline 架構微調
           Gap 6 (軸向振動)   ──→  需要 protocol 簽名變更
```

### 建議分批實作

| 批次 | Gap | 預估新增程式碼 | 預估新增測試 | 說明 |
|------|-----|---------------|-------------|------|
| **Batch 1** | Gap 1 + Gap 3 + Gap 5 | ~170-240 行 | ~16-21 個 | preprocessing 模組擴展，無架構變動 |
| **Batch 2** | Gap 2 + Gap 7 | ~180-240 行 | ~12-16 個 | 視覺化新模組 + Tier 1 小修改 |
| **Batch 3** | Gap 4 + Gap 6 | ~140-190 行 | ~10-14 個 | 需要 protocol/pipeline 微調 |

### 風險評估

| Gap | 風險 | 緩解 |
|-----|------|------|
| Gap 1 | Fast Kurtogram 演算法實作複雜度 | 可先用 brute-force grid search，再優化 |
| Gap 3 | pywt CWT scale↔freq 對應不直覺 | 封裝 `pywt.scale2frequency()` 轉換 |
| Gap 4 | 角度域重取樣的內插精度 | 使用 `scipy.interpolate.interp1d(kind='cubic')` |
| Gap 5 | EMD-signal 套件穩定性 | 限定版本，寫 fallback（若導入失敗則 skip） |
| Gap 6 | protocol 簽名變更影響所有 analyzer | 用 `**kwargs` 或可選參數避免破壞性變更 |

---

## 哲學總結

| 原則 | 在本計畫中的體現 |
|------|----------------|
| **Thompson: 由下而上** | 先擴展 preprocessing primitives (Gap 1,3,5) → 再整合至 analyzers (Gap 2,7) → 最後調整架構 (Gap 4,6) |
| **Thompson: 做一件事** | 每個新函數只做一件事：`compute_stft()`, `compute_cwt()`, `compute_emd()`, `compute_kurtogram()` |
| **Thompson: 暴力法** | Gap 1 先用 grid search；Gap 7 先用 critical_speed 而非瀑布圖 |
| **Knuth: 數學嚴謹** | 所有頻率公式有明確定義；kurtosis 使用 Fisher 定義；複雜度已分析 |
| **Knuth: 97%/3%** | Gap 3 (STFT/CWT) 和 Gap 5 (EMD) 在穩態場景不是效能瓶頸，封裝即可 |
| **Torvalds: 資料結構** | Gap 4 新增 `tach_pulses` 驅動行為；Gap 6 用可選參數避免破壞性變更 |
| **Torvalds: 消除 special case** | Gap 6 消除 #9 的 partial diagnosis；Gap 7 消除 whirl/whip 的 merged 狀態 |
| **Torvalds: 不要過度設計** | 不造「通用時頻分析框架」、不造「繪圖引擎」、不造「多通道資料模型」 |
