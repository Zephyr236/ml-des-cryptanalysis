import pytest

torch = pytest.importorskip("torch")

from torch.nn import functional as F

from des_ml.des_torch import des_encrypt_torch, key_schedule_torch, rand64
from des_ml.eval.ddt_rank import log_ddt_tensor, sbox_lut
from des_ml.models.chunk_scorer import ChunkScorer, candidate_log_ddt


def test_chunk_scorer_shapes_and_ddt_initialisation():
    generator = torch.Generator().manual_seed(11)
    keys = rand64(4, generator=generator)
    plaintext1 = rand64(4 * 8, generator=generator)
    plaintext2 = plaintext1 ^ 1
    repeated = keys.repeat_interleave(8)
    ciphertext1 = des_encrypt_torch(plaintext1, repeated, 4).reshape(4, 8)
    ciphertext2 = des_encrypt_torch(plaintext2, repeated, 4).reshape(4, 8)
    model = ChunkScorer(
        hidden=32,
        dropout=0.0,
        sbox_lut=sbox_lut(),
        log_ddt=log_ddt_tensor(),
    )
    logits = model(
        plaintext1.reshape(4, 8), plaintext2.reshape(4, 8), ciphertext1, ciphertext2
    )
    ddt = candidate_log_ddt(
        ciphertext1, ciphertext2, model.sbox_lut, model.log_ddt
    )
    assert logits.shape == (4, 8, 64)
    per_pair = model(
        plaintext1.reshape(4, 8),
        plaintext2.reshape(4, 8),
        ciphertext1,
        ciphertext2,
        return_per_pair=True,
    )
    assert per_pair.shape == (4, 8, 8, 64)
    assert torch.allclose(logits.detach(), ddt, atol=1e-6)

    truth = torch.stack(
        [
            (key_schedule_torch(keys, 4)[-1] >> (42 - 6 * j)) & 0x3F
            for j in range(8)
        ],
        dim=1,
    )
    loss = F.cross_entropy(logits.reshape(-1, 64), truth.reshape(-1))
    loss.backward()
    assert torch.isfinite(loss)
