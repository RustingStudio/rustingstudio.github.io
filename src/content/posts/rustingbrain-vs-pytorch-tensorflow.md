---
title: "Training a 100M transformer in pure Rust: RustingBrain vs PyTorch and TensorFlow"
date: 2026-10-02
description: "A Rust deep-learning library with NVRTC-compiled CUDA kernels against torch.compile and XLA on one RTX 3060. Where it wins, where it loses, and a benchmark bug I shipped."
project: brain
tags: [benchmark, deep learning, CUDA]
minutes: 5
source: "https://github.com/RustingStudio/RustingScience/blob/main/posts/rustingbrain-vs-pytorch-tensorflow/index.md"
---
[RustingBrain](https://github.com/RustingStudio/RustingBrain) is a deep-learning
library I write in Rust. There is no Python in the training loop and no C++
build step. The CUDA kernels are compiled at startup by NVRTC, and everything
else is Rust.

The question for this post: on one consumer GPU, how does it compare with
PyTorch and TensorFlow at their fastest settings?

## The result

Training throughput in tokens per second. Higher is better. One idle RTX 3060
12 GB.

| batch × seq | RustingBrain | TensorFlow (XLA) | PyTorch (`torch.compile`) |
|---|---|---|---|
| 1 × 512  | 13071 | **15560** | 9607  |
| 1 × 1024 | **16352** | 15652 | 12235 |
| 4 × 512  | 22045 | **22412** | 17993 |
| 4 × 1024 | **21787** | 20063 | 20544 |
| 8 × 512  | 22926 | **23906** | 21366 |

In short:

- RustingBrain is faster than PyTorch at every shape.
- TensorFlow with XLA is still faster at three of five shapes, by 2–19%.
- At 1 × 1024 and 4 × 1024, RustingBrain is the fastest of the three.

The biggest gap is at 1 × 512, where TensorFlow is 19% faster. With small
batches, per-step overhead matters more than raw GEMM speed. XLA compiles the
whole step into a few large kernels, and RustingBrain does not do that yet.

## The setup

All three frameworks train the same model:

- Dense decoder-only transformer with 101.7M parameters
- `d_model` 768, 16 layers
- Grouped-query attention: 12 query heads, 4 KV heads, `head_dim` 64
- SwiGLU feed-forward with `d_ff` 1408, RMSNorm, rotary positions
- Vocabulary of 32004, synthetic token IDs (throughput does not depend on
  the content)

Each framework runs at its fastest path:

| | Version | Fast path | Precision |
|---|---|---|---|
| PyTorch | 2.14.0 + CUDA 12.6 | `torch.compile` | FP16 autocast, FP32 master weights, `GradScaler` |
| TensorFlow | 2.21.0 | `jit_compile=True` (XLA) | `mixed_float16` policy |
| RustingBrain | see below | fused CUDA kernels | BF16 activations, FP32 master weights |


Hardware: RTX 3060 12 GB, NVIDIA driver 615.71.09, Linux. On Ampere, BF16 and
FP16 tensor cores have the same peak, 25.5 TFLOPS on this card. So the
different 16-bit formats do not give any side a hardware advantage.

## How we got here: 11905 to 23411 tok/s

The first version of RustingBrain trained this model at **11905 tok/s**. That
is about half of today's number.

### Step 1: measure before changing anything

`nsys profile` showed three custom attention-softmax kernels taking **21.3% of
GPU time**: `causal_softmax_lse`, `causal_softmax_bwd` and
`causal_probs_from_lse`.

My first idea was to make those kernels faster. The profile said no. Each one
already ran at 302–384 GB/s, and the card's memory bandwidth peak is 360 GB/s.
There was no headroom inside them.

The real cost was the `[seq_len, seq_len]` FP32 attention matrix they wrote to
memory and read back. The only way to go faster was to never create that
matrix.

### Step 2: fused flash attention

A fused causal flash-attention kernel for Ampere tensor cores, forward and
backward, removed the matrix completely. This one change moved throughput from
11905 to about **19–20k tok/s**.

### Step 3: many small fusions

After flash attention, nothing large was left. The remaining wins were small,
and each one was measured on its own:

| Change | tok/s | Gain |
|---|---|---|
| Residual add folded into `rmsnorm_bwd` | 22240 | 1.017× |
| Operand copy folded into `rmsnorm_bwd` | 22383 | 1.006× |
| BF16 `grad_out` for flash-attention backward | 22692 | 1.014× |
| Residual duplicate folded into `rmsnorm_fwd` | 22944 | 1.008× |
| Stale gradients instead of zeroing every step | **23411** | **1.020×** |

### The biggest small win: stop zeroing gradients

Every optimizer step cleared 467 MB of gradient buffers. This let the
weight-gradient GEMMs accumulate with `beta = 1`.

The fix is a `grad_dirty` flag per parameter. The first GEMM that writes a
gradient in a step uses `beta = 0` and overwrites the stale buffer. The next
writers accumulate as before. This removes the memset and also the GEMM's read
of its destination.

### A negative result

I also tried folding the residual add into `rmsnorm_fwd`. The copies dropped
from 2.52 ms to 0.08 ms, but `rmsnorm_fwd` itself went from 2.17 ms to
4.63 ms. The read it removed was already hidden under a 22 TFLOPS GEMM, so the
net gain was zero. I did not keep it.

Negative results like this are worth writing down. Without the note, I would
try the same idea again in six months.

### Where the time goes now

GEMMs are 60% of a training step and run at 78–98% of the card's 25.5 TFLOPS
peak. There is almost no headroom there.

The next target is `flash_attention_dkv` at 15.45 ms per step. Ablation shows
it is bound by the MMA pipeline, not by memory bandwidth or occupancy. The
suspect is the fragment packing in its second MMA loop.

## The bug I shipped in this benchmark

The first published version of this table had PyTorch at **23121 tok/s** at
4 × 1024. That number was wrong.

The PyTorch script cast the whole model to FP16 with `model.to(torch.float16)`.
It should have kept FP32 master weights and used `torch.autocast`. With pure
FP16 weights, the loss silently became NaN. A NaN step is cheap, so the number
was fast and meaningless.

The script had a `loss_ok` check, and the check caught it. But I reported the
speed before I looked at that column.

With the fix, PyTorch runs at **20544 tok/s** at 4 × 1024. All PyTorch numbers
in this post come from the fixed script.

> Lesson: a throughput number is only valid if the loss is finite. Now the
> sanity check is a gate, not a column.

## Limitations

Read the table with these in mind:

- **One GPU, one model family.** No multi-GPU, no distributed training, no
  CPU offload. If you need those, use PyTorch.
- **Throughput only.** These are tokens per second with synthetic data. This post
  does not compare convergence or final model quality.
- **Different timing harnesses.** The Python scripts run 5 warmup steps, then
  5 trials of 10 steps, and report the mean. The Rust `bench` binary runs 1
  warmup step, then 10 timed steps. In both, every step copies the loss back
  to the CPU, so the clock only stops after the GPU has finished.
- **Short runs vary.** The table comes from the 10-step sweep, so all three
  frameworks have the same number of timed steps per trial. Longer 60-step
  runs of RustingBrain at 4 × 1024 reach 23411 tok/s instead of 21787. I use
  the sweep number in the table to keep the comparison fair.
- **No `torch.compile` tuning.** PyTorch uses the default `torch.compile`
  mode, not `mode="max-autotune"`. That may close part of the gap.

## Reproduce it

The Python scripts are attached to this post:

- [torch_bench_300m.py](https://github.com/RustingStudio/RustingScience/blob/main/posts/rustingbrain-vs-pytorch-tensorflow/torch_bench_300m.py)
- [tf_bench_300m.py](https://github.com/RustingStudio/RustingScience/blob/main/posts/rustingbrain-vs-pytorch-tensorflow/tf_bench_300m.py)
- [run_all_shapes.sh](https://github.com/RustingStudio/RustingScience/blob/main/posts/rustingbrain-vs-pytorch-tensorflow/run_all_shapes.sh) runs every shape as its own process

```bash
BENCH_BATCH=4 BENCH_SEQ=1024 python torch_bench_300m.py
BENCH_BATCH=4 BENCH_SEQ=1024 python tf_bench_300m.py
```

For RustingBrain:

```bash
./target/release/bench --gpu --mixed-precision \
  --d-model 768 --n-layers 16 --n-heads 12 --n-kv-heads 4 --head-dim 64 \
  --d-ff 1408 --seq-len 1024 --batch-size 4 --steps 10 \
  --gpu-memory-budget-mib 9000
```


Use an idle card. A shared GPU makes every number here meaningless. In my
logs, the same build ran 2.14× slower while another training job used the
card.

If you get different numbers, or you find a mistake in the method, open an
issue on [RustingBrain](https://github.com/RustingStudio/RustingBrain/issues).
I will add corrections to this post.
