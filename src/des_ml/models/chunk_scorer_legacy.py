"""Legacy shared-head chunk scorer (2-round checkpoint, run fa7d023)."""

from __future__ import annotations

import torch
from torch import nn

from ..data import blocks_to_planes
from ..des import IP, E
from ..des_torch import permute_torch

__all__ = ["LegacyChunkScorer"]

MASK32 = 0xFFFFFFFF


def _sbox_inputs(left: torch.Tensor) -> torch.Tensor:
    expanded = permute_torch(left, E, 32)
    return torch.stack([(expanded >> (42 - 6 * j)) & 0x3F for j in range(8)], dim=-1)


class LegacyChunkScorer(nn.Module):
    def __init__(self, *, hidden=256, dropout=0.1, sbox_lut, log_ddt) -> None:
        super().__init__()
        self.register_buffer("sbox_lut", sbox_lut.long())
        self.register_buffer("log_ddt", log_ddt.float())
        self.trunk = nn.Sequential(
            nn.Linear(4 * 64, hidden), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(hidden, hidden), nn.GELU(),
        )
        self.key_embedding = nn.Embedding(64, 32)
        self.output_embedding = nn.Embedding(16, 16)
        self.input_embedding = nn.Embedding(64, 16)
        self.sbox_embedding = nn.Embedding(8, 8)
        self.head = nn.Sequential(
            nn.Linear(hidden + 32 + 16 + 16 + 8 + 1, hidden // 2),
            nn.GELU(), nn.Linear(hidden // 2, 1),
        )

    def forward(self, plaintext1, plaintext2, ciphertext1, ciphertext2):
        state1 = permute_torch(ciphertext1, IP, 64)
        state2 = permute_torch(ciphertext2, IP, 64)
        right1 = (state1 >> 32) & MASK32
        left1 = state1 & MASK32
        right2 = (state2 >> 32) & MASK32
        left2 = state2 & MASK32
        context = torch.cat(
            [blocks_to_planes(plaintext1), blocks_to_planes(plaintext2),
             blocks_to_planes(right1), blocks_to_planes(right2)], dim=-1,
        )
        trunk = self.trunk(context)
        inputs1 = _sbox_inputs(left1)
        inputs2 = _sbox_inputs(left2)
        candidates = torch.arange(64, device=left1.device)
        logits = []
        for j in range(8):
            u1, u2 = inputs1[..., j], inputs2[..., j]
            a = u1 ^ u2
            six1 = u1.unsqueeze(-1) ^ candidates
            six2 = u2.unsqueeze(-1) ^ candidates
            outputs = self.sbox_lut[j][six1] ^ self.sbox_lut[j][six2]
            ddt = self.log_ddt[j][a.unsqueeze(-1), outputs]
            features = torch.cat(
                [
                    trunk.unsqueeze(2).expand(-1, -1, 64, -1),
                    self.key_embedding(candidates).unsqueeze(0).unsqueeze(0).expand(
                        trunk.shape[0], trunk.shape[1], -1, -1),
                    self.output_embedding(outputs),
                    self.input_embedding(u1.unsqueeze(-1).expand_as(six1)),
                    self.sbox_embedding(torch.full_like(six1, j, dtype=torch.long)),
                    ddt.unsqueeze(-1),
                ], dim=-1,
            )
            logits.append(self.head(features).squeeze(-1) + ddt)
        return torch.stack(logits, dim=1).sum(dim=2)
