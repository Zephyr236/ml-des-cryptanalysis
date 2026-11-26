"""Small metric helpers shared by training and evaluation."""

from __future__ import annotations

import math

import numpy as np
import torch

__all__ = ["binary_accuracy", "roc_auc", "advantage", "is_finite_metric"]


def binary_accuracy(labels: torch.Tensor, scores: torch.Tensor) -> float:
    predictions = (scores >= 0.5).long()
    return float((predictions == labels.long()).float().mean().item())


def roc_auc(labels, scores) -> float:
    """Rank-based ROC AUC with average ranks for ties.

    Avoids a scikit-learn dependency so the result validator and the
    training image stay small.
    """
    labels = np.asarray(labels).astype(np.int64).ravel()
    scores = np.asarray(scores, dtype=np.float64).ravel()
    n_pos = int(labels.sum())
    n_neg = int(labels.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")

    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(scores.size, dtype=np.float64)
    i = 0
    while i < sorted_scores.size:
        j = i
        while j + 1 < sorted_scores.size and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        average_rank = (i + j + 2) / 2.0  # 1-based ranks
        ranks[order[i : j + 1]] = average_rank
        i = j + 1
    return float((ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def advantage(accuracy: float) -> float:
    """Distinguishing advantage 2 * acc - 1 (zero for a random guess)."""
    return 2.0 * accuracy - 1.0


def is_finite_metric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
