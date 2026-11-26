"""S-box-factorised last-round chunk scorer (SPADE-style).

For an ``R``-round ciphertext pair, the last round is partially
decrypted for one S-box at a time.  A candidate 6-bit chunk key
determines four bits of ``L_{R-1}``; the scorer combines a shared trunk
over the pair context with per-candidate features and an exact log-DDT
initialisation.  With the residual head zero-initialised the model is
exactly the classical log-DDT counter; training learns a residual on top.
"""

from __future__ import annotations

import torch
from torch import nn

from ..data import blocks_to_planes
from ..des import IP, E
from ..des_torch import permute_torch

__all__ = ["ChunkScorer", "last_round_context", "sbox_inputs", "candidate_log_ddt"]

MASK32 = 0xFFFFFFFF


def last_round_context(ciphertext1: torch.Tensor, ciphertext2: torch.Tensor):
    """Return ``(R_R, L_R, R'_R, L'_R)`` from IP(C)."""
    state1 = permute_torch(ciphertext1, IP, 64)
    state2 = permute_torch(ciphertext2, IP, 64)
    return (
        (state1 >> 32) & MASK32,
        state1 & MASK32,
        (state2 >> 32) & MASK32,
        state2 & MASK32,
    )


def sbox_inputs(left: torch.Tensor) -> torch.Tensor:
    """``(..., 8)`` 6-bit S-box inputs of the last round."""
    expanded = permute_torch(left, E, 32)
    return torch.stack([(expanded >> (42 - 6 * j)) & 0x3F for j in range(8)], dim=-1)


class ChunkScorer(nn.Module):
    def __init__(
        self,
        *,
        hidden: int = 256,
        dropout: float = 0.1,
        sbox_lut: torch.Tensor,
        log_ddt: torch.Tensor,
    ) -> None:
        super().__init__()
        self.register_buffer("sbox_lut", sbox_lut.long())
        self.register_buffer("log_ddt", log_ddt.float())
        self.trunk = nn.Sequential(
            nn.Linear(6 * 64, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, hidden),
            nn.GELU(),
        )
        self.key_embedding = nn.Embedding(64, 32)
        self.output_embedding = nn.Embedding(16, 16)
        self.input_embedding = nn.Embedding(64, 16)
        self.sbox_embedding = nn.Embedding(8, 8)
        self.head = nn.Sequential(
            nn.Linear(hidden + 32 + 16 + 16 + 16 + 8 + 1, hidden // 2),
            nn.GELU(),
            nn.Linear(hidden // 2, 1),
        )
        # Start as the exact log-DDT counter.
        nn.init.zeros_(self.head[-1].weight)
        nn.init.zeros_(self.head[-1].bias)

    def forward(
        self,
        plaintext1: torch.Tensor,
        plaintext2: torch.Tensor,
        ciphertext1: torch.Tensor,
        ciphertext2: torch.Tensor,
    ) -> torch.Tensor:
        """Return ``(B, 8, 64)`` summed logits over the pair axis."""
        state1 = permute_torch(ciphertext1, IP, 64)
        state2 = permute_torch(ciphertext2, IP, 64)
        right1 = (state1 >> 32) & MASK32
        left1 = state1 & MASK32
        right2 = (state2 >> 32) & MASK32
        left2 = state2 & MASK32
        context = torch.cat(
            [
                blocks_to_planes(plaintext1),
                blocks_to_planes(plaintext2),
                blocks_to_planes(right1),
                blocks_to_planes(right2),
                blocks_to_planes(left1),
                blocks_to_planes(left2),
            ],
            dim=-1,
        )
        trunk = self.trunk(context)  # (B, M, hidden)
        inputs1 = sbox_inputs(left1)
        inputs2 = sbox_inputs(left2)
        difference = inputs1 ^ inputs2
        candidates = torch.arange(64, device=left1.device)
        logits = []
        for j in range(8):
            u1 = inputs1[..., j]
            u2 = inputs2[..., j]
            a = difference[..., j]
            six1 = u1.unsqueeze(-1) ^ candidates
            six2 = u2.unsqueeze(-1) ^ candidates
            outputs = self.sbox_lut[j][six1] ^ self.sbox_lut[j][six2]
            ddt = self.log_ddt[j][a.unsqueeze(-1), outputs]
            key = self.key_embedding(candidates)
            out = self.output_embedding(outputs)
            inp = self.input_embedding(u1.unsqueeze(-1).expand_as(six1))
            inp2 = self.input_embedding(u2.unsqueeze(-1).expand_as(six2))
            sbox = self.sbox_embedding(torch.full_like(six1, j, dtype=torch.long))
            trunk_expanded = trunk.unsqueeze(2).expand(-1, -1, 64, -1)
            features = torch.cat(
                [
                    trunk_expanded,
                    key.unsqueeze(0).unsqueeze(0).expand(trunk.shape[0], trunk.shape[1], -1, -1),
                    out,
                    inp,
                    inp2,
                    sbox,
                    ddt.unsqueeze(-1),
                ],
                dim=-1,
            )
            logits.append(self.head(features).squeeze(-1) + ddt)
        return torch.stack(logits, dim=1).sum(dim=2)


def candidate_log_ddt(
    ciphertext1: torch.Tensor,
    ciphertext2: torch.Tensor,
    sbox_lut: torch.Tensor,
    log_ddt: torch.Tensor,
) -> torch.Tensor:
    """Exact log-DDT counter, ``(B, 8, 64)``, for the baseline."""
    state1 = permute_torch(ciphertext1, IP, 64)
    state2 = permute_torch(ciphertext2, IP, 64)
    inputs1 = sbox_inputs(state1 & MASK32)
    inputs2 = sbox_inputs(state2 & MASK32)
    candidates = torch.arange(64, device=ciphertext1.device)
    result = []
    for j in range(8):
        u1 = inputs1[..., j]
        u2 = inputs2[..., j]
        a = u1 ^ u2
        six1 = u1.unsqueeze(-1) ^ candidates
        six2 = u2.unsqueeze(-1) ^ candidates
        outputs = sbox_lut[j][six1] ^ sbox_lut[j][six2]
        result.append(log_ddt[j][a.unsqueeze(-1), outputs].sum(dim=1))
    return torch.stack(result, dim=1)
