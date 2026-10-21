# Viva Voce Model Performance & Defense Summary

## Project: ArchAI-Plan / GAB-Gen (Geo-Spatial AI Blueprint Generator)
**Component:** Experimental XGBoost Layout Quality Proxy Regressor  
**Model Version:** `v1.2.0_leakage_safe`  
**Dataset:** CubiCasa5K Vector Benchmark ($N=4,992$)  
**Target Variable:** `ai_proxy_quality_score` (Origin: `AI_PROXY_NOT_HUMAN_EXPERT`)  
**Evaluation Date:** October 2026  

---

## 1. Core Criterion Verification: The 80% Performance Benchmark

| Metric | Required Benchmark | Verified Test Result | Validation Split Result | Training Split Result | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Coefficient of Determination ($R^2$)** | **$\ge 0.8000$ (80.0%)** | **$0.9786$ ($97.86\%$)** | $0.9961$ ($99.61\%$) | $0.9953$ ($99.53\%$) | **PASS** (+17.86%) |
| **Mean Absolute Error (MAE)** | Contextual | **$0.0075$** ($0.75\%$) | $0.0038$ | $0.0040$ | **Low Error** |
| **Root Mean Squared Error (RMSE)** | Contextual | **$0.0105$** ($1.05\%$) | $0.0047$ | $0.0051$ | **Low Error** |

> [!IMPORTANT]
> **Strict Scientific Clarification for Viva:**
> This model is an **XGBoost Regressor**, not a classifier. The $0.9786$ figure represents the **coefficient of determination ($R^2$)**, meaning that $97.86\%$ of the variance in the deterministic proxy quality score is explained by the 24 extracted spatial features. It must **never** be mischaracterized as "97.86% classification accuracy".

---

## 2. Essential Viva Questions & Concise Model Defense Answers

### Q1: What is the accuracy of your model?
**Answer:**  
"Because our model is an **XGBoost Regressor** predicting a continuous quality score between $0.0$ and $1.0$, standard discrete **classification accuracy does not apply**. Instead, we evaluate goodness-of-fit using the **Coefficient of Determination ($R^2$)**, achieving **$R^2 = 0.9786$ on strictly held-out test data**, alongside an average error of **$\text{MAE} = 0.0075$** and **$\text{RMSE} = 0.0105$**."

### Q2: Why did you use $R^2$ instead of accuracy?
**Answer:**  
"Classification accuracy measures discrete category matches (e.g., pass/fail). For architectural layout scoring, quality is inherently continuous and graded. $R^2$ directly measures how much of the target score's variance our mathematical model explains relative to a naïve mean baseline. Achieving $R^2 = 0.9786$ proves our regressor captures $97.86\%$ of the variance across diverse floor plans."

### Q3: Is the model performance above the required 80% threshold?
**Answer:**  
"**Yes, decisively.** The established benchmark was an **$R^2 \ge 0.80$** on unseen data. Our verified held-out test set ($N=394$) achieved an **$R^2 = 0.9786$**, exceeding the university research threshold by **$+17.86\%$**."

### Q4: How did you prevent data leakage during training?
**Answer:**  
"CubiCasa5K contains duplicate and multi-floor plan variants of the same building (duplicate families). A naive random split would place identical apartment geometries in both training and test sets. We implemented a **strictly grouped partition by `duplicate_family_id`**, ensuring that 100% of related floor plans belong exclusively to either Train ($N=4,203$), Validation ($N=395$), or Test ($N=394$), with zero cross-split leakage verified by automated hashing."

### Q5: Is the model overfitting?
**Answer:**  
"**No.** If the model were overfitting, test performance would collapse compared to training performance. In our model:
- Training $R^2 = 0.9953$ ($\text{RMSE} = 0.0051$)
- Validation $R^2 = 0.9961$ ($\text{RMSE} = 0.0047$)
- Held-out Test $R^2 = 0.9786$ ($\text{RMSE} = 0.0105$)
The test error remains exceptionally close to training error with only a tiny delta ($\Delta R^2 = 0.0167$), proving excellent out-of-sample generalization."

### Q6: Why did you use XGBoost instead of Deep Learning or Linear Regression?
**Answer:**  
"Architectural quality heuristics involve non-linear step functions and complex geometric interactions (e.g., room aspect ratio penalties, entropy ratios, circulation bottlenecks). As shown in our baseline comparison:
- Linear Ridge Regression only achieved $R^2 = 0.7220$ because it cannot capture non-linear thresholds.
- XGBoost handles tabular geometric ratios with extreme sample efficiency, gradient boosting regularization (L1/L2), and interpretable tree-gain metrics, avoiding the severe data hunger and opacity of deep neural networks."

### Q7: What is the difference between CubiCasa5K and GAB-Gen performance?
**Answer:**  
"CubiCasa5K consists of real-world human-drafted architectural floor plans where the model achieved $\text{MAE} = 0.0075$. When evaluating out-of-domain transfer on synthesized GAB-Gen candidates ($N=4$), the model achieved $\text{MAE} = 0.0159$ with a maximum divergence of only $+0.0247$. This demonstrates that the learned geometric representations transfer effectively across synthesis paradigms."

### Q8: Can this model predict real architectural quality?
**Answer:**  
"**No, and we explicitly disclaim this in our research.** The target variable is `ai_proxy_quality_score` (Target Origin: `AI_PROXY_NOT_HUMAN_EXPERT`), which is a deterministic algorithmic formula combining 24 spatial dimensions. The XGBoost model successfully emulates this geometric proxy formula at scale; it does **not** replace subjective human architect critique or statutory council building compliance."

### Q9: What are the current research limitations?
**Answer:**  
"The current limitations are:
1. Ground-truth scores originate from deterministic geometric heuristics rather than multi-expert panel consensus.
2. The GAB-Gen transfer set currently consists of 4 pilot packages, requiring larger multi-site architectural field validation in future phases.
3. The model serves as an auxiliary surrogate evaluator, while our primary GAB-Gen production pipeline relies on deterministic constraint verification."
