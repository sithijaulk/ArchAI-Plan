"""
Phase 10: Baseline Models for Architectural Quality Assessment.
Provides non-parametric, statistical, and linear comparison points:
1. MeanPredictor: Predicts the training-set mean label for all instances.
2. HeuristicBaselinePredictor: Maps Phase 5 explainable heuristic scores to the expert evaluation scale.
3. OrdinaryLeastSquaresPredictor: Closed-form (X^T X)^-1 X^T y linear regression with L2 ridge regularization.
Implemented cleanly with pure NumPy for zero external dependency failures.
"""
from typing import Dict, List, Optional
import numpy as np


class MeanPredictor:
    """Predicts the mean training target score."""

    def __init__(self):
        self.mean_value: float = 0.5

    def fit(self, X: np.ndarray, y: np.ndarray) -> "MeanPredictor":
        if len(y) > 0:
            self.mean_value = float(np.mean(y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.full((len(X),), self.mean_value, dtype=float)


class HeuristicBaselinePredictor:
    """
    Evaluates the deterministic Phase 5 heuristic ranking scores against human expert labels.
    Supports optional linear calibration (y = alpha * score + beta) fit exclusively on training data.
    """

    def __init__(self, calibrate: bool = True):
        self.calibrate = calibrate
        self.alpha: float = 1.0
        self.beta: float = 0.0

    def fit(self, heuristic_scores: np.ndarray, y: np.ndarray) -> "HeuristicBaselinePredictor":
        if self.calibrate and len(heuristic_scores) >= 2:
            s = np.asarray(heuristic_scores, dtype=float)
            t = np.asarray(y, dtype=float)
            var_s = np.var(s)
            if var_s > 1e-9:
                cov = np.cov(s, t)[0, 1]
                self.alpha = float(cov / var_s)
                self.beta = float(np.mean(t) - self.alpha * np.mean(s))
            else:
                self.alpha = 1.0
                self.beta = float(np.mean(t) - np.mean(s))
        return self

    def predict(self, heuristic_scores: np.ndarray) -> np.ndarray:
        s = np.asarray(heuristic_scores, dtype=float)
        if self.calibrate:
            preds = self.alpha * s + self.beta
            return np.clip(preds, 0.0, 1.0)
        return s


class RidgeRegressionBaseline:
    """
    Regularized Ridge Regression solved via normal equations:
    w = (X^T X + lambda * I)^-1 X^T y
    """

    def __init__(self, l2_reg: float = 1.0):
        self.l2_reg = l2_reg
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeRegressionBaseline":
        X_mat = np.asarray(X, dtype=float)
        y_vec = np.asarray(y, dtype=float)
        n, d = X_mat.shape

        if n == 0 or d == 0:
            return self

        # Center features and target
        x_mean = np.mean(X_mat, axis=0)
        y_mean = float(np.mean(y_vec))
        X_centered = X_mat - x_mean
        y_centered = y_vec - y_mean

        A = X_centered.T @ X_centered + self.l2_reg * np.eye(d)
        b = X_centered.T @ y_centered

        try:
            self.weights = np.linalg.solve(A, b)
            self.bias = float(y_mean - np.dot(x_mean, self.weights))
        except np.linalg.LinAlgError:
            self.weights = np.zeros((d,), dtype=float)
            self.bias = y_mean

        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X_mat = np.asarray(X, dtype=float)
        if self.weights is None or len(self.weights) == 0:
            return np.full((len(X_mat),), self.bias, dtype=float)
        raw = X_mat @ self.weights + self.bias
        return np.clip(raw, 0.0, 1.0)
