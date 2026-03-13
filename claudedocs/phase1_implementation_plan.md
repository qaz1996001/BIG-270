# Phase 1 Implementation Plan

# 振動故障分類系統 Phase 1 實作計劃

> 建立日期：2026-03-11
> 類型：Implementation Plan / 實作計劃
> 狀態：In Progress
> 參考：`brainstorm_parameter_driven_classification.md`, `research_vibration_fault_diagnosis.md`

---

## 1. Phase 1 總覽

Phase 1 涵蓋 **Tier 0-2** 的完整分析能力，以「手上有什麼參數就分析到什麼程度」為設計原則。

### 覆蓋範圍

| 項目 | 規格 |
|------|------|
| Tier 範圍 | Tier 0（純加速度）→ Tier 1（+RPM）→ Tier 2（+bearing_geometry） |
| 故障數量 | **10 faults**：8 specific + 1 merged group（Sub-synchronous Instability） |
| Tier 0 | Health assessment only — ISO 10816 severity, time-domain indicators |
| Tier 1 | 5 specific faults + 1 merged group + 3 bearing category = 7 addressable |
| Tier 2 | 8 specific faults + 1 merged group = **10 addressable** |

### Phase 1 可診斷的故障清單

| # | Fault 故障 | Category | Tier 1 | Tier 2 |
|---|-----------|----------|--------|--------|
| 1 | Unbalance 不平衡 | Rotor | **S** | S |
| 2 | Bent Shaft 軸彎曲 | Rotor | **S** | S |
| 3 | Parallel Misalignment 平行不對中 | Alignment | **S** | S |
| 4 | Inner Race Defect 內環損傷 | Bearing | C | **S** |
| 5 | Outer Race Defect 外環損傷 | Bearing | C | **S** |
| 6 | Looseness 軸承座鬆動 | Structural | **S** | S |
| 7 | Ball Defect 滾珠損傷 | Bearing | C | **S** |
| 9 | Angular Misalignment 角度不對中 | Alignment | **S** | S |
| 11+12 | Oil Whirl/Whip 油膜旋振/晃盪 | Fluid | **M** | M |

> **S** = Specific, **C** = Category only, **M** = Merged group

### 技術棧

| 工具 | 用途 | 版本要求 |
|------|------|---------|
| **Python** | Runtime | 3.12+ |
| **uv** | Package manager / virtual environment | latest |
| **ruff** | Linter + formatter（取代 black, isort, flake8） | latest |
| **ty** | Type checker（取代 mypy） | latest |
| **NumPy** | 數值計算、FFT | >=1.26 |
| **SciPy** | Signal processing（Hilbert, filters） | >=1.12 |
| **pytest** | Testing framework | >=8.0 |

---

## 2. 模組清單與狀態

| Module | Path | Status | Description |
|--------|------|--------|-------------|
| Core Models | `src/vibfault/core/models.py` | Done | `MachineParameters`, `BearingGeometry`, `DiagnosisResult`, severity enums |
| Preprocessing | `src/vibfault/core/preprocessing.py` | Done | FFT (`compute_fft`), envelope analysis (`envelope_spectrum`), time-domain features (`time_domain_features`), `velocity_rms` |
| Frequencies | `src/vibfault/core/frequencies.py` | Done | BPFI/BPFO/BSF/FTF calculation (`bearing_frequencies`), `frequency_match` with configurable tolerance |
| Analyzer Protocol | `src/vibfault/analyzers/protocol.py` | Done | `Analyzer` protocol definition, `FaultCandidate` dataclass |
| Tier 0 Analyzer | `src/vibfault/analyzers/tier0.py` | Done | Health assessment — ISO 10816 severity classification, time-domain anomaly detection |
| Tier 1 Analyzer | `src/vibfault/analyzers/tier1.py` | Done | Order analysis — 1X/2X/nX 特徵提取, sub-synchronous detection, 6 fault rules |
| Tier 2 Analyzer | `src/vibfault/analyzers/tier2.py` | Done | Envelope analysis — BPFI/BPFO/BSF/FTF matching, 3 bearing fault specific diagnosis |
| Pipeline | `src/vibfault/pipeline.py` | Done | Tier 自動選擇, analyzer orchestration, conflict resolution logic |
| Tests | `tests/` | **Done** | 141 tests across 8 files — unit + integration for all modules |
| CLI | `src/vibfault/__main__.py` | **Done** | argparse CLI with CSV/WAV input, JSON/text output |

### 模組依賴關係

```
MachineParameters ──┐
BearingGeometry  ───┤
                    ▼
              ┌─────────────┐
              │  Pipeline    │  orchestration + conflict resolution
              └──────┬──────┘
                     │ dispatches to
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Tier 0  │ │ Tier 1  │ │ Tier 2  │
   │ (health)│ │ (order) │ │ (envlp) │
   └────┬────┘ └────┬────┘ └────┬────┘
        │            │            │
        └────────────┼────────────┘
                     ▼
        ┌────────────────────────┐
        │  Core: preprocessing   │  FFT, envelope, time-domain
        │  Core: frequencies     │  BPFI/BPFO/BSF/FTF
        │  Core: models          │  data structures
        └────────────────────────┘
```

---

## 3. 測試計劃

### 3.1 Unit Tests

每個模組皆有對應的 unit test 檔案，使用已知解析輸入（known analytical inputs）驗證正確性。

| Test File | 測試對象 | 重點 |
|-----------|---------|------|
| `test_preprocessing.py` | `preprocessing.py` | `compute_fft` 對已知正弦波的頻率/振幅、`envelope_spectrum` 對調幅訊號的解調、`time_domain_features` 的 RMS/Peak/Kurtosis/Crest Factor、`velocity_rms` 積分正確性 |
| `test_frequencies.py` | `frequencies.py` | 軸承特徵頻率公式（BPFI/BPFO/BSF/FTF）與手算結果比對、`frequency_match` 的容差邏輯（±3% 預設值） |
| `test_tier0.py` | `tier0.py` | ISO 10816 severity classification 各等級邊界值、time-domain health indicators 的閾值判定 |
| `test_tier1.py` | `tier1.py` | Order feature extraction（1X, 2X, sub-synchronous）、6 條 fault rules 各自的觸發與非觸發條件 |
| `test_tier2.py` | `tier2.py` | Envelope analysis 對合成軸承訊號的偵測能力、BPFI/BPFO/BSF 各缺陷的判定邏輯 |
| `test_pipeline.py` | `pipeline.py` | Full pipeline 從 `MachineParameters` 到 `DiagnosisResult` 的完整流程、Tier 自動選擇邏輯、conflict resolution |

### 3.2 Integration Tests

以合成訊號（synthetic signals）模擬真實故障場景，驗證端到端的診斷正確性。

| 場景 | 合成訊號描述 | 預期結果 |
|------|-------------|---------|
| Unbalance 不平衡 | Strong 1X component at shaft frequency, low 2X | Fault #1 Unbalance, high confidence |
| Bearing Outer Race 外環損傷 | BPFO harmonics modulated on high-frequency carrier | Fault #5 Outer Race Defect, via envelope analysis |
| No RPM 無轉速 | 純加速度訊號, RPM=None | Tier 0 only — ISO severity + health indicators, no specific fault |
| Multiple Faults 複合故障 | 1X dominant + BPFO harmonics | Fault #1 + Fault #5, conflict resolver 不互斥 |
| Looseness 鬆動 | Rich sub-harmonic content (0.5X, 1X, 2X, 3X...) | Fault #6 Looseness |

### 3.3 Validation with Public Datasets

| 資料集 | 用途 | 狀態 |
|--------|------|------|
| **CWRU Bearing Data Center** | 軸承故障（inner race, outer race, ball）12kHz/48kHz 取樣 | Future — Phase 1 完成後使用 |
| **MFPT Bearing Fault Dataset** | 額外的軸承故障驗證 | Future |

---

## 4. 里程碑 (Milestones)

| # | Milestone | Deliverable | Status |
|---|-----------|-------------|--------|
| M1 | Core Infrastructure | `models.py`, `preprocessing.py`, `frequencies.py` — 資料結構與訊號處理基礎 | **DONE** |
| M2 | Tier 0-2 Analyzers | `tier0.py`, `tier1.py`, `tier2.py` — 三層分析器完整實作 | **DONE** |
| M3 | Pipeline Integration | `pipeline.py` — Tier 自動選擇 + analyzer orchestration + conflict resolution | **DONE** |
| M4 | Test Suite | 141 tests: unit + integration for all modules (8 test files) | **DONE** |
| M5 | Validation | 使用 CWRU bearing dataset 驗證，調整 thresholds 與 confidence weights | **TODO** (deferred) |
| M6 | Documentation & CLI | CLI with argparse, CSV/WAV input, JSON output, --help | **DONE** |

### 當前進度

```
M1 ████████████ Done
M2 ████████████ Done
M3 ████████████ Done
M4 ████████████ Done (141 tests, all passing)
M5 ░░░░░░░░░░░░ TODO (deferred — CWRU dataset validation)
M6 ████████████ Done (CLI + docstrings)
```

---

## 5. 下一步 (Next Steps)

以優先順序排列：

1. **Write unit tests for all modules**
   - 從 `test_preprocessing.py` 開始（最底層、無依賴）
   - 逐層向上：`frequencies` → `tier0` → `tier1` → `tier2` → `pipeline`
   - 目標覆蓋率：90%+

2. **Create synthetic test signals for each fault type**
   - 建立 `tests/fixtures/` 目錄存放合成訊號生成器
   - 每種故障至少一組標準測試訊號 + 一組邊界情況

3. **Validate with CWRU bearing dataset**
   - 下載 CWRU 12kHz normal/inner/outer/ball 資料
   - 建立 validation script，比對診斷結果與已知標籤
   - 記錄 confusion matrix 與 per-fault accuracy

4. **Tune thresholds based on validation results**
   - 調整 `frequency_match` tolerance（目前 ±3%）
   - 調整各 fault rule 的 confidence weights
   - 調整 ISO 10816 severity boundaries

5. **Add CLI interface for interactive use**
   - 擴展 `__main__.py` 支援命令列參數
   - 支援 CSV/WAV 檔案輸入
   - 結構化 JSON 輸出

---

## 6. Phase 2 預覽

Phase 2 將擴展至 Tier 3-5，涵蓋電氣、齒輪、與進階分析能力。

| Tier | 新增能力 | 需要的額外參數 | 新增故障 |
|------|---------|---------------|---------|
| **Tier 3** | Electrical fault analysis — 2FL analysis, pole-pass frequency sidebands | `pole_pairs`, `line_frequency` | #8 Air Gap, #10+#13 Stator Electrical (merged), #14 Broken Bar, #14+#15 Rotor Electrical (merged) |
| **Tier 4** | Gear fault analysis — GMF analysis, cepstrum, sideband symmetry | `gear_teeth_count` | #16-#20 五種齒輪故障 |
| **Tier 5** | MCSA + waterfall — 完整電流分析與瀑布圖 | `current_signal`, `critical_speed` | 所有 merged groups 拆分為 specific，達成 20/20 全覆蓋 |

### ML Integration Roadmap

Phase 2 後期將逐步導入機器學習，與傳統方法並行（hybrid approach）：

```
Stage 1: SVM / Random Forest
  └─ 使用傳統特徵（RMS, Kurtosis, order amplitudes）作為輸入
  └─ 與 rule-based 結果做 ensemble voting

Stage 2: 1D-CNN
  └─ 直接輸入 raw vibration signal
  └─ 學習自動提取時頻特徵

Stage 3: Transformer / Foundation Model
  └─ Pre-trained vibration foundation model
  └─ Few-shot adaptation for new machine types
```

---

> **Design Philosophy Reminder:**
> 「根據手上有什麼參數，自動決定能分多細」—— 系統不會因為缺少參數而失敗，
> 只會退回到能力範圍內的最佳診斷結果。
