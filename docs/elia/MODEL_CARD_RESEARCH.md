# ELIA Engine — Model Card & Research Evaluation

> **Component 4**: Eco-Spatial Landscape Intelligence (ELIA Engine)  
> **Model Name**: `elia_garden_layout_unet`  
> **Model Version**: `elia-garden-layout-v1.0`  
> **Planner Version**: `elia-hybrid-planner-v2.1`  
> **Model Artifact Checksum (SHA-256)**: `f96e15976963a06960d76f836f86aa85d4986c1634fcacbc7fb3bd849c2fe79b`  
> **Date**: 2026-10-20

---

## 1. Research Objective & System Boundaries

The research goal of the ELIA learned model is to discover valid, context-sensitive spatial distributions for vegetation (trees), outdoor living amenities (seating/dining), and pathway/boundary lighting on residential parcels, conditioned on authoritative architectural constraints (boundary shape, house footprint, road exposure, main entrance, utility restrictions, and shadow aspects).

### Explicit Division of Responsibility (Hybrid Generative Architecture)

ELIA does **not** generate the entire exterior layout end-to-end through unconstrained neural generation:
1. **Learned UNet Model**: Predicts continuous 2D spatial density distributions (heatmaps) across the parcel for:
   - Tree canopy planting locations (Channel 0)
   - Garden seating and outdoor living areas (Channel 1)
   - Garden/perimeter lighting node positions (Channel 2)
   - Circulation guidance field (Channel 3, advisory only)
2. **Deterministic Geometric Planners**: Execute all high-liability structural, circulation, and regulatory geometry:
   - Vehicular gate placement along the surveyed road-facing boundary
   - Garage positioning and vehicle access apron
   - Straight and curved (A*) driveway centerlines and 2D clearance envelopes
   - Pedestrian walkways from gate to house entrance
   - Rooftop solar photovoltaic panel arrangement (coplanar / tilted racking)
   - Elevated balcony and terrace container planting
3. **Versioned 54-Rule Evaluator**: Evaluates the coordinated candidate against explicit legal, engineering, environmental, and botanical rules. Safety is **never** delegated to neural activations alone.

---

## 2. Model Architecture & Tensor Contract

### 2.1 Architecture Specification
- **Base Architecture**: 5-Stage Convolutional UNet with symmetric skip connections.
- **Encoder**: 3 contracting blocks with $3\times3$ convolutions, Batch Normalization, ReLU activations, and $2\times2$ Max Pooling.
- **Bottleneck**: Dual $3\times3$ convolutions (filter depth = 128) capturing global parcel context.
- **Decoder**: 3 expanding blocks with $2\times2$ Bilinear Upsampling, skip connection concatenation, and $3\times3$ convolutions.
- **Final Layer**: $1\times1$ convolution with Sigmoid activation outputting per-pixel probabilities $\in [0.0, 1.0]$.
- **Parameters**: 186,436 trainable parameters; stored as 77.5 KB compressed NumPy array (`weights.npz`) for fast, secure CPU inference with zero deserialization vulnerabilities.

### 2.2 Input Tensor Specification ($9 \times 96 \times 96$, `float32`)
Spatial coordinates in meters are mapped to $[0, 96] \times [0, 96]$ preserving exact aspect ratio:
$$s = \frac{90.0}{\max(x_{\max} - x_{\min}, y_{\max} - y_{\min})}, \quad u = (x - x_{\min}) \cdot s, \quad v = (y - y_{\min}) \cdot s$$

| Channel | Identifier | Semantic Content | Representation |
|---|---|---|---|
| **0** | `land_mask` | Surveyed property boundary | Binary mask ($1.0 = \text{interior}, 0.0 = \text{exterior}$) |
| **1** | `house_mask` | Fixed residential building footprint | Binary mask ($1.0 = \text{building}, 0.0 = \text{ground}$) |
| **2** | `road_access_mask` | Road-facing property edge | 2.0 m corridor along road boundary segment |
| **3** | `entrance_mask` | Main house entrance point | 2D Gaussian density ($\sigma = 2.0\text{ m}$) |
| **4** | `utility_restriction_mask` | Water well, septic tank (50ft / 15.24m separation) | Binary buffer exclusion zone |
| **5** | `shadow_aspect_mask` | Solar azimuth & building shadow envelope | Continuous intensity $[0, 1]$ relative to north bearing |
| **6** | `preference_density_weight` | User greenery density preference | Scalar field ($0.33 = \text{low}, 0.66 = \text{medium}, 1.0 = \text{high}$) |
| **7** | `preference_style_greeny` | "Greeny" concept style selected | Binary scalar ($1.0 = \text{active}, 0.0 = \text{inactive}$) |
| **8** | `preference_style_minimal` | "Minimalistic" concept style selected | Binary scalar ($1.0 = \text{active}, 0.0 = \text{inactive}$) |

### 2.3 Output Tensor Specification ($4 \times 96 \times 96$, `float32`, values $\in [0.0, 1.0]$)

| Channel | Identifier | Output Semantic | Target Generation Method |
|---|---|---|---|
| **0** | `tree_heatmap` | Probability distribution of viable tree centers | Extracted via peak detection (NMS radius = 3 cells) |
| **1** | `seating_heatmap` | Probability distribution of outdoor living zones | Extracted via peak detection & obstacle clearance |
| **2** | `lighting_heatmap` | Probability distribution of exterior lighting nodes | Extracted along access and garden perimeters |
| **3** | `path_guidance_heatmap` | Advisory circulation guidance field | Informative only; geometric pathing remains deterministic |

---

## 3. Dataset Provenance & Methodology

### 3.1 Training Dataset Composition
- **Total Dataset Size**: 332 residential plot scenarios.
- **Split Breakdown**:
  - **Training Set**: 237 records (71.4%)
  - **Validation Set**: 46 records (13.9%)
  - **Held-Out Test Set**: 49 records (14.7%)
- **Data Provenance**:
  - **Surveyed Architectural Samples**: 42 real surveyed residential building parcels from Western, Central, and Southern Sri Lankan local authority jurisdictions.
  - **Controlled Parametric Layouts**: 290 geometrically diverse synthetic scenarios derived from residential lot typologies (standard suburban rectangular, narrow urban infill, L-shaped courtyard, corner double-frontage, and sloping terrain plots).
- **Independent Sites vs. Scenarios**:
  - The dataset comprises **48 distinct parcel geometries** expanded across varied orientation angles, building aspect ratios, entrance configurations, and density preferences.
  - **Important Methodological Note**: Synthetic training and validation performance must not be conflated with certified real-world architectural compliance. Real-world implementation is governed by the 54-rule validator.

### 3.2 Training Procedure & Checkpoint Selection
- **Loss Function**: Combined Binary Cross-Entropy with Logits (`BCEWithLogitsLoss`) and Focal Spatial Penalty targeting class imbalance (sparse object peaks against vast open space).
- **Optimizer**: AdamW (initial learning rate = $1 \times 10^{-3}$, weight decay = $1 \times 10^{-4}$) with Cosine Annealing learning rate schedule.
- **Hardware & Training Time**: Google Colab Tesla T4 GPU; trained for 17 epochs (early stopping triggered at minimum validation loss of 0.0382 at epoch 14).
- **Checkpoint Selection**: Epoch 14 model weights serialized to `weights.npz`.

---

## 4. Empirical Evaluation Results

The evaluation protocol was executed across **5 geometrically distinct held-out residential test sites** under two standardized requirement profiles (Medium Greenery and High Greenery), yielding 10 evaluation trials.

### 4.1 Latency and Computational Resource Profile (Single-Core CPU)

| Test Site Identifier | Parcel Typology | Parcel Bounds (m) | Max Tree Peak | Mean Activation | Inference Latency (ms) |
|---|---|:---:|:---:|:---:|:---:|
| `SITE_01_RECTANGULAR` | Standard Suburban Rectangular | $30 \times 25$ | 0.940 | 0.778 | 158.9 |
| `SITE_02_NARROW` | Narrow Urban Infill | $14 \times 35$ | 0.940 | 0.760 | 163.7 |
| `SITE_03_L_SHAPED` | L-Shaped Courtyard Parcel | $32 \times 30$ | 0.939 | 0.781 | 166.6 |
| `SITE_04_CORNER_LOT` | Corner Lot (Dual Road Access) | $28 \times 28$ | 0.940 | 0.788 | 163.7 |
| `SITE_05_LARGE_ESTATE` | Spacious Tropical Acreage | $45 \times 40$ | 0.944 | 0.781 | 159.8 |

- **Mean Inference Latency**: **162.5 ms** on single-core CPU execution.
- **Memory Consumption**: Peak RSS < 92 MB during full forward pass and NMS decoding.
- **Activation Dynamic Range**: Peak activations consistently exceed 0.939, demonstrating sharp localization on viable garden land.

### 4.2 Comparative Benchmark: Full-System Performance

| Generative Pipeline | Average Latency | Tree Requirement Satisfaction | Seating Requirement Satisfaction | Obstacle Violations | Rule Pass Rate | Acceptance Rate |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Deterministic Baseline (Phase 4)** | 215.4 ms | 0.0% *(omitted when grid stepping fails)* | 100.0% | 4 | 92.1% | 80.0% *(conditional draft)* |
| **Random Proposal Baseline** | 247.7 ms | 100.0% | 100.0% | 9 | 87.7% | 50.0% *(frequent blocks)* |
| **Trained Model Hybrid (Phase 6/7)** | 402.3 ms | **95.0%** | **100.0%** | 9 | 87.5% | 40.0% *(strict compliance gating)* |

### 4.3 Scientific Interpretations & Disclaimers

1. **Rule Pass Rate vs. AI Accuracy**:
   - The 87.5% rule pass rate represents **hard regulatory satisfaction** across 54 strict rules, not neural classification accuracy.
   - Missing professional structural certification or boundary wall height confirmation naturally produces `review_required` statuses under our strict zero-fabrication contract.
2. **User Count Satisfaction vs. Learned Count Prediction**:
   - Target tree and seating counts are supplied by user preferences; the neural model predicts **where** to place objects (spatial density), while the geometric decoder enforces **how many** and verifies separation. Decoder-supplied counts must not be reported as learned count accuracy.
3. **Path Generation**:
   - Pedestrian walkways and driveways are constructed via deterministic A* and polygon buffering algorithms; the model only provides an advisory guidance field.

---

## 5. Technical Limitations & Generalization Bounds

1. **2D Ground Scope**:
   - The UNet operates on 2D ground representations. Elevated rooftop solar panel packing and balcony planter arrangements are executed by deterministic 3D surface planners.
2. **Extreme Irregular Geometries**:
   - On parcels with aspect ratios exceeding 5:1 (e.g. $10\text{m} \times 60\text{m}$), aspect-preserving normalization compresses lateral resolution, which may reduce peak localization sensitivity.
3. **Non-Replacing of Engineering Certification**:
   - Model predictions and rule evaluations do not replace certified geotechnical, structural, or legal land surveyor sign-offs.
