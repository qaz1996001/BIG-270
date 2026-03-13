# Parameter-Driven Adaptive Vibration Fault Classification System

# 參數驅動的自適應振動故障分類系統 — 需求規格與分類映射

> 建立日期：2026-03-09
> 類型：Brainstorm / 需求規格
> 狀態：Draft
> 參考：`research_vibration_fault_diagnosis.md`

---

## 設計哲學

本系統的核心理念：**根據「手上有什麼參數」自動決定「能分多細」**，而非在缺參數時直接失敗。

| 哲學家 | 原則 | 在本系統的體現 |
|--------|------|---------------|
| **Ken Thompson** | 由底而上：從最小可用單元開始 | 從純加速度（Tier 0）開始，逐層疊加分析能力 |
| **Donald Knuth** | 數學嚴謹：公式精確、容差有依據 | 特徵頻率公式完整推導，容差 ±3% 來自 ISO/工程實踐 |
| **Linus Torvalds** | 資料結構決定行為 | nullable 欄位取代控制旗標；Tier 由資料自動浮現，非硬編碼分支 |
| **Martin Fowler** | YAGNI + 演化設計 | Phase 1 只做 Tier 0-2（10 種故障），後續按需擴展 |

---

## 1. 參數層級系統（Parameter Tier System）

### 1.1 Tier 定義總覽

| Tier | Required Parameters | Unlocked Methods | Diagnosable Faults |
|------|--------------------|-----------------|--------------------|
| **0** | acceleration + sampling_rate | 時域統計（RMS, Peak, Kurtosis, Crest Factor）、raw FFT、ISO 10816 severity | 0 specific / health assessment only |
| **1** | + rpm | FFT order mapping、sub-synchronous detection、harmonic counting、1X/2X/nX analysis | 5 specific + 2 merged = **7** |
| **2** | + bearing_geometry (or bearing_model) | Envelope analysis、kurtogram、BPFI/BPFO/BSF/FTF matching | 8 specific + 2 merged = **10** |
| **3** | + electrical_params (pole_pairs, line_freq) | 2FL analysis、pole-pass frequency sidebands | 9 specific + 3 merged = **14** |
| **4** | + gear_teeth_count | GMF analysis、cepstrum、sideband symmetry | 14 specific + 3 merged = **19** |
| **5** | + current_signal + critical_speed | MCSA、waterfall plot | 20 specific = **full coverage** |

### 1.2 Tier 自動計算邏輯

```
def compute_tier(params: MachineParameters) -> int:
    """Tier is a DERIVED property, not a stored value.
    It emerges from which fields are non-null."""

    if params.current_signal is not None and params.critical_speed is not None:
        return 5
    if params.gear_teeth is not None:
        return 4
    if params.pole_pairs is not None and params.line_frequency is not None:
        return 3
    if params.bearing is not None:  # BearingGeometry or model lookup
        return 2
    if params.rpm is not None:      # manual or auto-estimated
        return 1
    return 0  # Always reachable: acceleration + sampling_rate is minimum
```

**Key design choice (Torvalds):** Tier 由資料結構自動決定，無 `if tier == 2` 之類的控制分支。每個分析模組自行檢查「我需要的參數存在嗎？」，存在就執行，不存在就跳過。

### 1.3 RPM 策略

| Source | `rpm_source` tag | Confidence Multiplier |
|--------|------------------|-----------------------|
| Manual input | `"manual"` | ×1.0 |
| Tachometer signal | `"tachometer"` | ×0.95 |
| Auto-estimated from FFT peak | `"auto_estimated"` | ×0.7 |

Auto-estimation method: 在 FFT 中找 10-200 Hz 範圍內的最大峰值，假設為 1X 轉頻，反推 RPM。標記為 `rpm_source: "auto_estimated"`，所有依賴 RPM 的診斷結果信心度 ×0.7。

---

## 2. 完整 Tier-to-Fault 矩陣（20 Faults × 6 Tiers）

Legend:
- **S** = Specific diagnosis（可具體判定）
- **P** = Partial（可偵測但無法完全區分）
- **M** = Merged（與其他故障合併為一組報告）
- **C** = Category only（僅能判定類別，如「軸承問題」）
- **—** = Not diagnosable at this tier

| # | Fault 故障 | Category | T0 | T1 | T2 | T3 | T4 | T5 |
|---|-----------|----------|----|----|----|----|----|----|
| 1 | Unbalance 不平衡 | Rotor | — | **S** | S | S | S | S |
| 2 | Bent Shaft 軸彎曲 | Rotor | — | **S** | S | S | S | S |
| 3 | Parallel Misalignment 平行不對中 | Alignment | — | **S** | S | S | S | S |
| 4 | Inner Race Defect 內環損傷 | Bearing | — | C | **S** | S | S | S |
| 5 | Outer Race Defect 外環損傷 | Bearing | — | C | **S** | S | S | S |
| 6 | Looseness 軸承座鬆動 | Structural | — | **S** | S | S | S | S |
| 7 | Ball Defect 滾珠損傷 | Bearing | — | C | **S** | S | S | S |
| 8 | Air Gap Eccentricity 氣隙不均 | Electrical | — | — | — | **S** | S | S |
| 9 | Angular Misalignment 角度不對中 | Alignment | — | **S** | S | S | S | S |
| 10 | Phase Problem 相位問題 | Electrical | — | — | — | **M** | M | **S** |
| 11 | Oil Whirl 油膜旋振 | Fluid | — | **M**¹ | M | M | M | **S** |
| 12 | Oil Whip 油膜晃盪 | Fluid | — | **M**¹ | M | M | M | **S** |
| 13 | Winding Short 繞組短路 | Electrical | — | — | — | **M**² | M | **S** |
| 14 | Broken Rotor Bar 轉子斷條 | Electrical | — | — | — | **S** | S | S |
| 15 | End Ring Short 端環短路 | Electrical | — | — | — | **M**³ | M | **S** |
| 16 | Gear Misalignment 齒輪不對中 | Gear | — | — | — | — | **S** | S |
| 17 | Broken Tooth 齒輪斷齒 | Gear | — | — | — | — | **S** | S |
| 18 | Gear Eccentricity 齒輪偏心 | Gear | — | — | — | — | **S** | S |
| 19 | Gear Shaft Bend 齒輪軸彎曲 | Gear | — | — | — | — | **S** | S |
| 20 | Gear Wear 齒輪磨損 | Gear | — | — | — | — | **S** | S |

### Merge Groups 合併組說明

| ID | Merge Group | Members | Tier Available | 拆分條件 |
|----|------------|---------|----------------|---------|
| ¹ | Sub-synchronous Instability 次同步不穩定 | #11 Oil Whirl + #12 Oil Whip | T1 | T5: 需 critical_speed 區分 whirl（頻率追蹤轉速）vs whip（鎖定臨界轉速）|
| ² | Stator Electrical Fault 定子電氣故障 | #10 Phase + #13 Winding Short | T3 | T5: MCSA 可區分電壓不平衡 vs 匝間短路 |
| ³ | Rotor Electrical Fault 轉子電氣故障 | #14 Broken Bar + #15 End Ring | T3 (partial) | T5: MCSA 邊帶模式差異可區分 |

### Tier 統計彙總

| Tier | Specific | Merged (groups) | Category | Not Diagnosable | Total Addressable |
|------|----------|-----------------|----------|-----------------|-------------------|
| 0 | 0 | 0 | 0 | 20 | 0 |
| 1 | 5 | 2 (1 group) | 3 (bearing) | 10 | 7+3=10 |
| 2 | 8 | 2 (1 group) | 0 | 10 | 10 |
| 3 | 9 | 3 (2 groups) | 0 | 5 | 14 (with merges) |
| 4 | 14 | 3 (2 groups) | 0 | 0 | 19 (with merges) |
| 5 | 20 | 0 | 0 | 0 | 20 |

### Tier 0 特殊功能

Tier 0 無法診斷具體故障，但提供：
- **ISO 10816 Severity Assessment**：based on overall RMS velocity
- **Time-domain Health Indicators**：Kurtosis, Crest Factor, RMS trend
- **Raw FFT Anomaly Flag**：偵測異常頻率峰值（無法命名，但可標記位置）
- **Degradation Trend**：多次量測的 RMS/Kurtosis 趨勢追蹤

### Tier 1 Bearing Category Detection (without geometry)

在 Tier 1（有 RPM 但無軸承幾何），軸承故障（#4, #5, #7）以 Category "C" 偵測：
- 高頻包絡能量異常 + 非整數階次峰值 → 判定「Bearing fault suspected」
- 無法區分 inner/outer/ball，因為不知道 BPFI/BPFO/BSF 的精確頻率
- 峭度升高作為輔助證據

---

## 3. 資料結構設計（Data Structures）

### 3.1 MachineParameters

```python
@dataclass
class BearingGeometry:
    n_balls: int                    # Number of rolling elements
    ball_diameter: float            # Ball diameter (mm)
    pitch_diameter: float           # Pitch circle diameter (mm)
    contact_angle: float            # Contact angle (degrees)

@dataclass
class MachineParameters:
    """All fields nullable. Tier is a derived property.

    Torvalds principle: the data structure IS the control flow.
    No 'mode' flag, no 'tier' field. The presence/absence of data
    determines what analyses run.
    """

    # --- Tier 0 (always present) ---
    sampling_rate: float            # Hz, REQUIRED

    # --- Tier 1 ---
    rpm: Optional[float] = None
    rpm_source: Optional[str] = None  # "manual" | "tachometer" | "auto_estimated"

    # --- Tier 2 ---
    bearing: Optional[BearingGeometry] = None
    bearing_model: Optional[str] = None  # e.g., "SKF 6205" → lookup geometry

    # --- Tier 3 ---
    pole_pairs: Optional[int] = None
    line_frequency: Optional[float] = None  # 50 or 60 Hz

    # --- Tier 4 ---
    gear_teeth_drive: Optional[int] = None
    gear_teeth_driven: Optional[int] = None

    # --- Tier 5 ---
    critical_speed: Optional[float] = None  # RPM
    # current_signal handled separately as signal data, not parameter

    # --- Machine classification (for ISO 10816) ---
    machine_class: Optional[str] = None  # "I" | "II" | "III" | "IV"
    foundation_type: Optional[str] = None  # "rigid" | "flexible"

    @property
    def tier(self) -> int:
        """Derived, not stored."""
        if self.critical_speed is not None:
            return 5  # current_signal checked at pipeline level
        if self.gear_teeth_drive is not None:
            return 4
        if self.pole_pairs is not None and self.line_frequency is not None:
            return 3
        if self.bearing is not None or self.bearing_model is not None:
            return 2
        if self.rpm is not None:
            return 1
        return 0
```

### 3.2 DiagnosisResult

```python
@dataclass
class Evidence:
    feature_name: str          # e.g., "1X_amplitude", "BPFO_envelope"
    observed_value: float
    expected_range: Tuple[float, float]
    match_score: float         # 0.0 ~ 1.0
    description: str           # Human-readable explanation

@dataclass
class FaultDiagnosis:
    fault_id: int              # 1-20
    fault_name: str
    fault_category: str        # "Rotor" | "Alignment" | "Bearing" | ...
    diagnosis_type: str        # "S" | "P" | "M" | "C"
    confidence: float          # 0.0 ~ 1.0
    evidence: List[Evidence]
    merged_with: Optional[List[int]] = None  # fault_ids if merged

@dataclass
class DiagnosisResult:
    """Complete output of the diagnostic pipeline."""

    # --- Input context ---
    tier: int
    parameters: MachineParameters
    timestamp: datetime

    # --- Results ---
    iso_severity: str                    # "A-Good" | "B-Acceptable" | "C-Alert" | "D-Danger"
    iso_rms_velocity: float              # mm/s
    health_indicators: Dict[str, float]  # RMS, Kurtosis, Crest Factor, etc.

    diagnosed_faults: List[FaultDiagnosis]      # Sorted by confidence DESC
    not_diagnosable: List[str]                  # Faults that cannot be assessed at current tier
    suggested_parameters: List[str]             # "Provide bearing_model to unlock Tier 2"

    # --- Quality metadata ---
    rpm_source: Optional[str]
    confidence_modifier: float           # 1.0 for manual RPM, 0.7 for auto
    analysis_methods_used: List[str]     # ["FFT", "Envelope", "Cepstrum", ...]
    warnings: List[str]                  # e.g., "RPM auto-estimated, lower confidence"
```

### 3.3 Design Rationale

**為什麼不用 enum 或 flag 控制分析流程？**

```
# BAD (control flag approach):
if tier >= 2:
    run_envelope_analysis()
if tier >= 3:
    run_electrical_analysis()

# GOOD (data-driven approach):
# Each analyzer checks its own prerequisites
class EnvelopeAnalyzer:
    def can_run(self, params):
        return params.bearing is not None or params.bearing_model is not None

    def run(self, signal, params):
        if not self.can_run(params):
            return None  # Skip silently
        ...
```

Torvalds: 「好的程式設計師關心資料結構和它們的關係。」tier 不是存在參數裡的旗標，而是從資料自然浮現的性質。每個分析器只關心「我需要的欄位有沒有值」。

---

## 4. Pipeline 架構

### 4.1 執行流程

```
                    ┌──────────────────────────────────┐
                    │      Signal Input (acceleration)  │
                    └──────────────┬───────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │      Preprocessing                │
                    │  Detrend → Anti-alias → Window    │
                    └──────────────┬───────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
    ┌─────────▼────────┐ ┌────────▼────────┐ ┌─────────▼─────────┐
    │   Tier 0 Block   │ │  Tier 1 Block   │ │   Tier 2 Block    │
    │                  │ │  (needs rpm)    │ │ (needs bearing)   │
    │ - RMS            │ │ - Order map     │ │ - Kurtogram       │
    │ - Kurtosis       │ │ - 1X/2X/nX amp  │ │ - Envelope spec   │
    │ - Crest Factor   │ │ - Sub-sync det  │ │ - BPFI/BPFO match │
    │ - Raw FFT        │ │ - Harmonic cnt  │ │ - BSF/FTF match   │
    │ - ISO 10816      │ │                 │ │                   │
    └─────────┬────────┘ └────────┬────────┘ └─────────┬─────────┘
              │                    │                     │
              │     ┌──────────────┼─────────────────────┤
              │     │              │                      │
    ┌─────────▼─────▼──┐ ┌────────▼────────┐ ┌──────────▼────────┐
    │   Tier 3 Block   │ │  Tier 4 Block   │ │   Tier 5 Block    │
    │ (needs elec.)    │ │ (needs gear)    │ │ (needs current)   │
    │ - 2FL analysis   │ │ - GMF analysis  │ │ - MCSA            │
    │ - Pole-pass sdb  │ │ - Cepstrum      │ │ - Waterfall       │
    │ - RBPF sidebands │ │ - Sideband sym  │ │ - Whirl vs Whip   │
    └─────────┬────────┘ └────────┬────────┘ └──────────┬────────┘
              │                    │                      │
              └────────────────────┼──────────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │      Conflict Resolution          │
                    │  - Mutual exclusion rules         │
                    │  - Confidence weighting           │
                    │  - Evidence aggregation           │
                    └──────────────┬───────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │      Result Assembly              │
                    │  - Rank by confidence             │
                    │  - List not-diagnosable           │
                    │  - Suggest next parameters        │
                    └──────────────────────────────────┘
```

### 4.2 Analyzer Interface（每個分析模組的標準介面）

```python
class Analyzer(Protocol):
    """Every analysis block implements this interface.
    Thompson: each block is a composable primitive."""

    def prerequisites(self) -> List[str]:
        """Return list of required parameter field names."""
        ...

    def can_run(self, params: MachineParameters) -> bool:
        """Check if all prerequisites are non-null."""
        ...

    def analyze(self, signal: np.ndarray, params: MachineParameters) -> List[FaultCandidate]:
        """Run analysis, return fault candidates with evidence."""
        ...
```

### 4.3 Pipeline Execution Rules

1. **所有可執行的 Block 都會執行**：不是 if-else，是 filter-and-run
2. **Block 之間無依賴**：每個 Block 獨立產出 FaultCandidate list
3. **衝突解決在最後**：所有 candidates 匯集後統一處理
4. **缺參數 = 跳過，非失敗**：`can_run()` return False → pipeline 繼續

### 4.4 Conflict Resolution Rules

| Conflict Type | Resolution Strategy |
|---------------|-------------------|
| Same fault from multiple analyzers | 取最高 confidence，合併 evidence |
| Mutually exclusive faults (e.g., #1 vs #2) | 比較 evidence weight，保留較強者 |
| Merged group faults | 合併報告，標記 `diagnosis_type: "M"` |
| Low confidence (<0.3) | 降為 "suspected"，不列入主診斷 |

**Mutual Exclusion Table:**

| Pair | Reason | Resolution |
|------|--------|-----------|
| #1 Unbalance vs #2 Bent Shaft | Both show 1X dominant | 2X/1X ratio > 0.5 → Bent Shaft; else Unbalance |
| #3 Parallel vs #9 Angular Misalignment | Both at 1X-2X | Axial/Radial ratio: >0.7 → Angular; <0.3 → Parallel |
| #11 Oil Whirl vs #12 Oil Whip | Both sub-synchronous | Frequency tracking with RPM → Whirl; Locked → Whip |
| #1 Unbalance vs #8 Air Gap | 1X dominant in both | With electrical params: 2FL sidebands → Air Gap |

---

## 5. 規則引擎設計（Decision Table / Rule Engine）

### 5.1 Rule Definition Structure

```python
@dataclass
class DiagnosticRule:
    """Each fault has one or more diagnostic rules.
    Knuth: precise conditions, no ambiguity."""

    fault_id: int
    fault_name: str
    min_tier: int                        # Minimum tier to even attempt this rule
    required_features: List[str]         # Feature names that must be computed

    conditions: List[Condition]          # All must pass (AND logic)
    weight: float                       # 0.0 ~ 1.0, importance of this rule
    confidence_base: float              # Base confidence if all conditions pass
    confidence_modifiers: Dict[str, float]  # Situational adjustments

@dataclass
class Condition:
    feature: str                        # e.g., "1X_amplitude_ratio"
    operator: str                       # ">" | "<" | "between" | "peak_at"
    threshold: Union[float, Tuple[float, float]]
    tolerance: float = 0.03             # ±3% frequency tolerance
    description: str = ""
```

### 5.2 Complete Fault Rule Definitions

#### Tier 1 Faults（需要 RPM）

**Fault #1: Unbalance 不平衡**
```yaml
fault_id: 1
fault_name: "Unbalance"
min_tier: 1
conditions:
  - feature: "1X_is_dominant"
    operator: "=="
    threshold: true
    description: "1X is the highest peak in 0-10X range"
  - feature: "1X_amplitude_ratio"
    operator: ">"
    threshold: 0.6
    description: "1X accounts for >60% of total spectral energy in 0-5X band"
  - feature: "2X_to_1X_ratio"
    operator: "<"
    threshold: 0.5
    description: "2X is less than 50% of 1X (otherwise bent shaft)"
  - feature: "axial_to_radial_ratio"
    operator: "<"
    threshold: 0.3
    description: "Low axial vibration relative to radial"
confidence_base: 0.85
modifiers:
  rpm_auto_estimated: 0.7
  single_axis_only: 0.8
```

**Fault #2: Bent Shaft 軸彎曲**
```yaml
fault_id: 2
fault_name: "Bent Shaft"
min_tier: 1
conditions:
  - feature: "1X_amplitude"
    operator: ">"
    threshold: "elevated"  # Above baseline or ISO threshold
  - feature: "2X_to_1X_ratio"
    operator: ">"
    threshold: 0.5
    description: "2X is significant relative to 1X"
  - feature: "axial_1X_elevated"
    operator: "=="
    threshold: true
    description: "Axial 1X is notably high"
confidence_base: 0.80
```

**Fault #3: Parallel Misalignment 平行不對中**
```yaml
fault_id: 3
fault_name: "Parallel Misalignment"
min_tier: 1
conditions:
  - feature: "2X_is_dominant"
    operator: "=="
    threshold: true
    description: "2X is the highest or near-highest peak"
  - feature: "2X_amplitude"
    operator: ">"
    threshold: "elevated"
  - feature: "radial_dominant"
    operator: "=="
    threshold: true
    description: "Radial vibration >> axial"
confidence_base: 0.80
```

**Fault #9: Angular Misalignment 角度不對中**
```yaml
fault_id: 9
fault_name: "Angular Misalignment"
min_tier: 1
conditions:
  - feature: "axial_1X_dominant"
    operator: "=="
    threshold: true
    description: "Axial 1X is the most prominent feature"
  - feature: "axial_to_radial_ratio"
    operator: ">"
    threshold: 0.7
    description: "Axial vibration is high relative to radial"
confidence_base: 0.80
```

**Fault #6: Looseness 軸承座鬆動**
```yaml
fault_id: 6
fault_name: "Mechanical Looseness"
min_tier: 1
conditions:
  - feature: "harmonic_count"
    operator: ">="
    threshold: 5
    description: "5 or more harmonics of 1X visible"
  - feature: "sub_harmonic_present"
    operator: "=="
    threshold: true
    description: "0.5X sub-harmonic present"
  - feature: "broadband_floor_elevated"
    operator: "=="
    threshold: true
    description: "Overall noise floor is elevated"
confidence_base: 0.75
```

**Fault #11/#12: Oil Whirl/Whip 油膜旋振/晃盪（Tier 1 Merged）**
```yaml
fault_id: [11, 12]
fault_name: "Sub-synchronous Instability (Oil Whirl/Whip)"
min_tier: 1
diagnosis_type: "M"  # Merged at T1-T4; split at T5
conditions:
  - feature: "sub_sync_peak_present"
    operator: "=="
    threshold: true
    description: "Peak between 0.35X and 0.50X"
  - feature: "sub_sync_frequency_ratio"
    operator: "between"
    threshold: [0.35, 0.50]
    tolerance: 0.02
    description: "Sub-synchronous peak at 0.4X-0.48X range"
confidence_base: 0.70
split_condition: "T5: if sub_sync_freq tracks RPM → Whirl; if locked to critical_speed → Whip"
```

#### Tier 2 Faults（需要 Bearing Geometry）

**Fault #4: Inner Race Defect 內環損傷**
```yaml
fault_id: 4
fault_name: "Bearing Inner Race Defect"
min_tier: 2
conditions:
  - feature: "envelope_BPFI_present"
    operator: "=="
    threshold: true
    tolerance: 0.03  # ±3% of calculated BPFI
    description: "BPFI peak in envelope spectrum"
  - feature: "BPFI_harmonics_count"
    operator: ">="
    threshold: 2
    description: "At least 2 harmonics of BPFI visible"
  - feature: "BPFI_sidebands_1X"
    operator: "=="
    threshold: true
    description: "1X sidebands around BPFI (amplitude modulation)"
confidence_base: 0.85
modifiers:
  high_kurtosis: 1.1  # Kurtosis > 5 boosts confidence
  kurtogram_match: 1.15
```

**Fault #5: Outer Race Defect 外環損傷**
```yaml
fault_id: 5
fault_name: "Bearing Outer Race Defect"
min_tier: 2
conditions:
  - feature: "envelope_BPFO_present"
    operator: "=="
    threshold: true
    tolerance: 0.03
    description: "BPFO peak in envelope spectrum"
  - feature: "BPFO_harmonics_count"
    operator: ">="
    threshold: 2
    description: "At least 2 harmonics of BPFO"
  - feature: "no_significant_sidebands"
    operator: "=="
    threshold: true
    description: "BPFO typically shows NO prominent 1X sidebands"
confidence_base: 0.85
```

**Fault #7: Ball Defect 滾珠損傷**
```yaml
fault_id: 7
fault_name: "Bearing Ball Defect"
min_tier: 2
conditions:
  - feature: "envelope_BSF_present"
    operator: "=="
    threshold: true
    tolerance: 0.03
    description: "BSF peak in envelope spectrum"
  - feature: "BSF_or_2xBSF_with_FTF_sidebands"
    operator: "=="
    threshold: true
    description: "BSF with cage frequency (FTF) sidebands"
confidence_base: 0.70  # Lower base: ball defects are harder to detect
modifiers:
  kurtogram_band_match: 1.2
```

#### Tier 3 Faults（需要 Electrical Parameters）

**Fault #8: Air Gap Eccentricity 氣隙不均**
```yaml
fault_id: 8
fault_name: "Air Gap Eccentricity"
min_tier: 3
conditions:
  - feature: "2FL_peak_present"
    operator: "=="
    threshold: true
    description: "Peak at 2× line frequency (e.g., 100 Hz or 120 Hz)"
  - feature: "pole_pass_sidebands_around_2FL"
    operator: "=="
    threshold: true
    description: "Sidebands at 2FL ± Fp"
confidence_base: 0.80
```

**Fault #14: Broken Rotor Bar 轉子斷條**
```yaml
fault_id: 14
fault_name: "Broken Rotor Bar"
min_tier: 3
conditions:
  - feature: "1X_pole_pass_sidebands"
    operator: "=="
    threshold: true
    description: "Sidebands at 1X ± pole-pass frequency (Fp)"
  - feature: "RBPF_sidebands"
    operator: "=="
    threshold: true
    description: "Rotor bar pass frequency sidebands visible"
confidence_base: 0.75
modifiers:
  mcsa_available: 1.3  # MCSA greatly improves detection
```

**Fault #10/#13: Stator Electrical Merged 定子電氣合併**
```yaml
fault_id: [10, 13]
fault_name: "Stator Electrical Fault (Phase/Winding)"
min_tier: 3
diagnosis_type: "M"
conditions:
  - feature: "2FL_elevated"
    operator: "=="
    threshold: true
    description: "2× line frequency vibration elevated"
  - feature: "no_rotor_bar_sidebands"
    operator: "=="
    threshold: true
    description: "Absence of RBPF sidebands (rules out rotor faults)"
confidence_base: 0.65
split_condition: "T5: MCSA current spectrum distinguishes voltage unbalance vs winding short"
```

**Fault #15: End Ring Short 端環短路**
```yaml
fault_id: 15
fault_name: "End Ring Short"
min_tier: 3
diagnosis_type: "M"  # Merged with #14 at T3-T4
conditions:
  - feature: "similar_to_broken_bar"
    operator: "=="
    threshold: true
    description: "Pattern similar to broken rotor bar"
confidence_base: 0.50  # Very low without MCSA
split_condition: "T5: MCSA sideband amplitude pattern differs from broken bar"
```

#### Tier 4 Faults（需要 Gear Teeth Count）

**Fault #16: Gear Misalignment 齒輪不對中**
```yaml
fault_id: 16
fault_name: "Gear Misalignment"
min_tier: 4
conditions:
  - feature: "GMF_present"
    operator: "=="
    threshold: true
    description: "Gear mesh frequency peak visible"
  - feature: "GMF_sideband_asymmetry"
    operator: ">"
    threshold: 0.3
    description: "Sidebands around GMF are asymmetric (>30% difference)"
  - feature: "2xGMF_elevated"
    operator: "=="
    threshold: true
    description: "2nd harmonic of GMF elevated"
confidence_base: 0.80
```

**Fault #17: Broken Tooth 齒輪斷齒**
```yaml
fault_id: 17
fault_name: "Gear Broken Tooth"
min_tier: 4
conditions:
  - feature: "time_domain_impulse_periodic"
    operator: "=="
    threshold: true
    description: "Periodic impulse in time domain at gear rotation period"
  - feature: "GMF_harmonics_elevated"
    operator: "=="
    threshold: true
    description: "Multiple GMF harmonics with increased amplitude"
  - feature: "cepstrum_rahmonic_at_gear_period"
    operator: "=="
    threshold: true
    description: "Cepstrum shows rahmonic at 1/shaft_speed"
confidence_base: 0.85
```

**Fault #18: Gear Eccentricity 齒輪偏心**
```yaml
fault_id: 18
fault_name: "Gear Eccentricity"
min_tier: 4
conditions:
  - feature: "GMF_1X_sidebands"
    operator: "=="
    threshold: true
    description: "1X sidebands around GMF (amplitude modulation)"
  - feature: "1X_elevated"
    operator: "=="
    threshold: true
    description: "1X component also elevated"
confidence_base: 0.75
```

**Fault #19: Gear Shaft Bend 齒輪軸彎曲**
```yaml
fault_id: 19
fault_name: "Gear Shaft Bend"
min_tier: 4
conditions:
  - feature: "1X_and_2X_elevated"
    operator: "=="
    threshold: true
    description: "Both 1X and 2X of gear shaft are elevated"
  - feature: "GMF_1X_sidebands"
    operator: "=="
    threshold: true
    description: "1X sidebands around GMF"
confidence_base: 0.70
```

**Fault #20: Gear Wear 齒輪磨損**
```yaml
fault_id: 20
fault_name: "Gear Wear"
min_tier: 4
conditions:
  - feature: "GMF_harmonic_energy_trend"
    operator: "increasing"
    threshold: null
    description: "Multiple GMF harmonics gradually increasing over time"
  - feature: "broadband_around_GMF"
    operator: "=="
    threshold: true
    description: "Broadband energy increase around GMF region"
confidence_base: 0.65  # Hard to diagnose definitively
modifiers:
  trend_data_available: 1.3  # Historical comparison greatly helps
```

---

## 6. Phase 1 Scope（Tier 0-2, 10 Fault Coverage）

### 6.1 Phase 1 目標

| Item | Scope |
|------|-------|
| Tiers | 0, 1, 2 |
| Faults covered | 10 (8 specific + 1 merged group of 2) |
| Signal type | Single-axis or tri-axial acceleration |
| RPM input | Manual + auto-estimation fallback |
| Bearing input | Manual geometry or model lookup (SKF/FAG/NSK database) |

### 6.2 Phase 1 故障清單

| # | Fault | Tier | Type | Detection Method |
|---|-------|------|------|-----------------|
| 1 | Unbalance | T1 | S | 1X dominance + radial dominant |
| 2 | Bent Shaft | T1 | S | 1X+2X + axial elevated |
| 3 | Parallel Misalignment | T1 | S | 2X dominant + radial |
| 9 | Angular Misalignment | T1 | S | Axial 1X dominant |
| 6 | Looseness | T1 | S | Multiple harmonics + sub-harmonics |
| 11/12 | Oil Whirl/Whip | T1 | M | Sub-synchronous 0.4X-0.48X |
| 4 | Inner Race | T2 | S | BPFI + 1X sidebands in envelope |
| 5 | Outer Race | T2 | S | BPFO in envelope, no sidebands |
| 7 | Ball Defect | T2 | S | BSF + FTF sidebands in envelope |

### 6.3 Phase 1 不包含（YAGNI）

- Electrical fault analysis（Tier 3）— 需要極數和電源頻率
- Gear fault analysis（Tier 4）— 需要齒數
- MCSA current analysis（Tier 5）— 需要電流訊號
- Waterfall plot for whirl/whip separation（Tier 5）— 需要臨界轉速
- Multi-channel phase analysis — 超出 Phase 1 範圍
- Order tracking for variable speed — 超出 Phase 1 範圍

### 6.4 Phase 1 Deliverables

1. `MachineParameters` dataclass with Tier 0-2 fields
2. `DiagnosisResult` dataclass (full structure, but only T0-T2 populated)
3. Preprocessing pipeline (detrend, window, anti-alias)
4. FFT analyzer with order mapping
5. Envelope spectrum analyzer
6. Kurtogram for optimal filter band selection
7. Rule engine with 10-fault decision table
8. Conflict resolver for mutually exclusive faults
9. ISO 10816 severity classifier
10. Result formatter with suggested parameters for next tier

---

## 7. 特徵頻率公式（Characteristic Frequency Formulas）

### 7.1 Bearing Characteristic Frequencies

All formulas assume shaft speed `f_r` in Hz (RPM / 60).

**BPFO — Ball Pass Frequency, Outer Race（外環通過頻率）**
```
BPFO = (n / 2) × f_r × (1 - (d / D) × cos(α))

Where:
  n = number of rolling elements (balls/rollers)
  d = ball/roller diameter (mm)
  D = pitch circle diameter (mm)
  α = contact angle (degrees → radians for cos)
  f_r = shaft rotational frequency (Hz) = RPM / 60
```

**BPFI — Ball Pass Frequency, Inner Race（內環通過頻率）**
```
BPFI = (n / 2) × f_r × (1 + (d / D) × cos(α))
```

**BSF — Ball Spin Frequency（滾珠自旋頻率）**
```
BSF = (D / (2 × d)) × f_r × (1 - ((d / D) × cos(α))²)
```

**FTF — Fundamental Train Frequency / Cage Frequency（保持架頻率）**
```
FTF = (f_r / 2) × (1 - (d / D) × cos(α))
```

### 7.2 Electrical Characteristic Frequencies

**Line Frequency（電源頻率）**
```
FL = line_frequency  (50 Hz or 60 Hz)
2FL = 2 × FL         (100 Hz or 120 Hz)
```

**Slip Frequency（滑差頻率）**
```
f_slip = f_synchronous - f_r

Where:
  f_synchronous = FL / pole_pairs  (synchronous speed in Hz)
  f_r = actual shaft speed (Hz)
```

**Pole Pass Frequency（極通頻率）**
```
Fp = pole_pairs × f_slip = pole_pairs × (f_synchronous - f_r)

Alternatively:
Fp = s × FL

Where: s = slip ratio = (f_synchronous - f_r) / f_synchronous
```

**Rotor Bar Pass Frequency（轉子條通過頻率）**
```
RBPF = n_bars × f_r

Where: n_bars = number of rotor bars (often unknown; can estimate from spectrum)
```

### 7.3 Gear Characteristic Frequencies

**GMF — Gear Mesh Frequency（齒輪嚙合頻率）**
```
GMF = Z × f_r

Where:
  Z = number of teeth on the gear
  f_r = shaft rotational frequency of that gear (Hz)

For a gear pair:
  GMF = Z_drive × f_drive = Z_driven × f_driven
  Gear ratio: f_driven / f_drive = Z_drive / Z_driven
```

**Hunting Tooth Frequency（獵齒頻率）**
```
HTF = GMF / LCM(Z_drive, Z_driven)

Where: LCM = Least Common Multiple
```

### 7.4 容差說明（Tolerance: ±3%）

**Why ±3%?**

1. **Slip variation**: Motor slip varies with load (typically 1-5%), causing actual RPM to differ from nominal
2. **Speed fluctuation**: Real machines don't run at perfectly constant speed
3. **Frequency resolution**: FFT frequency bin width = f_s / N; with typical settings (f_s=10kHz, N=8192), resolution ≈ 1.22 Hz
4. **Manufacturing tolerance**: Bearing geometry has manufacturing tolerances (typically ±1-2%)
5. **Contact angle variation**: Actual contact angle changes with load

**Implementation:**

```python
def frequency_match(observed_freq: float, expected_freq: float, tolerance: float = 0.03) -> bool:
    """Check if observed frequency matches expected within tolerance.
    Knuth: mathematical precision with engineering pragmatism."""
    lower = expected_freq * (1 - tolerance)
    upper = expected_freq * (1 + tolerance)
    return lower <= observed_freq <= upper

def find_harmonic_peaks(spectrum_freqs, spectrum_amps, fundamental: float,
                        max_harmonics: int = 5, tolerance: float = 0.03,
                        min_prominence: float = 3.0) -> List[HarmonicPeak]:
    """Find harmonics of a fundamental frequency in spectrum.
    Returns list of detected harmonic peaks with their amplitudes."""
    peaks = []
    for n in range(1, max_harmonics + 1):
        expected = n * fundamental
        # Search within tolerance band
        mask = (spectrum_freqs >= expected * (1 - tolerance)) & \
               (spectrum_freqs <= expected * (1 + tolerance))
        if mask.any():
            idx = spectrum_amps[mask].argmax()
            amp = spectrum_amps[mask][idx]
            freq = spectrum_freqs[mask][idx]
            # Check prominence above local noise floor
            if amp / local_noise_floor(spectrum_amps, freq) > min_prominence:
                peaks.append(HarmonicPeak(harmonic=n, frequency=freq, amplitude=amp))
    return peaks
```

**Tolerance tiers for different sources:**

| Source | Tolerance | Rationale |
|--------|-----------|-----------|
| Manual RPM + precise bearing geometry | ±2% | High confidence in expected frequencies |
| Manual RPM + bearing model lookup | ±3% | Standard tolerance (default) |
| Auto-estimated RPM + bearing geometry | ±5% | RPM uncertainty compounds |
| Auto-estimated RPM + bearing model | ±6% | Maximum uncertainty |

---

## 8. 閾值策略（Threshold Strategy based on ISO 10816）

### 8.1 ISO 10816 Machine Classification

| Class | Description 說明 | Examples |
|-------|-----------------|----------|
| **I** | Small machines | Motors up to 15 kW |
| **II** | Medium machines, no special foundation | Motors 15-75 kW on standard foundation |
| **III** | Large machines on rigid foundation | Motors >75 kW, turbines, generators on concrete |
| **IV** | Large machines on flexible foundation | Same as III but on steel or flexible mounts |

### 8.2 Velocity RMS Severity Thresholds (mm/s)

| Zone | Class I | Class II | Class III | Class IV | Meaning |
|------|---------|----------|-----------|----------|---------|
| **A** (Good) | 0 - 0.71 | 0 - 1.12 | 0 - 1.12 | 0 - 1.12 | Newly commissioned |
| **B** (Acceptable) | 0.71 - 1.8 | 1.12 - 2.8 | 1.12 - 2.8 | 1.12 - 2.8 | Unrestricted long-term operation |
| **C** (Alert) | 1.8 - 4.5 | 2.8 - 7.1 | 2.8 - 7.1 | 2.8 - 7.1 | Limited acceptable operation |
| **D** (Danger) | > 4.5 | > 7.1 | > 7.1 | > 7.1 | Damage may occur |

### 8.3 Feature-Level Thresholds

Feature-level thresholds 不使用固定絕對值，而是基於相對比較：

**Approach: Relative thresholds（相對閾值法）**

```python
# Knuth: precise definitions, not magic numbers

class ThresholdStrategy:
    """Thresholds are relative, not absolute.
    This makes the system robust across different machine sizes."""

    # --- Harmonic amplitude ratios ---
    UNBALANCE_1X_DOMINANCE = 0.6        # 1X must be >60% of 0-5X energy
    BENT_SHAFT_2X_TO_1X = 0.5           # 2X/1X ratio > 50%
    MISALIGNMENT_AXIAL_RADIAL = 0.7     # Axial/Radial > 70% → angular
    LOOSENESS_MIN_HARMONICS = 5          # At least 5 visible harmonics

    # --- Envelope spectrum ---
    BEARING_PEAK_PROMINENCE_DB = 10     # Peak must be 10 dB above noise floor
    BEARING_MIN_HARMONICS = 2           # At least 2 harmonics of fault freq

    # --- Sub-synchronous ---
    OIL_WHIRL_RANGE = (0.35, 0.50)      # Sub-sync peak location as order ratio

    # --- Electrical ---
    ELECTRICAL_2FL_PROMINENCE_DB = 6    # 2FL peak prominence

    # --- Gear ---
    GMF_SIDEBAND_ASYMMETRY = 0.3        # >30% difference = asymmetric

    # --- General ---
    MIN_CONFIDENCE_TO_REPORT = 0.3      # Below this, don't report
    KURTOSIS_BEARING_THRESHOLD = 4.0    # Kurtosis > 4 suggests bearing impact
    CREST_FACTOR_THRESHOLD = 6.0        # Crest factor > 6 suggests impulsive
```

### 8.4 Confidence Scoring Formula

```python
def compute_confidence(rule: DiagnosticRule,
                       condition_results: List[bool],
                       params: MachineParameters) -> float:
    """
    Final confidence = base × condition_ratio × modifier_product

    Knuth: explicit formula, no hidden adjustments.
    """
    # How many conditions passed?
    passed = sum(condition_results)
    total = len(condition_results)
    condition_ratio = passed / total

    # Must pass at least N-1 conditions (allow 1 miss)
    if passed < total - 1:
        return 0.0

    # Apply modifiers
    modifier = 1.0
    if params.rpm_source == "auto_estimated":
        modifier *= 0.7
    if single_axis_measurement:
        modifier *= 0.8

    # Rule-specific modifiers
    for mod_name, mod_value in rule.confidence_modifiers.items():
        if mod_name applies:
            modifier *= mod_value

    confidence = rule.confidence_base * condition_ratio * modifier
    return min(confidence, 1.0)  # Cap at 1.0
```

### 8.5 Default Machine Class Strategy

When `machine_class` is not provided:
1. Default to Class II（中型機器）— 最常見的工業場景
2. 在 `warnings` 中標記：`"Machine class assumed as II. Provide machine_class for accurate ISO 10816 assessment."`
3. 建議使用者提供功率或機型以自動分類

---

## Appendix A: Verification Checklist

### A.1 Fault Coverage Verification（20/20 故障覆蓋確認）

| # | Fault | In Matrix? | Has Rules? | Min Tier | Phase 1? |
|---|-------|-----------|-----------|----------|----------|
| 1 | Unbalance | Yes | Yes | T1 | Yes |
| 2 | Bent Shaft | Yes | Yes | T1 | Yes |
| 3 | Parallel Misalignment | Yes | Yes | T1 | Yes |
| 4 | Inner Race Defect | Yes | Yes | T2 | Yes |
| 5 | Outer Race Defect | Yes | Yes | T2 | Yes |
| 6 | Looseness | Yes | Yes | T1 | Yes |
| 7 | Ball Defect | Yes | Yes | T2 | Yes |
| 8 | Air Gap Eccentricity | Yes | Yes | T3 | No |
| 9 | Angular Misalignment | Yes | Yes | T1 | Yes |
| 10 | Phase Problem | Yes | Yes (merged) | T3 | No |
| 11 | Oil Whirl | Yes | Yes (merged) | T1 | Yes (merged) |
| 12 | Oil Whip | Yes | Yes (merged) | T1 | Yes (merged) |
| 13 | Winding Short | Yes | Yes (merged) | T3 | No |
| 14 | Broken Rotor Bar | Yes | Yes | T3 | No |
| 15 | End Ring Short | Yes | Yes (merged) | T3 | No |
| 16 | Gear Misalignment | Yes | Yes | T4 | No |
| 17 | Broken Tooth | Yes | Yes | T4 | No |
| 18 | Gear Eccentricity | Yes | Yes | T4 | No |
| 19 | Gear Shaft Bend | Yes | Yes | T4 | No |
| 20 | Gear Wear | Yes | Yes | T4 | No |

**Result: 20/20 faults covered in matrix, 20/20 have rules defined.**

### A.2 Philosophy Compliance Verification

| Principle | Check | Status |
|-----------|-------|--------|
| **Thompson: Bottom-up** | System starts from Tier 0 (just acceleration) and builds up | PASS |
| **Thompson: Composable primitives** | Each analyzer is independent, implements same interface | PASS |
| **Knuth: Mathematical precision** | All formulas fully specified with units and derivation | PASS |
| **Knuth: Tolerance justified** | ±3% tolerance explained with 5 engineering reasons | PASS |
| **Torvalds: Data structures over code** | Tier derived from nullable fields, no mode flags | PASS |
| **Torvalds: No special branches** | `can_run()` pattern replaces if-tier checks | PASS |
| **Fowler: YAGNI** | Phase 1 scoped to Tier 0-2, 10 faults only | PASS |
| **Fowler: Evolutionary design** | Full structure defined but only Phase 1 implemented | PASS |

### A.3 Tier-Parameter Consistency Check

| Tier | Required Params | Unlocked Methods | Methods Need Those Params? |
|------|----------------|-----------------|---------------------------|
| T0 | accel + fs | Time stats, raw FFT, ISO 10816 | Yes: FFT needs fs; ISO needs RMS velocity | PASS |
| T1 | + rpm | Order map, harmonic counting, sub-sync | Yes: orders need rpm to convert Hz→X | PASS |
| T2 | + bearing | Envelope, kurtogram, BPFI/BPFO/BSF | Yes: characteristic freqs need geometry | PASS |
| T3 | + electrical | 2FL, pole-pass, RBPF | Yes: Fp needs pole_pairs + slip | PASS |
| T4 | + gear teeth | GMF, cepstrum, sideband analysis | Yes: GMF = teeth × shaft_freq | PASS |
| T5 | + current + critical | MCSA, waterfall, whirl/whip split | Yes: MCSA needs current; split needs critical | PASS |
