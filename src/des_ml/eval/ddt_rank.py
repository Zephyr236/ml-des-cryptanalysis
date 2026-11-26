"""Exact log-DDT ranking of last-round chunks.

This is the classical counter that SPADE's DDT-initialised residual must
beat.  For a fixed target key, each S-box is a 64-way hypothesis; the
score of a candidate is the sum, over pairs, of the log-DDT likelihood
of the observed output difference given the key-independent input
difference.  The true chunk is ranked against the other 63.

Nothing here is neural and nothing needs a gradient.  The point is to
measure whether the chosen data (round count, KPA/CPA, delta, pair
budget) carries usable classical signal at all.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import torch

from ..data import SPLIT_TEST, key_split
from ..des import IP, E, sbox_output
from ..des_torch import des_encrypt_torch, key_schedule_torch, permute_torch, rand64
from ..theory.ddt import ddt_tables

__all__ = [
    "sbox_lut",
    "log_ddt_tensor",
    "sample_keys",
    "make_pairs",
    "true_chunks",
    "chunk_scores",
    "ranks",
    "rank_stats",
]

DDT_FLOOR = 2.0**-8
MASK32 = 0xFFFFFFFF


@lru_cache(maxsize=1)
def sbox_lut() -> torch.Tensor:
    """``(8, 64)`` lookup table: 6-bit input -> 4-bit S-box output."""
    table = torch.zeros((8, 64), dtype=torch.long)
    for j in range(8):
        for six in range(64):
            table[j, six] = sbox_output(j, six)
    return table


@lru_cache(maxsize=1)
def log_ddt_tensor(floor: float = DDT_FLOOR) -> torch.Tensor:
    """``(8, 64, 16)`` log-likelihood table with the ADR-0008 floor."""
    counts = ddt_tables().astype(np.float64) / 64.0
    return torch.tensor(np.log(np.maximum(counts, floor)), dtype=torch.float32)


def sample_keys(
    n: int,
    *,
    split: int = SPLIT_TEST,
    device: torch.device | str = "cpu",
    generator: torch.Generator | None = None,
) -> torch.Tensor:
    """Draw ``n`` keys from a key-disjoint bucket."""
    chunks: list[torch.Tensor] = []
    collected = 0
    while collected < n:
        candidates = rand64(max(n, 64), device=device, generator=generator)
        selected = candidates[key_split(candidates) == split]
        if selected.numel():
            chunks.append(selected)
            collected += selected.numel()
    return torch.cat(chunks)[:n]


def make_pairs(
    keys: torch.Tensor,
    pairs: int,
    *,
    rounds: int,
    mode: str,
    delta: int | None,
    generator: torch.Generator,
    device: torch.device | str,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Return ciphertext tensors ``(K, pairs)`` under one key per row."""
    if mode not in {"kpa", "cpa"}:
        raise ValueError("mode must be 'kpa' or 'cpa'")
    if mode == "cpa" and delta is None:
        raise ValueError("cpa requires a delta")
    n_keys = keys.numel()
    repeated = keys.repeat_interleave(pairs)
    total = repeated.numel()
    plaintext1 = rand64(total, device=device, generator=generator)
    if mode == "cpa":
        plaintext2 = plaintext1 ^ int(delta)
    else:
        plaintext2 = rand64(total, device=device, generator=generator)
    ciphertext1 = des_encrypt_torch(plaintext1, repeated, rounds).reshape(n_keys, pairs)
    ciphertext2 = des_encrypt_torch(plaintext2, repeated, rounds).reshape(n_keys, pairs)
    return ciphertext1, ciphertext2


def true_chunks(keys: torch.Tensor, rounds: int) -> torch.Tensor:
    """``(K, 8)`` true 6-bit chunks of the last-round key."""
    round_key = key_schedule_torch(keys, rounds)[-1]
    return torch.stack(
        [(round_key >> (42 - 6 * j)) & 0x3F for j in range(8)], dim=1
    )


def chunk_scores(
    ciphertext1: torch.Tensor,
    ciphertext2: torch.Tensor,
    *,
    lut: torch.Tensor | None = None,
    log_ddt: torch.Tensor | None = None,
) -> torch.Tensor:
    """Return ``(K, 8, 64)`` summed log-DDT scores for every chunk candidate."""
    lut = sbox_lut() if lut is None else lut
    log_ddt = log_ddt_tensor() if log_ddt is None else log_ddt
    lut = lut.to(ciphertext1.device)
    log_ddt = log_ddt.to(ciphertext1.device)

    state1 = permute_torch(ciphertext1, IP, 64)
    state2 = permute_torch(ciphertext2, IP, 64)
    left1 = state1 & MASK32
    left2 = state2 & MASK32
    expanded1 = permute_torch(left1, E, 32)
    expanded2 = permute_torch(left2, E, 32)

    candidates = torch.arange(64, device=ciphertext1.device)
    per_box: list[torch.Tensor] = []
    for j in range(8):
        input1 = (expanded1 >> (42 - 6 * j)) & 0x3F
        input2 = (expanded2 >> (42 - 6 * j)) & 0x3F
        difference = input1 ^ input2
        six1 = input1.unsqueeze(-1) ^ candidates
        six2 = input2.unsqueeze(-1) ^ candidates
        output_difference = lut[j][six1] ^ lut[j][six2]
        scores = log_ddt[j][difference.unsqueeze(-1), output_difference].sum(dim=1)
        per_box.append(scores)
    return torch.stack(per_box, dim=1)


def ranks(scores: torch.Tensor, truth: torch.Tensor) -> torch.Tensor:
    """Average rank of the true chunk among 64 candidates (1 best, 64 worst)."""
    if scores.shape != (truth.shape[0], 8, 64):
        raise ValueError("scores must be (K, 8, 64)")
    true_scores = scores.gather(2, truth.unsqueeze(-1)).squeeze(-1)
    greater = (scores > true_scores.unsqueeze(-1)).sum(dim=-1)
    equal = (scores == true_scores.unsqueeze(-1)).sum(dim=-1)
    return 1.0 + greater.float() + (equal.float() - 1.0) / 2.0


def rank_stats(scores: torch.Tensor, truth: torch.Tensor) -> dict[str, float]:
    """Summarise the rank distribution of the true chunk."""
    rank_values = ranks(scores, truth)
    flat = rank_values.reshape(-1)
    return {
        "mean_rank": float(flat.mean()),
        "median_rank": float(flat.median()),
        "top1": float((rank_values <= 1.0).float().mean()),
        "top5": float((rank_values <= 5.0).float().mean()),
        "top16": float((rank_values <= 16.0).float().mean()),
        "random_mean_rank": 32.5,
        "random_top1": 1.0 / 64.0,
        "n_chunks": float(flat.numel()),
    }
