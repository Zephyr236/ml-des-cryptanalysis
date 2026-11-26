"""Beam search for differential trails in round-reduced DES.

A trail is a sequence of Feistel difference states.  At each round the
active S-boxes (non-zero input difference) contribute a DDT probability;
the trail probability is the product over all active S-boxes and rounds.
The search is a beam search over states: for each state we keep the best
few output-difference combinations per active S-box, merge duplicate
next states, and retain the best ``beam`` states.

The result is a **valid lower bound** on the best characteristic, not a
proof of optimality.  Parameters (beam, branch, combos) must be reported
with every trail.  See ADR-0009.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..des import IP_INV, E, P, permute
from .ddt import ddt_tables

__all__ = [
    "TrailStep",
    "Trail",
    "search",
    "reconstruct",
    "single_bit_starts",
    "sbox_input_differences",
    "expand_node",
    "shuffled_ddt",
]

MASK32 = 0xFFFFFFFF


@dataclass(frozen=True)
class TrailStep:
    left_in: int
    right_in: int
    sbox_inputs: tuple[int, ...]
    sbox_outputs: tuple[int, ...]
    log2_probability: float
    left_out: int
    right_out: int


@dataclass(frozen=True)
class Trail:
    start: tuple[int, int]
    states: tuple[tuple[int, int], ...]
    steps: tuple[TrailStep, ...]
    log2_probability: float
    input_difference: int

    @property
    def probability(self) -> float:
        return 2.0**self.log2_probability


@dataclass
class _Node:
    log2p: float
    left: int
    right: int
    parent: _Node | None
    step: TrailStep | None


def sbox_input_differences(right: int) -> tuple[int, ...]:
    expanded = permute(right, E, 32)
    return tuple((expanded >> (42 - 6 * j)) & 0x3F for j in range(8))


def _top_combinations(
    choice_lists: list[list[tuple[int, float]]], combos: int, branch: int
) -> list[tuple[float, tuple[int, ...]]]:
    states: list[tuple[float, tuple[int, ...]]] = [(0.0, ())]
    for choices in choice_lists:
        expanded: list[tuple[float, tuple[int, ...]]] = []
        for logp, outputs in states:
            for output, logp_output in choices[:branch]:
                expanded.append((logp + logp_output, outputs + (output,)))
        expanded.sort(key=lambda item: item[0], reverse=True)
        states = expanded[:combos]
    return states


def expand_node(
    node: _Node, ddt, *, branch: int, combos: int
) -> list[tuple[float, int, int, _Node, TrailStep]]:
    """Enumerate the best output-difference combinations for one state."""
    inputs = sbox_input_differences(node.right)
    active = [j for j, value in enumerate(inputs) if value]
    choice_lists: list[list[tuple[int, float]]] = []
    for j in active:
        row = ddt[j, inputs[j]]
        choices = [
            (int(output), math.log2(int(count) / 64.0))
            for output, count in enumerate(row)
            if count
        ]
        choices.sort(key=lambda item: item[1], reverse=True)
        choice_lists.append(choices)

    results: list[tuple[float, int, int, _Node, TrailStep]] = []
    for logp, chosen in _top_combinations(choice_lists, combos, branch):
        outputs = [0] * 8
        for index, j in enumerate(active):
            outputs[j] = chosen[index]
        pre_p = 0
        for output in outputs:
            pre_p = (pre_p << 4) | output
        f_difference = permute(pre_p, P, 32)
        next_left = node.right
        next_right = (node.left ^ f_difference) & MASK32
        step = TrailStep(
            node.left,
            node.right,
            inputs,
            tuple(outputs),
            logp,
            next_left,
            next_right,
        )
        results.append((node.log2p + logp, next_left, next_right, node, step))
    return results


def _has_active_step(node: _Node) -> bool:
    cursor = node
    while cursor.step is not None:
        if any(cursor.step.sbox_inputs):
            return True
        cursor = cursor.parent
    return False


def shuffled_ddt(seed: int = 0) -> np.ndarray:
    """Structural null: permute each non-zero DDT row, preserving counts.

    The row sums and the multiset of differential counts are unchanged;
    only the difference-to-difference mapping is destroyed.  A search on
    this table measures how much of a found trail depends on the specific
    DES S-box structure.
    """
    ddt = ddt_tables().copy()
    rng = np.random.default_rng(seed)
    for j in range(8):
        for difference in range(1, 64):
            ddt[j, difference] = rng.permutation(ddt[j, difference])
    return ddt


def search(
    start_states: list[tuple[int, int]],
    rounds: int,
    *,
    beam: int = 2000,
    branch: int = 4,
    combos: int = 12,
    ddt=None,
) -> tuple[dict[int, _Node], dict[int, _Node]]:
    """Return ``(best, best_active)`` per round.

    ``best`` may be a trivial trail with no active S-boxes (one round of
    deterministic Feistel propagation); ``best_active`` requires at least
    one active S-box and is the trail used for key-recovery work.
    """
    if not start_states:
        raise ValueError("at least one start state is required")
    ddt = ddt_tables() if ddt is None else ddt
    nodes = [_Node(0.0, left & MASK32, right & MASK32, None, None) for left, right in start_states]
    best: dict[int, _Node] = {}
    best_active: dict[int, _Node] = {}
    for round_index in range(1, rounds + 1):
        candidates: dict[tuple[int, int], _Node] = {}
        for node in nodes:
            for log2p, left, right, parent, step in expand_node(
                node, ddt, branch=branch, combos=combos
            ):
                key = (left, right)
                if key not in candidates or log2p > candidates[key].log2p:
                    candidates[key] = _Node(log2p, left, right, parent, step)
        nodes = sorted(candidates.values(), key=lambda node: node.log2p, reverse=True)[:beam]
        if not nodes:
            break
        best[round_index] = nodes[0]
        for node in nodes:
            if _has_active_step(node):
                best_active[round_index] = node
                break
    return best, best_active


def reconstruct(node: _Node) -> Trail:
    steps: list[TrailStep] = []
    cursor = node
    while cursor.step is not None:
        steps.append(cursor.step)
        cursor = cursor.parent
    steps.reverse()
    states = [(steps[0].left_in, steps[0].right_in)] + [
        (step.left_out, step.right_out) for step in steps
    ]
    start = states[0]
    input_difference = permute((start[0] << 32) | start[1], IP_INV, 64)
    log2p = sum(step.log2_probability for step in steps)
    return Trail(start, tuple(states), tuple(steps), log2p, input_difference)


def single_bit_starts() -> list[tuple[int, int]]:
    states: list[tuple[int, int]] = []
    for bit in range(32):
        states.append((0, 1 << bit))
        states.append((1 << bit, 0))
    return states
