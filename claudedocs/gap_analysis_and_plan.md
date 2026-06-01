# Gap Analysis: research_vibration_fault_diagnosis.md vs 實際實作

> 分析日期：2026-03-13
> 範圍：Section 一（20 種故障模式）+ Section 二（傳統診斷方法）

---

## 一、20 種故障模式分類 — 完成度對照

| # | 故障名稱 | 實作位置 | 狀態 | 備註 |
|---|---------|---------|------|------|
| 1 | 不平衡 | tier1.py | ✅ 完成 | 1X dominant + energy ratio + 2X/1X < 0.5 |
| 2 | 軸彎曲 | tier1.py | ✅ 完成 | 1X elevated + 2X/1X > 0.5 |
| 3 | 平行不對中 | tier1.py | ✅ 完成 | 2X dominant |
| 4 | 內環損傷 | tier2.py | ✅ 完成 | BPFI harmonics + 1X sidebands (envelope) |
| 5 | 外環損傷 | tier2.py | ✅ 完成 | BPFO harmonics, sideband penalty |
| 6 | 軸承座鬆動 | tier1.py | ✅ 完成 | ≥5 harmonics + sub-harmonic (0.5X/1/3X/1/4X) |
| 7 | 滾珠損傷 | tier2.py | ✅ 完成 | BSF + FTF sidebands (classic + sideband-only) |
| 8 | 氣隙不均 | tier3.py | ✅ 完成 | 2FL + Fp sidebands |
| 9 | 角度不對中 | tier1.py | ⚠️ 部分 | 僅偵測 1X elevated（缺少軸向振動分析） |
| 10 | 相位問題 | tier3.py | ✅ 完成 | Merged with #13, 2FL without Fp sidebands |
| 11 | 油膜旋振 | tier1.py | ✅ 完成 | Merged with #12, 0.35–0.50X sub-sync |
| 12 | 油膜晃盪 | tier1.py | ✅ 完成 | Merged with #11 |
| 13 | 繞組短路 | tier3.py | ✅ 完成 | Merged with #10 |
| 14 | 轉子斷條 | tier3.py | ✅ 完成 | Merged with #15, 1X + Fp sidebands + RBPF |
| 15 | 端環短路 | tier3.py | ✅ 完成 | Merged with #14 |
| 16 | 齒輪不對中 | tier4.py | ✅ 完成 | GMF + asymmetric sidebands |
| 17 | 齒輪斷齒 | tier4.py | ✅ 完成 | Kurtosis + GMF harmonics + cepstrum rahmonic |
| 18 | 齒輪偏心 | tier4.py | ✅ 完成 | GMF ± 1X symmetric sidebands |
| 19 | 齒輪軸彎曲 | tier4.py | ✅ 完成 | 1X + 2X + GMF sidebands |
| 20 | 齒輪磨損 | tier4.py | ✅ 完成 | ≥3 GMF harmonics + broadband energy |

**結論**：20/20 故障全部已實作。#9 Angular Misalignment 為 partial diagnosis（設計如此，需要多通道軸向數據才能完整診斷）。

---

## 二、第一階段傳統方法 — 完成度對照

### 2.1 核心訊號處理技術

| 方法 | 研究文件編號 | 實作狀態 | 實作位置 | 備註 |
|------|-------------|---------|---------|------|
| **FFT 頻譜分析** | 2.1-A | ✅ 完成 | `preprocessing.py: compute_fft()` | 含 PSD (`compute_psd()`) |
| **包絡線分析** | 2.1-B | ✅ 完成 | `preprocessing.py: compute_envelope()` | Hilbert + bandpass + FFT |
| **倒頻譜分析** | 2.1-C | ✅ 完成 | `preprocessing.py: compute_cepstrum()` | Log-power cepstrum |
| **階次追蹤** | 2.1-D | ❌ 未實作 | — | 變速工況下的角度域重取樣 |
| **時頻分析 (STFT/CWT)** | 2.1-E | ❌ 未實作 | — | pywt 已列為依賴但未使用 |
| **EMD** | 2.1-F | ❌ 未實作 | — | PyEMD 未列為依賴 |
| **峭度圖 (Kurtogram)** | 6.8 | ❌ 未實作 | — | 軸承最佳濾波頻帶選擇 |
| **頻譜峭度** | 6.8 | ❌ 未實作 | — | 軸承故障早期偵測增強 |

### 2.2 各故障類別診斷規則

| 類別 | 實作狀態 | 缺失項目 |
|------|---------|---------|
| **轉子類** (#1, #2) | ✅ 完成 | 缺少：軸向振動分析（需多通道輸入） |
| **對中類** (#3, #9) | ⚠️ 部分 | #9 缺少：軸向 1X 分析（partial diagnosis by design） |
| **軸承類** (#4, #5, #6, #7) | ✅ 完成 | — |
| **電氣類** (#8, #10, #13, #14, #15) | ✅ 完成 | 缺少：MCSA（需要電流訊號，屬 Tier 5） |
| **流體類** (#11, #12) | ✅ 完成 | 缺少：瀑布圖、臨界轉速追蹤（區分 whirl vs whip） |
| **齒輪類** (#16-#20) | ✅ 完成 | — |

### 2.3 規則引擎架構

| 項目 | 實作狀態 | 說明 |
|------|---------|------|
| 前處理（去趨勢、濾波） | ✅ 完成 | detrend, bandpass_filter, apply_window |
| 多路分析 | ✅ 完成 | FFT + Envelope + Cepstrum + Time-domain |
| 特徵頻率提取 | ✅ 完成 | frequencies.py (bearing + electrical + gear) |
| 特徵比對（規則引擎） | ✅ 完成 | 每個 analyzer 內含規則匹配 |
| 故障分類 + 信心度 | ✅ 完成 | FaultCandidate + confidence modifiers |
| 衝突解決 | ✅ 完成 | pipeline.py: mutual exclusion + merge groups |
| ISO 10816 嚴重度 | ✅ 完成 | tier0.py: Class I-IV, Zones A-D |

### 2.4 Python 工具使用

| 套件 | 研究文件要求 | 實作狀態 | 說明 |
|------|-------------|---------|------|
| `numpy.fft` | FFT / 頻譜分析 | ✅ 使用中 | preprocessing.py |
| `scipy.signal` | 濾波、Hilbert、Welch | ✅ 使用中 | preprocessing.py |
| `pywt` | 小波轉換 (CWT) | ❌ 已列依賴但未使用 | pyproject.toml 未列 |
| `PyEMD` | EMD | ❌ 未列依賴、未使用 | — |
| `matplotlib` | 視覺化 | ❌ 已列依賴但未使用 | pyproject.toml 有列 |
| `plotly` | 視覺化 | ❌ 已列依賴但未使用 | pyproject.toml 有列 |

---

## 三、Gap 彙整

### Gap 1: 階次追蹤 (Order Tracking) — 2.1-D

- **用途**：變速工況下的故障診斷，將時域訊號重取樣至角度域
- **影響**：目前系統假設恆速工況。若輸入訊號來自變速機組，所有基於轉頻的診斷精度將降低
- **實作需求**：
  - 角度域重取樣 (angular resampling)
  - 需要 tachometer 脈衝訊號或 RPM profile 作為輸入
  - `MachineParameters` 需新增 RPM profile 欄位
- **優先級**：中（需要額外感測器輸入，非所有使用情境都需要）
- **預估複雜度**：中

### Gap 2: 時頻分析 STFT / CWT — 2.1-E

- **用途**：暫態訊號分析、啟停機過程診斷
- **影響**：無法分析非穩態訊號（如啟機、停機、瞬態衝擊）
- **實作需求**：
  - STFT: `scipy.signal.stft()` 已有現成工具
  - CWT: `pywt.cwt()` 需加入依賴
  - 可視為 preprocessing 模組的擴展
- **優先級**：中低（穩態分析已覆蓋大部分工業場景）
- **預估複雜度**：低（封裝 scipy/pywt 即可）

### Gap 3: 經驗模態分解 EMD — 2.1-F

- **用途**：自適應分解非線性、非穩態訊號為 IMF
- **影響**：缺少一種可增強軸承早期故障偵測的方法（與包絡線分析結合）
- **實作需求**：
  - 新增 `PyEMD` 依賴
  - 實作 EMD → IMF 提取 → 選擇性包絡分析
- **優先級**：低（包絡線分析已覆蓋主要軸承故障偵測需求）
- **預估複雜度**：低

### Gap 4: 峭度圖 / 頻譜峭度 (Kurtogram / Spectral Kurtosis) — 6.8

- **用途**：自動選擇軸承故障包絡分析的最佳帶通濾波頻帶
- **影響**：目前 Tier 2 包絡分析使用固定帶通範圍，可能錯過某些非典型共振頻帶
- **實作需求**：
  - Fast Kurtogram 演算法實作
  - 整合至 Tier 2 analyzer 作為自動頻帶選擇前處理
- **優先級**：中高（直接提升軸承故障偵測靈敏度）
- **預估複雜度**：中

### Gap 5: 視覺化模組 — 2.4

- **用途**：頻譜圖、包絡頻譜圖、倒頻譜圖、時域波形、瀑布圖
- **影響**：使用者無法透過圖形直觀驗證診斷結果
- **實作需求**：
  - 基礎繪圖函數（頻譜、時域、包絡）
  - 瀑布圖（需要多組時序資料）
  - matplotlib 已為依賴，只需建立繪圖模組
- **優先級**：中（對使用者體驗重要，但不影響診斷核心功能）
- **預估複雜度**：中

### Gap 6: 軸向振動分析 — 轉子/對中類診斷增強

- **用途**：完善 #2 軸彎曲（軸向 1X）、#9 角度不對中（軸向 1X 顯著）
- **影響**：#9 目前為 partial diagnosis
- **實作需求**：
  - `MachineParameters` 或訊號輸入需支援多通道（徑向 + 軸向）
  - 修改 tier1.py 對應規則
- **優先級**：低（需要硬體感測器配置變更，非軟體限制）
- **預估複雜度**：中

### Gap 7: 油膜旋振 vs 油膜晃盪區分 — 流體類診斷增強

- **用途**：目前 #11/#12 merged，無法區分 whirl（頻率隨轉速線性增加）和 whip（鎖定臨界轉速）
- **影響**：合理的限制（區分需要多轉速資料或臨界轉速資訊）
- **實作需求**：
  - 需要多轉速下的振動資料（瀑布圖分析）
  - 或 `MachineParameters` 加入 `critical_speed` 欄位
  - 這屬於 Tier 5 (設計規劃中但 deferred)
- **優先級**：低
- **預估複雜度**：高（需要系統架構調整）

---

## 四、建議實作優先序

基於「投入產出比」與「對現有診斷能力的提升幅度」排序：

| 優先序 | Gap | 理由 |
|--------|-----|------|
| 1 | **Gap 4: Kurtogram** | 直接提升軸承故障偵測靈敏度，自動頻帶選擇 |
| 2 | **Gap 5: 視覺化模組** | 使用者可視化驗證，依賴已就緒 |
| 3 | **Gap 2: STFT/CWT** | 擴展至非穩態場景，實作複雜度低 |
| 4 | **Gap 1: 階次追蹤** | 變速機組支援，但需額外感測器輸入 |
| 5 | **Gap 3: EMD** | 增強軸承早期偵測，但包絡分析已覆蓋主要場景 |
| 6 | **Gap 6: 軸向振動** | 需多通道輸入架構調整 |
| 7 | **Gap 7: Whirl/Whip 區分** | 需多轉速資料或臨界轉速（Tier 5 範疇） |

---

## 五、總結

### 已完成
- ✅ 20/20 故障模式全部已實作診斷規則
- ✅ 3/6 核心訊號處理技術（FFT、Envelope、Cepstrum）
- ✅ 規則引擎架構完整（前處理 → 多路分析 → 規則匹配 → 信心度 → 衝突解決）
- ✅ ISO 10816 嚴重度評估
- ✅ CLI 介面支援所有 Tier 參數
- ✅ 141 個測試全部通過

### 未完成（7 個 Gap）
- ❌ 3/6 核心訊號處理技術（Order Tracking、STFT/CWT、EMD）
- ❌ 峭度圖（軸承診斷增強）
- ❌ 視覺化模組
- ❌ 多通道（軸向）振動支援
- ❌ 油膜 Whirl/Whip 區分

### 評估
第一階段傳統方法的**核心功能已完成**（20 故障 × 規則引擎 × 信心度評分）。未完成的 Gap 多屬於**進階增強**（如 Kurtogram 提升靈敏度）或**需要額外硬體/資料輸入**（如 Order Tracking 需 tachometer、軸向分析需多通道感測器）。建議根據實際應用場景選擇性實作。
