"""Neural distinguishers over 64-bit plaintext/ciphertext pairs.

The input is the six bit planes produced by
:meth:`des_ml.data.PairBatch.to_planes`:

    P1, P2, C1, C2, P1 xor P2, C1 xor C2

A small residual 1-D CNN over the 64-bit axis is the primary model.  The
MLP is kept as a deliberate weak baseline: if the CNN cannot beat it,
the inductive bias is not buying anything.
"""

from __future__ import annotations

import torch
from torch import nn

__all__ = ["PairCNN", "PairMLP", "build_model"]


class _ResidualBlock(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(channels, channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(channels)
        self.conv2 = nn.Conv1d(channels, channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        x = torch.relu(self.bn1(self.conv1(x)))
        x = self.bn2(self.conv2(x))
        return torch.relu(x + residual)


class PairCNN(nn.Module):
    def __init__(
        self,
        *,
        in_channels: int = 6,
        channels: int = 64,
        blocks: int = 4,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(in_channels, channels, kernel_size=3, padding=1),
            nn.BatchNorm1d(channels),
            nn.ReLU(),
        )
        self.blocks = nn.Sequential(*(_ResidualBlock(channels) for _ in range(blocks)))
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(channels, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.stem(x)
        x = self.blocks(x)
        x = x.mean(dim=2)  # global average pool over the 64 bit positions
        return self.head(x).squeeze(1)


class PairMLP(nn.Module):
    def __init__(self, *, in_features: int = 384, hidden: int = 512, dropout: float = 0.1) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(in_features, hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(1)


def build_model(config: dict) -> nn.Module:
    name = config.get("name", "pair_cnn")
    if name == "pair_cnn":
        return PairCNN(
            in_channels=int(config.get("in_channels", 6)),
            channels=int(config.get("channels", 64)),
            blocks=int(config.get("blocks", 4)),
            dropout=float(config.get("dropout", 0.1)),
        )
    if name == "pair_mlp":
        return PairMLP(
            in_features=int(config.get("in_features", 6 * 64)),
            hidden=int(config.get("hidden", 512)),
            dropout=float(config.get("dropout", 0.1)),
        )
    raise ValueError(f"unknown model: {name}")
