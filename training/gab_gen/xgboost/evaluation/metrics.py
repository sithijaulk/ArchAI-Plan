"""
Phase 10: Scientific Evaluation Metrics for Architectural Quality Regression and Ranking.
Implements:
- Continuous Regression: MAE, RMSE, Pearson r, Spearman rho, R-squared.
- Within-Site Ranking: NDCG@K, Pairwise Ranking Accuracy, Top-1 Selection Agreement, Kendall Tau.
Pure NumPy implementation: fully independent of scipy/sklearn to guarantee zero runtime failures.
"""
import math
from typing import Dict, List, Optional, Tuple
import numpy as np


def compute_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error."""
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(np.abs(y_true - y_pred)))


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error."""
    if len(y_true) == 0:
        return 0.0
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def compute_r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Coefficient of Determination (R^2). Returns 0.0 if total sum of squares is 0."""
    if len(y_true) <= 1:
        return 0.0
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot < 1e-12:
        return 0.0
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    return float(1.0 - (ss_res / ss_tot))


def compute_spearman_rho(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Spearman Rank Correlation Coefficient."""
    if len(y_true) <= 1:
        return 0.0
    # Rank transformation
    rank_true = np.argsort(np.argsort(y_true)).astype(float)
    rank_pred = np.argsort(np.argsort(y_pred)).astype(float)

    std_t = np.std(rank_true, ddof=1)
    std_p = np.std(rank_pred, ddof=1)
    if std_t < 1e-12 or std_p < 1e-12:
        return 0.0

    corr_mat = np.corrcoef(rank_true, rank_pred)
    return float(corr_mat[0, 1])


def compute_kendall_tau(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Kendall Tau rank correlation coefficient."""
    n = len(y_true)
    if n <= 1:
        return 0.0
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            true_diff = y_true[i] - y_true[j]
            pred_diff = y_pred[i] - y_pred[j]
            prod = true_diff * pred_diff
            if prod > 0:
                concordant += 1
            elif prod < 0:
                discordant += 1
    total_pairs = n * (n - 1) / 2.0
    return float((concordant - discordant) / total_pairs) if total_pairs > 0 else 0.0


def compute_dcg_at_k(relevance_scores: List[float], k: int) -> float:
    """Discounted Cumulative Gain at rank K."""
    k_eval = min(k, len(relevance_scores))
    dcg = 0.0
    for i in range(k_eval):
        rel = relevance_scores[i]
        dcg += (2.0 ** rel - 1.0) / math.log2(i + 2.0)
    return dcg


def compute_ndcg_at_k(y_true: np.ndarray, y_pred: np.ndarray, k: int = 3) -> float:
    """Normalized Discounted Cumulative Gain at rank K."""
    if len(y_true) == 0:
        return 0.0
    if len(y_true) == 1:
        return 1.0

    order = np.argsort(-y_pred)
    ordered_true = [float(y_true[idx]) for idx in order]
    dcg = compute_dcg_at_k(ordered_true, k)

    ideal_order = np.argsort(-y_true)
    ideal_true = [float(y_true[idx]) for idx in ideal_order]
    idcg = compute_dcg_at_k(ideal_true, k)

    if idcg < 1e-12:
        return 1.0 if dcg < 1e-12 else 0.0
    return float(min(1.0, dcg / idcg))


def compute_pairwise_ranking_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Fraction of pairs whose relative ordering in y_pred matches y_true."""
    n = len(y_true)
    if n <= 1:
        return 1.0
    correct = 0
    total = 0
    for i in range(n):
        for j in range(i + 1, n):
            if y_true[i] != y_true[j]:
                total += 1
                if (y_pred[i] > y_pred[j] and y_true[i] > y_true[j]) or (y_pred[i] < y_pred[j] and y_true[i] < y_true[j]):
                    correct += 1
    return float(correct / total) if total > 0 else 1.0


def compute_top1_agreement(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Returns 1.0 if the candidate ranked highest by prediction is also highest in truth."""
    if len(y_true) == 0:
        return 0.0
    best_pred_idx = int(np.argmax(y_pred))
    best_true_idx = int(np.argmax(y_true))
    return 1.0 if best_pred_idx == best_true_idx else 0.0


def evaluate_regression_and_ranking(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    site_groups: Optional[List[str]] = None,
    k_ndcg: int = 3,
) -> Dict[str, float]:
    """
    Computes global regression metrics and within-site candidate ranking metrics.
    """
    y_t = np.asarray(y_true, dtype=float)
    y_p = np.asarray(y_pred, dtype=float)

    if len(y_t) == 0:
        return {
            "mae": 0.0,
            "rmse": 0.0,
            "r2": 0.0,
            "spearman_rho": 0.0,
            "kendall_tau": 0.0,
            "mean_within_site_ndcg": 0.0,
            "mean_pairwise_ranking_accuracy": 0.0,
            "top1_agreement_rate": 0.0,
        }

    global_mae = compute_mae(y_t, y_p)
    global_rmse = compute_rmse(y_t, y_p)
    global_r2 = compute_r2_score(y_t, y_p)
    global_spearman = compute_spearman_rho(y_t, y_p)
    global_kendall = compute_kendall_tau(y_t, y_p)

    if site_groups is not None and len(site_groups) == len(y_t):
        site_to_indices: Dict[str, List[int]] = {}
        for idx, sg in enumerate(site_groups):
            site_to_indices.setdefault(sg, []).append(idx)

        site_ndcgs = []
        site_pairwise = []
        site_top1 = []

        for site_id, indices in site_to_indices.items():
            if len(indices) >= 2:
                sub_t = y_t[indices]
                sub_p = y_p[indices]
                site_ndcgs.append(compute_ndcg_at_k(sub_t, sub_p, k=k_ndcg))
                site_pairwise.append(compute_pairwise_ranking_accuracy(sub_t, sub_p))
                site_top1.append(compute_top1_agreement(sub_t, sub_p))

        mean_ndcg = float(np.mean(site_ndcgs)) if site_ndcgs else 1.0
        mean_pairwise = float(np.mean(site_pairwise)) if site_pairwise else 1.0
        top1_rate = float(np.mean(site_top1)) if site_top1 else 1.0
    else:
        mean_ndcg = compute_ndcg_at_k(y_t, y_p, k=k_ndcg)
        mean_pairwise = compute_pairwise_ranking_accuracy(y_t, y_p)
        top1_rate = compute_top1_agreement(y_t, y_p)

    return {
        "mae": round(global_mae, 4),
        "rmse": round(global_rmse, 4),
        "r2": round(global_r2, 4),
        "spearman_rho": round(global_spearman, 4),
        "kendall_tau": round(global_kendall, 4),
        "mean_within_site_ndcg": round(mean_ndcg, 4),
        "mean_pairwise_ranking_accuracy": round(mean_pairwise, 4),
        "top1_agreement_rate": round(top1_rate, 4),
    }
