import pytest

torch = pytest.importorskip("torch")

from des_ml.data import SPLIT_TEST, key_split
from des_ml.eval.ddt_rank import (
    chunk_scores,
    make_pairs,
    rank_stats,
    sample_keys,
    true_chunks,
)
from des_ml.last_round import chunk_ddt_score, true_chunk_key
from des_ml.theory.ddt import ddt_tables

DDT = ddt_tables()
KEY = 0x133457799BBCDFF1


def test_true_chunks_match_scalar():
    keys = torch.tensor([KEY, 0x0F1E2D3C4B5A6978], dtype=torch.long)
    for rounds in (2, 4, 8, 16):
        chunks = true_chunks(keys, rounds)
        for row, key in enumerate(keys.tolist()):
            for j in range(8):
                assert int(chunks[row, j]) == true_chunk_key(key, rounds, j)


def test_scores_match_scalar_ddt():
    generator = torch.Generator().manual_seed(5)
    keys = torch.tensor([KEY], dtype=torch.long)
    c1, c2 = make_pairs(
        keys, 3, rounds=4, mode="cpa", delta=1, generator=generator, device="cpu"
    )
    scores = chunk_scores(c1, c2)
    assert scores.shape == (1, 8, 64)
    for j in range(8):
        for candidate in (0, 7, 63):
            expected = sum(
                chunk_ddt_score(
                    int(c1[0, m]), int(c2[0, m]), candidate, j, DDT[j]
                )
                for m in range(3)
            )
            assert float(scores[0, j, candidate]) == pytest.approx(expected, abs=1e-5)


def test_rank_stats_known_ordering():
    scores = torch.zeros((1, 8, 64))
    truth = torch.zeros((1, 8), dtype=torch.long)
    stats = rank_stats(scores, truth)
    assert stats["mean_rank"] == pytest.approx(32.5)  # all tied
    assert stats["top1"] == 0.0

    best = scores.clone()
    best[0, :, 0] = 1.0
    assert rank_stats(best, truth)["mean_rank"] == pytest.approx(1.0)
    assert rank_stats(best, truth)["top1"] == pytest.approx(1.0)

    worst = scores.clone()
    worst[0, :, 0] = -1.0
    assert rank_stats(worst, truth)["mean_rank"] == pytest.approx(64.0)


def test_sampled_keys_are_key_disjoint():
    generator = torch.Generator().manual_seed(11)
    keys = sample_keys(64, split=SPLIT_TEST, generator=generator)
    assert keys.numel() == 64
    assert bool((key_split(keys) == SPLIT_TEST).all())


def test_pair_shapes_and_rounds():
    generator = torch.Generator().manual_seed(12)
    keys = sample_keys(3, generator=generator)
    for mode, delta in (("kpa", None), ("cpa", 0x0F0F0F0F0F0F0F0F)):
        c1, c2 = make_pairs(
            keys, 5, rounds=4, mode=mode, delta=delta, generator=generator, device="cpu"
        )
        assert c1.shape == (3, 5)
        assert c2.shape == (3, 5)
        assert not torch.equal(c1, c2)
