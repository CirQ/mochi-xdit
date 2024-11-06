import torch
import pytest
from genmo.mochi_preview.dit.joint_model.asymm_models_joint import AsymmetricAttention
from genmo.mochi_preview.dit.joint_model.rope_mixed import compute_mixed_rotation, create_position_matrix

def test_forward_xdit_matches_forward():
    # Initialize model parameters
    dim_x = 3072
    dim_y = 1536
    num_heads = 24
    device = torch.device("cuda")
    dtype = torch.bfloat16
    
    batch_size = 1
    seq_len_x = 1590
    seq_len_y = 256

    # Create model instance
    model = AsymmetricAttention(
        dim_x=dim_x,
        dim_y=dim_y,
        num_heads=num_heads,
        qkv_bias=True,
        qk_norm=True,
        update_y=True,
        attention_mode="sdpa",
        device=device,
    ).to(dtype)

    # Create input tensors
    x = torch.randn(batch_size, seq_len_x, dim_x, device=device, dtype=dtype)
    y = torch.randn(batch_size, seq_len_y, dim_y, device=device, dtype=dtype)
    scale_x = torch.randn(batch_size, dim_x, device=device, dtype=dtype)
    scale_y = torch.randn(batch_size, dim_y, device=device, dtype=dtype)

    # Create position encodings
    T, pH, pW = 2, 30, 53  # Example values, adjust as needed

    # Create position array and compute rotations
    N = x.size(1)  # Get actual sequence length

    # T: 2, pH: 30, pW: 53, device: cuda:0, dtype: torch.bfloat16, target_area: 36864 
    pos = create_position_matrix(T, pH=pH, pW=pW, device=device, dtype=dtype)  # (N, 3)

    # Initialize pos_frequencies with correct size
    pos_frequencies = torch.randn(3, num_heads, dim_x // num_heads // 2, device=device, dtype=dtype)

    # Compute rotations for actual sequence length
    rope_cos, rope_sin = compute_mixed_rotation(
        freqs=pos_frequencies, 
        pos=pos[:N]  # Only use positions up to sequence length
    )  # Each are (N, num_heads, dim // 2)

    # Create packed indices
    total_len = seq_len_x + seq_len_y
    valid_token_indices = torch.arange(total_len, device=device)
    cu_seqlens = torch.tensor([0, total_len], device=device, dtype=torch.int32)
    
    packed_indices = {
        "valid_token_indices_kv": valid_token_indices,
        "cu_seqlens_kv": cu_seqlens,
        "max_seqlen_in_batch_kv": total_len,
    }

    # Run both forward passes
    with torch.no_grad():
        out_forward = model.forward(
            x=x,
            y=y,
            scale_x=scale_x,
            scale_y=scale_y,
            packed_indices=packed_indices,
            rope_cos=rope_cos,
            rope_sin=rope_sin,
        )

        out_xdit = model.forward_xdit(
            x=x,
            y=y,
            scale_x=scale_x,
            scale_y=scale_y,
            packed_indices=packed_indices,
            rope_cos=rope_cos,
            rope_sin=rope_sin,
        )

    # Compare outputs
    x_forward, y_forward = out_forward
    x_xdit, y_xdit = out_xdit

    # Check shapes match
    assert x_forward.shape == x_xdit.shape, f"X shape mismatch: {x_forward.shape} vs {x_xdit.shape}"
    assert y_forward.shape == y_xdit.shape, f"Y shape mismatch: {y_forward.shape} vs {y_xdit.shape}"

    # # Check values are close
    torch.testing.assert_close(x_forward, x_xdit, rtol=1e-3, atol=1e-3)
    torch.testing.assert_close(y_forward, y_xdit, rtol=1e-3, atol=1e-3) 


if __name__ == "__main__":
    test_forward_xdit_matches_forward()