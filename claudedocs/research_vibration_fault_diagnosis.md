# 振動故障診斷研究報告：傳統方法與機器學習方法

> 研究日期：2026-03-09
> 深度：Deep
> 信心度：高

---

## 執行摘要

本報告針對 20 種機械故障模式，研究兩階段實作路徑：
1. **第一階段**：使用傳統訊號處理與規則引擎進行故障診斷（無需 ML）
2. **第二階段**：導入機器學習模型，逐步替代或增強傳統方法

---

## 一、20 種故障模式分類

| # | 故障名稱 | 類別 | 傳統診斷難度 |
|---|---------|------|-------------|
| 1 | 不平衡 | 轉子 | ★☆☆ 低 |
| 2 | 軸彎曲 | 轉子 | ★☆☆ 低 |
| 3 | 平行不對中 | 對中 | ★☆☆ 低 |
| 4 | 內環損傷 | 軸承 | ★★☆ 中 |
| 5 | 外環損傷 | 軸承 | ★★☆ 中 |
| 6 | 軸承座鬆動 | 結構 | ★☆☆ 低 |
| 7 | 滾珠損傷 | 軸承 | ★★★ 高 |
| 8 | 氣隙不均 | 電氣 | ★★☆ 中 |
| 9 | 角度不對中 | 對中 | ★☆☆ 低 |
| 10 | 相位問題 | 電氣 | ★★☆ 中 |
| 11 | 油膜旋振 | 流體 | ★★☆ 中 |
| 12 | 油膜晃盪 | 流體 | ★★☆ 中 |
| 13 | 繞組短路 | 電氣 | ★★★ 高 |
| 14 | 轉子斷條 | 電氣 | ★★☆ 中 |
| 15 | 端環短路 | 電氣 | ★★★ 高 |
| 16 | 齒輪不對中 | 齒輪 | ★★☆ 中 |
| 17 | 齒輪斷齒 | 齒輪 | ★★☆ 中 |
| 18 | 齒輪偏心 | 齒輪 | ★★☆ 中 |
| 19 | 齒輪軸彎曲 | 齒輪 | ★★☆ 中 |
| 20 | 齒輪磨損 | 齒輪 | ★★★ 高 |

---

## 二、第一階段：傳統（非 ML）診斷方法

### 2.1 核心訊號處理技術

#### A. FFT 頻譜分析（所有故障的基礎）
- **用途**：將時域振動訊號轉換為頻域，識別特徵頻率
- **標準**：ISO 10816 系列定義振動嚴重度等級
- **工具**：NumPy/SciPy 的 `fft` 模組即可實作
- **資源**：
  - [ISO 10816-1 頻譜診斷指南](https://industrialmonitordirect.com/blogs/knowledgebase/industrial-motor-vibration-analysis-iso10816-1-interpretation-and-spectrum-diagnostics)
  - [SPM Instrument 振動量測與分析](https://www.spminstrument.com/measuring-techniques/vibration-monitoring/vibration-measurement-and-analysis/)

#### B. 包絡線分析（Envelope Analysis）
- **主要用途**：軸承故障（內環、外環、滾珠損傷）
- **原理**：對高頻共振帶進行帶通濾波 → 希爾伯特轉換取包絡 → FFT 分析包絡頻譜
- **特徵頻率**：BPFI（內環）、BPFO（外環）、BSF（滾珠）、FTF（保持架）
- **資源**：
  - [包絡頻譜故障特徵頻帶識別](https://www.mdpi.com/1424-8220/23/9/4338)
  - [軸承故障早期診斷比較分析](https://link.springer.com/article/10.1007/s10845-023-02151-y)

#### C. 倒頻譜分析（Cepstrum Analysis）
- **主要用途**：齒輪故障（不對中、斷齒、偏心、磨損）
- **原理**：偵測頻譜中的週期性結構（諧波族、邊帶）
- **優勢**：對傳輸路徑效應不敏感，可分離源與路徑
- **資源**：
  - [B&K 倒頻譜分析與齒輪箱故障診斷](https://www.bksv.com/media/doc/13-150.pdf)
  - [齒輪故障頻譜與倒頻譜分析](https://www.researchgate.net/publication/283178935_Fault_Detection_of_Gear_Using_Spectrum_and_Cepstrum_Analysis)

#### D. 階次追蹤（Order Tracking）
- **用途**：變速工況下的故障診斷
- **原理**：將時域訊號重新取樣至角度域，消除轉速變化影響

#### E. 時頻分析
- **方法**：短時傅立葉轉換（STFT）、連續小波轉換（CWT）、Wigner-Ville 分佈
- **用途**：暫態訊號分析、啟停機過程診斷

#### F. 經驗模態分解（EMD）
- **原理**：自適應分解訊號為本質模態函數（IMF）
- **用途**：結合包絡線分析用於軸承早期故障診斷

### 2.2 各故障類別的傳統診斷規則

#### 轉子類故障（#1 不平衡、#2 軸彎曲）

| 故障 | 特徵頻率 | 診斷規則 |
|------|---------|---------|
| 不平衡 | 1X（一倍轉頻）為主 | 徑向振動大，1X 幅值高，相位穩定，軸向小 |
| 軸彎曲 | 1X + 2X | 軸向 1X 幅值高，1X 與 2X 同時偏高 |

#### 對中類故障（#3 平行不對中、#9 角度不對中）

| 故障 | 特徵頻率 | 診斷規則 |
|------|---------|---------|
| 平行不對中 | 2X 為主 | 徑向 2X 幅值高，軸向相對低 |
| 角度不對中 | 1X 軸向為主 | 軸向 1X 振動顯著，可能伴隨 2X |

#### 軸承類故障（#4 內環、#5 外環、#6 鬆動、#7 滾珠）

| 故障 | 特徵頻率 | 診斷規則 |
|------|---------|---------|
| 內環損傷 | BPFI 及其諧波 | 包絡頻譜出現 BPFI，伴隨轉頻邊帶 |
| 外環損傷 | BPFO 及其諧波 | 包絡頻譜出現 BPFO，通常無明顯邊帶 |
| 滾珠損傷 | BSF 及其諧波 | 包絡頻譜出現 BSF，較難偵測 |
| 軸承座鬆動 | 0.5X 次諧波 + 多階諧波 | 頻譜出現大量轉頻諧波（2X~10X+），可能有 0.5X |

- **資源**：[軸承故障訊號偵測方法綜述](https://pmc.ncbi.nlm.nih.gov/articles/PMC9654419/)

#### 電氣類故障（#8 氣隙不均、#10 相位、#13 繞組短路、#14 轉子斷條、#15 端環短路）

| 故障 | 特徵頻率 | 診斷規則 |
|------|---------|---------|
| 氣隙不均 | 2×電源頻率(2FL) ± 極通頻率(Fp) 邊帶 | 2FL 處出現脈動振動 |
| 繞組短路 | 2FL | 局部過熱導致定子變形，產生熱致振動 |
| 轉子斷條 | 1X ± Fp 邊帶、RBPF 邊帶 | 電源頻率附近出現極通頻率邊帶 |
| 端環短路 | 類似轉子斷條 | 需結合電流訊號分析（MCSA） |
| 相位問題 | 2FL | 線電壓不平衡引起的振動 |

- **補充方法**：馬達電流特徵分析（MCSA）對電氣故障更敏感
- **資源**：
  - [電動馬達故障振動分析](https://adash.com/articles/electric-motor-faults-analysis/)
  - [電動馬達故障頻譜分析](https://vibromera.eu/uncategorized/electric-motor-defects-comprehensive-spectral-analysis/)
  - [感應馬達振動 - 電氣問題](https://irispower.com/wp-content/uploads/2023/07/Induction-Motor-Vibration-Electrical-Problems-Doyle-IRMC-2023.pdf)

#### 流體類故障（#11 油膜旋振、#12 油膜晃盪）

| 故障 | 特徵頻率 | 診斷規則 |
|------|---------|---------|
| 油膜旋振(Oil Whirl) | 0.4X ~ 0.48X（次同步） | 次同步峰值頻率隨轉速線性增加 |
| 油膜晃盪(Oil Whip) | 鎖定在一階臨界轉速 | 次同步頻率固定不再隨轉速增加 |

- **診斷關鍵**：瀑布圖（Waterfall Plot）觀察啟機過程
- **資源**：
  - [油膜旋振與晃盪識別](https://www.ctconline.com/media/vyxjkhgk/mdi-tech-tip-oil-whirl.pdf)
  - [流體不穩定與摩擦的區分](https://www.turbomachinerymag.com/view/differentiating-between-fluid-induced-instability-oil-whirl-and-oil-whip-and-a-rub)

#### 齒輪類故障（#16~#20）

| 故障 | 特徵頻率 | 診斷規則 |
|------|---------|---------|
| 齒輪不對中 | GMF 邊帶異常 | 齒輪嚙合頻率邊帶不對稱 |
| 齒輪斷齒 | GMF 諧波 + 時域衝擊 | 時域出現週期性衝擊，頻譜 GMF 諧波增加 |
| 齒輪偏心 | GMF ± 1X 邊帶 | GMF 周圍出現 1X 調變邊帶 |
| 齒輪軸彎曲 | 1X + GMF 邊帶 | 結合轉子彎曲與齒輪邊帶特徵 |
| 齒輪磨損 | GMF 諧波能量增加 | 多階 GMF 諧波幅值逐漸升高 |

- GMF = 齒輪嚙合頻率 = 齒數 × 轉頻

### 2.3 規則引擎架構（實作建議）

```
振動訊號 → 前處理（去趨勢、濾波）
         → 多路分析：
           ├─ FFT 頻譜分析 → 特徵頻率提取
           ├─ 包絡線分析 → 軸承特徵頻率
           ├─ 倒頻譜分析 → 齒輪特徵
           └─ 時域統計量 → RMS、峰值、峭度
         → 特徵比對（規則引擎 / 決策表）
         → 故障分類 + 信心度
```

**參考系統**：
- [VIBEX 專家系統 - 使用決策樹與決策表](https://www.sciencedirect.com/science/article/abs/pii/S0957417404001770)
- [旋轉機械故障偵測專家系統](https://pmc.ncbi.nlm.nih.gov/articles/PMC8617882/)

### 2.4 實作所需的 Python 工具

| 功能 | 套件 |
|------|------|
| FFT / 頻譜分析 | `numpy.fft`, `scipy.signal` |
| 包絡線分析 | `scipy.signal.hilbert` |
| 小波轉換 | `pywt` (PyWavelets) |
| EMD | `PyEMD` |
| 視覺化 | `matplotlib`, `plotly` |
| 訊號處理 | `scipy.signal` (濾波器設計、重取樣) |

---

## 三、第二階段：機器學習替代方案

### 3.1 推薦的 ML 方法（由簡到複雜）

#### 層級 1：傳統 ML（入門）
| 方法 | 適用場景 | 優勢 |
|------|---------|------|
| **SVM（支持向量機）** | 多類別故障分類 | 小樣本效果好，可解釋性佳 |
| **Random Forest** | 多類別分類 | 特徵重要性分析，抗過擬合 |
| **XGBoost / LightGBM** | 多類別分類 | 效能高，處理不平衡資料 |

- **特徵工程**：時域（RMS、峰值、峭度、偏度）+ 頻域（均方根頻率、重心頻率）+ 時頻域
- **工具**：`scikit-learn`, `xgboost`, `lightgbm`

#### 層級 2：1D-CNN（推薦首選深度學習）
- **輸入**：原始振動時序訊號或頻譜
- **架構**：多層 1D 卷積 → BatchNorm → ReLU → MaxPool → 全連接 → Softmax(20 類)
- **優勢**：自動特徵提取，無需手動特徵工程，已在多項研究中證實效能優異
- **精確度**：軸承故障可達 99%+
- **工具**：`PyTorch` 或 `TensorFlow/Keras`

#### 層級 3：CNN-LSTM 混合模型
- **原理**：CNN 提取空間/頻域特徵 + LSTM 捕捉時序相依性
- **適用**：需要考慮時序變化的場景
- **資源**：[CNN-LSTM 結合 FFT 和 CWT 的故障診斷](https://www.sciencedirect.com/science/article/abs/pii/S0166361520306126)

#### 層級 4：Transformer 模型（前沿）
- **MCSAT**：多尺度卷積稀疏注意力 Transformer，輕量高效
- **適用**：大量資料、多工況條件
- **資源**：[多尺度卷積稀疏注意力 Transformer](https://www.sciencedirect.com/science/article/abs/pii/S0925231225016066)

#### 層級 5：遷移學習（進階）
- **用途**：當目標設備標籤資料不足時，從源域遷移知識
- **方法**：預訓練模型 + 微調、Domain Adaptation
- **資源**：[旋轉機械深度遷移學習綜述 (2025)](https://onlinelibrary.wiley.com/doi/10.1002/eng2.70494)

### 3.2 公開資料集（訓練與驗證）

| 資料集 | 故障類型 | 取樣率 | 來源 |
|--------|---------|--------|------|
| **CWRU** (Case Western Reserve) | 軸承（內環/外環/滾珠） | 12kHz / 48kHz | [官網](https://engineering.case.edu/bearingdatacenter) |
| **Paderborn University** | 軸承 | 64kHz | 開源 |
| **MFPT** | 軸承 | 多種 | 機械故障預防技術學會 |
| **PHM2009** | 齒輪箱 | - | PHM Society |

- **CWRU NumPy 格式**：[GitHub - srigas/CWRU_Bearing_NumPy](https://github.com/srigas/CWRU_Bearing_NumPy)
- **軸承資料集彙整**：[awesome-bearing-dataset](https://github.com/VictorBauler/awesome-bearing-dataset)

### 3.3 從第一階段到第二階段的遷移路徑

```
第一階段（規則引擎）          第二階段（ML 增強）
─────────────────          ─────────────────
訊號前處理        ────→     共用（保留）
FFT/包絡/倒頻譜   ────→     作為 ML 輸入特徵
規則引擎判斷      ────→     ML 分類器替代
                           ↑ 規則引擎結果作為
                           │ ML 的對照基準
信心度輸出        ────→     ML 機率輸出
```

**建議遷移策略**：
1. 第一階段的訊號處理模組全部保留
2. 將傳統特徵（頻譜峰值、RMS 等）作為 ML 模型的輸入特徵
3. 先用 SVM/XGBoost 驗證 ML 是否優於規則引擎
4. 再導入 1D-CNN 直接處理原始訊號
5. 雙軌並行：規則引擎 + ML 模型同時運行，比對結果

---

## 四、實作路線圖

### 第一階段：傳統方法（建議 4-6 週）

```
Week 1-2: 訊號處理核心模組
  - FFT 頻譜分析引擎
  - 包絡線分析模組
  - 倒頻譜分析模組
  - 特徵頻率計算器（需要軸承/齒輪參數輸入）

Week 3-4: 規則引擎
  - 故障特徵頻率資料庫
  - 診斷規則表（20 種故障 × 頻率特徵 × 閾值）
  - 決策樹/決策表實作
  - 信心度評分機制

Week 5-6: 整合與驗證
  - 使用公開資料集驗證
  - 調整閾值與規則
  - 報表/視覺化輸出
```

### 第二階段：ML 增強（建議 4-8 週）

```
Week 1-2: 資料準備與傳統 ML
  - 特徵工程管線
  - SVM / XGBoost 基準模型
  - 與規則引擎結果對比

Week 3-5: 深度學習
  - 1D-CNN 模型訓練
  - 超參數調整
  - 多工況泛化測試

Week 6-8: 部署與整合
  - 模型推論引擎
  - 雙軌並行機制
  - 效能監控
```

---

## 五、關鍵參考資源

### 標準與指南
- [ISO 10816 振動嚴重度](https://acoem.us/blog/other-topics/understanding-the-iso-10816-3-vibration-severity-chart/)
- [固德科技 - 5分鐘搞懂振動監測](https://www.goodtechnology.com.tw/blog/25002.html)

### 傳統方法
- [VIBEX 專家系統](https://www.sciencedirect.com/science/article/abs/pii/S0957417404001770)
- [旋轉機械故障偵測專家系統](https://pmc.ncbi.nlm.nih.gov/articles/PMC8617882/)
- [電動馬達故障分析](https://adash.com/articles/electric-motor-faults-analysis/)
- [B&K 倒頻譜分析](https://www.bksv.com/media/doc/13-150.pdf)

### 機器學習方法
- [深度學習旋轉機械故障診斷綜述](https://link.springer.com/article/10.1007/s10462-022-10293-3)
- [CNN vs MLP vs RNN vs LSTM 比較分析](https://www.internationaljournalssrg.org/IJEEE/paper-details?Id=856)
- [CNN-LSTM 注意力機制故障偵測](https://pmc.ncbi.nlm.nih.gov/articles/PMC10181692/)
- [深度遷移學習綜述 (2025)](https://onlinelibrary.wiley.com/doi/10.1002/eng2.70494)

### 資料集
- [CWRU Bearing Data Center](https://engineering.case.edu/bearingdatacenter)
- [CWRU NumPy 版本](https://github.com/srigas/CWRU_Bearing_NumPy)
- [軸承資料集彙整](https://github.com/VictorBauler/awesome-bearing-dataset)
- [Kaggle CWRU 資料集](https://www.kaggle.com/datasets/brjapon/cwru-bearing-datasets)

### 實作教學
- [工業馬達故障分類 - Towards Data Science](https://towardsdatascience.com/industrial-motor-fault-classification-using-deep-learning-with-iot-implications-fd36ddc8ad5b/)
- [CWRU 資料集完整指南](https://medium.com/@NameerAkhter/all-you-need-to-know-about-cwru-dataset-8d391577d8f2)

---

## 六、MATLAB 驗證資源（用於功能對照與結果驗證）

> 以下 MATLAB 資源可作為 Python 實作的驗證基準，確保各訊號處理模組輸出結果一致。

### 6.1 所需 MATLAB Toolbox 清單

| Toolbox | 用途 | 必要性 |
|---------|------|--------|
| **Signal Processing Toolbox** | FFT、濾波器、包絡線、倒頻譜、階次追蹤、峭度圖 | 必要 |
| **Wavelet Toolbox** | CWT、STFT、EMD | 必要 |
| **Predictive Maintenance Toolbox** | 故障診斷範例、狀態指標、RUL 估算 | 強烈建議 |
| **Deep Learning Toolbox** | 1D-CNN、遷移學習故障分類 | 第二階段需要 |
| **Statistics and Machine Learning Toolbox** | SVM、分類器、Classification Learner | 第二階段需要 |

### 6.2 FFT 頻譜分析（對應 2.1-A）

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| Vibration Analysis 總覽 | Signal Processing Toolbox 振動分析功能彙整 | [MathWorks](https://www.mathworks.com/help/signal/vibration-analysis.html) |
| 旋轉機械振動分析範例 | 齒輪箱 FFT 分析、時間同步平均 | [MathWorks](https://www.mathworks.com/help/signal/ug/vibration-analysis-of-rotating-machinery.html) |
| MATLAB 振動訊號處理論文 | 完整的 MATLAB 振動故障診斷流程 | [ResearchGate](https://www.researchgate.net/publication/376809023_MATLAB-Based_Vibration_Signal_Processing_for_Fault_Diagnosis) |

### 6.3 包絡線分析（對應 2.1-B）

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| `envspectrum()` 函數 | 內建包絡頻譜函數，30 階帶通濾波 + Hilbert 方法 | [MathWorks](https://www.mathworks.com/help/signal/ref/envspectrum.html) |
| `envelope()` 函數 | 取包絡上下界，基於解析訊號 | [MathWorks](https://www.mathworks.com/help/signal/ref/envelope.html) |
| 包絡頻譜計算範例 | 計算振動訊號的包絡頻譜 | [MathWorks](https://www.mathworks.com/help/signal/ug/compute-envelope-spectrum.html) |
| 解析訊號包絡提取 | 使用 Hilbert 轉換提取包絡的完整教學 | [MathWorks](https://www.mathworks.com/help/signal/ug/envelope-extraction-using-the-analytic-signal.html) |
| 軸承包絡分析教學論文 | 63 行 MATLAB 程式碼的完整包絡分析教學 | [MDPI](https://www.mdpi.com/2076-3417/10/20/7302) |
| 軸承早期故障偵測案例 | MATLAB 案例研究，含完整程式碼 | [Medium](https://medium.com/@RashmiW/vibration-analysis-of-bearings-for-early-fault-detection-a-matlab-case-study-1e2ff244c78e) |

### 6.4 倒頻譜分析（對應 2.1-C）

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| Cepstrum Analysis 教學 | Signal Processing Toolbox 倒頻譜分析完整說明 | [MathWorks](https://www.mathworks.com/help/signal/ug/cepstrum-analysis.html) |
| `cceps()` 複倒頻譜 | 複倒頻譜函數文件 | [MathWorks](https://www.mathworks.com/help/signal/ref/cceps.html) |
| `rceps()` 實倒頻譜 | 實倒頻譜與最小相位重建 | [MathWorks](https://www.mathworks.com/help/signal/ref/rceps.html) |

### 6.5 階次追蹤（對應 2.1-D）

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| Order Analysis 範例 | 完整的振動訊號階次分析範例 | [MathWorks](https://www.mathworks.com/help/signal/ug/order-analysis-of-a-vibration-signal.html) |
| `ordertrack()` | 追蹤與提取振動訊號的階次幅值 | [MathWorks](https://www.mathworks.com/help/signal/ref/ordertrack.html) |
| `rpmordermap()` | 階次-RPM 圖，含重取樣消除拖尾 | [MathWorks](https://www.mathworks.com/help/signal/ref/rpmordermap.html) |
| `orderspectrum()` | 平均頻譜 vs 階次 | [MathWorks](https://www.mathworks.com/help/signal/ref/orderspectrum.html) |
| `orderwaveform()` | 提取時域階次波形 | [MathWorks](https://www.mathworks.com/help/signal/ref/orderwaveform.html) |
| `tachorpm()` | 從轉速計脈衝提取 RPM | [MathWorks](https://www.mathworks.com/help/signal/ref/tachorpm.html) |
| `rpmtrack()` | 從振動訊號提取 RPM 曲線 | [MathWorks](https://www.mathworks.com/help/signal/ref/rpmtrack.html) |

### 6.6 時頻分析：CWT / STFT（對應 2.1-E）

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| Wavelet Transforms 總覽 | MATLAB 小波轉換完整介紹 | [MathWorks](https://www.mathworks.com/discovery/wavelet-transforms.html) |
| `cwt()` 連續小波轉換 | 1D CWT 函數，預設 Morse 小波 | [MathWorks](https://www.mathworks.com/help/wavelet/ref/cwt.html) |
| CWT 時頻分析教學 | 實用入門教學 | [MathWorks](https://www.mathworks.com/help/wavelet/ug/practical-introduction-to-time-frequency-analysis-using-the-continuous-wavelet-transform.html) |
| CWT vs STFT 比較 | CWT 與 STFT 的解析度差異說明 | [MathWorks](https://www.mathworks.com/help/wavelet/ug/time-frequency-analysis-and-continuous-wavelet-transform.html) |
| Time-Frequency Gallery | 各種時頻分析方法的視覺化比較 | [MathWorks](https://www.mathworks.com/help/signal/ug/time-frequency-gallery.html) |

### 6.7 經驗模態分解 EMD（對應 2.1-F）

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| `emd()` 函數 | 內建 EMD 函數，輸出 IMF 與診斷資訊 | [MathWorks](https://www.mathworks.com/help/signal/ref/emd.html) |
| EMD 總覽頁面 | EMD 原理、應用與範例 | [MathWorks](https://www.mathworks.com/discovery/empirical-mode-decomposition.html) |
| IMF for Bearing Fault Diagnosis | File Exchange：軸承故障 IMF 分析工具 | [File Exchange](https://www.mathworks.com/matlabcentral/fileexchange/37226-imf-for-bearing-fault-diagnosis) |
| Robust EMD (REMD) | File Exchange：強健型 EMD 實作 | [File Exchange](https://www.mathworks.com/matlabcentral/fileexchange/70032-robust-empirical-mode-decomposition-remd) |

### 6.8 峭度圖 / 頻譜峭度（軸承故障進階偵測）

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| `kurtogram()` | 快速峭度圖，定位最佳濾波頻帶 | [MathWorks](https://www.mathworks.com/help/signal/ref/kurtogram.html) |
| `spectralKurtosis()` | 頻譜峭度計算 | [MathWorks](https://www.mathworks.com/help/signal/ref/spectralkurtosis.html) |
| Fast Kurtogram | File Exchange：快速峭度圖實作 | [File Exchange](https://www.mathworks.com/matlabcentral/fileexchange/48912-fast-kurtogram) |

> **驗證流程**：先用 `kurtogram()` 找到最佳頻帶 → 帶通濾波 → `envspectrum()` 提取包絡頻譜 → 與 Python 實作結果對比

### 6.9 軸承故障診斷完整範例

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| Rolling Element Bearing Fault Diagnosis | Predictive Maintenance Toolbox 完整範例（傳統方法） | [MathWorks](https://www.mathworks.com/help/predmaint/ug/Rolling-Element-Bearing-Fault-Diagnosis.html) |
| Bearing Fault Diagnosis Using Deep Learning | 深度學習方法，含 scalogram + 遷移學習 | [MathWorks](https://www.mathworks.com/help/predmaint/ug/rolling-element-bearing-fault-diagnosis-using-deep-learning.html) |
| Condition Monitoring Using Vibration Signals | 振動訊號狀態監測與預測維護 | [MathWorks](https://www.mathworks.com/help/predmaint/ug/condition-monitoring-and-prognostics-using-vibration-signals.html) |
| Data Preprocessing for Predictive Maintenance | 資料前處理範例 | [MathWorks](https://www.mathworks.com/help/predmaint/ug/data-preprocessing-for-condition-monitoring-and-predictive-maintenance.html) |

### 6.10 齒輪故障診斷範例

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| Gear Condition Monitoring Indicators | `gearConditionMetrics()`：RMS、峭度、波峰因子 | [MathWorks](https://www.mathworks.com/help/predmaint/ref/gearconditionmetrics.html) |
| Condition Indicators for Gear Monitoring | 齒輪狀態指標完整教學 | [MathWorks](https://www.mathworks.com/help/predmaint/ug/condition-indicators-for-gear-condition-monitoring.html) |
| Simulink 齒輪故障模擬 | 使用 Simulink 產生齒輪故障資料 | [MathWorks](https://www.mathworks.com/help/predmaint/ug/Use-Simulink-to-Generate-Fault-Data.html) |
| Motor Current Signature - Gear Train | MCSA 偵測齒輪系統故障 | [MathWorks](https://www.mathworks.com/help/predmaint/ug/motor-current-signature-analysis-for-gear-train-fault-detection.html) |
| Shaft Fault Isolation | Diagnostic Feature Designer 軸故障隔離範例 | [MathWorks](https://www.mathworks.com/help/predmaint/ug/isolate-a-shaft-fault-using-diagnostic-feature-designer.html) |

### 6.11 電氣故障診斷（MCSA）

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| MCSA for Gear Train Fault | MATLAB 馬達電流特徵分析範例 | [MathWorks](https://www.mathworks.com/help/predmaint/ug/motor-current-signature-analysis-for-gear-train-fault-detection.html) |
| Motor Fault Identification (ML) | 使用機器學習識別馬達故障（影片教學） | [MathWorks](https://www.mathworks.com/videos/identifying-motor-faults-using-machine-learning-for-predictive-maintenance-1665008342485.html) |
| MCSA 原理論文 | 感應馬達 MCSA 故障診斷 | [IntechOpen](https://www.intechopen.com/chapters/1171032) |

### 6.12 開源 MATLAB 振動分析工具箱

| 工具箱 | 說明 | 連結 |
|--------|------|------|
| **ABRAVIBE** | 噪音與振動分析工具箱：頻譜分析、同步取樣、階次追蹤 | [File Exchange](https://www.mathworks.com/matlabcentral/fileexchange/68508-abravibe-noise-and-vibration-analysis-toolbox) |
| **Engineering Vibration Toolbox** | 35+ 教育用程式，支援 MATLAB/Octave/Python | [GitHub](https://vibrationtoolbox.github.io/) |
| **VibrationData Toolbox** | 免費訊號分析與結構動力學套件 | [enDAQ](https://endaq.com/pages/vibration-shock-analysis-software-vibrationdata-toolbox) |

### 6.13 Predictive Maintenance Toolbox 總覽

| MATLAB 資源 | 說明 | 連結 |
|-------------|------|------|
| Toolbox 首頁 | 功能總覽：狀態監測、故障診斷、RUL | [MathWorks](https://www.mathworks.com/products/predictive-maintenance.html) |
| 入門指南 | 快速上手教學 | [MathWorks](https://www.mathworks.com/help/predmaint/getting-started-with-predictive-maintenance-toolbox.html) |
| 故障偵測與診斷 | 所有故障診斷範例彙整 | [MathWorks](https://www.mathworks.com/help/predmaint/detect-and-diagnose-faults.html) |
| 旋轉機械專區 | 軸承、齒輪、馬達範例集合 | [MathWorks](https://www.mathworks.com/help/predmaint/rotating-machinery.html) |
| 演算法設計指南 | 狀態監測與預測維護演算法設計流程 | [MathWorks](https://www.mathworks.com/help/predmaint/gs/designing-algorithms-for-condition-monitoring-and-predictive-maintenance.html) |

### 6.14 Python ↔ MATLAB 驗證對照表

| 功能模組 | Python 實作 | MATLAB 驗證函數 |
|---------|------------|----------------|
| FFT 頻譜 | `numpy.fft.fft()` | `fft()` |
| 功率頻譜密度 | `scipy.signal.welch()` | `pwelch()` |
| 包絡線提取 | `scipy.signal.hilbert()` | `envelope()`, `envspectrum()` |
| 倒頻譜 | 自行實作（log + ifft） | `cceps()`, `rceps()` |
| 階次追蹤 | 自行實作（角度域重取樣） | `ordertrack()`, `rpmordermap()` |
| CWT 小波 | `pywt.cwt()` | `cwt()` |
| STFT | `scipy.signal.stft()` | `spectrogram()` |
| EMD | `PyEMD.EMD()` | `emd()` |
| 峭度圖 | 自行實作 | `kurtogram()`, `spectralKurtosis()` |
| 帶通濾波 | `scipy.signal.butter()` + `filtfilt()` | `bandpass()`, `filtfilt()` |
| 軸承特徵頻率 | 自行計算公式 | `bearingFaultBands()` |
| 齒輪狀態指標 | 自行計算 | `gearConditionMetrics()` |
| 1D-CNN 分類 | `PyTorch` / `TensorFlow` | Deep Learning Toolbox |
| SVM 分類 | `sklearn.svm.SVC()` | `fitcecoc()`, Classification Learner |
