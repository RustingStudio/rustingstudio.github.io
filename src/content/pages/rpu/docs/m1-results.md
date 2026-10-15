---
title: "Milestone 1 results"
project: "rpu"
kind: "docs"
group: "Reference"
order: 3
description: "Measured 2026-10-14 on branch milestone-1: RTL and driver at commit da4e054, plus examples/mnist.rs from the phase 9 commit that adds this file. Verilator 5.052, memory read latency 1 cycle."
source: "https://github.com/RustingStudio/RustingPU/blob/main/docs/m1-results.md"
---
Measured 2026-10-14 on branch `milestone-1`: RTL and driver at commit `da4e054`, plus `examples/mnist.rs` from the phase 9 commit that adds this file. Verilator 5.052, memory read latency 1 cycle.

```bash
cargo run --release --features brain --example mnist          # N = 8, trains and saves the network
RPU_N=16 cargo run --release --features brain --example mnist # N = 16, loads the same network
```

## Network

- MNIST (the standard 60k train / 10k test IDX files, in the gitignored `data/mnist/`).
- RustingBrain 4.0.0 (crates.io), 784-128-10, ReLU then softmax, cross-entropy, Adam lr 1e-3, batch 32, 3 epochs, seed `0x6d6e_6973_7400_0001`, CPU only. Training takes 20 s; the epoch losses are 0.2835, 0.1254, 0.0852.
- Training is reproducible: a second run from scratch wrote a byte-identical `mnist-784-128-10.json` (MD5 `82d91856abb13afa577d5e0b28fa1756`).
- Int8: weights per output row, activations one scale per batch of 64 images. Dequantization, bias, ReLU and softmax run on the host. The RPU runs every matmul.

## Accuracy, 10,000 test images

| Path | N = 8 | N = 16 |
|---|---:|---:|
| f32 (RustingBrain) | 9726, 97.26% | 9726, 97.26% |
| host int8 | 9726, 97.26% | 9726, 97.26% |
| RPU | 9726, 97.26% | 9726, 97.26% |

The RPU outputs equal the host int8 outputs with `==` for every batch, at both sizes (the example asserts it). f32 minus int8 is 0.00 pp; the check allows 0.5 pp.

## Cycles

| | N = 8 | N = 16 |
|---|---:|---:|
| RPU busy cycles, 10k images | 18,905,978 | 5,450,401 |
| Cycles per image | 1890.6 | 545.0 |
| Streaming cycles | 16,000,000 | 4,000,000 |
| Array utilization (streaming / busy) | 84.63% | 73.39% |
| Plan estimate, cycles per image | ~1.75k (batch 8) | ~430 (batch 16) |
| Verilator wall time, RPU and host int8 | 16 s | 24 s |

Streaming is exactly `(784 * 128 + 128 * 16) / N^2` cycles per image (the 10 outputs pad to 16 at both sizes): 1600 at N = 8 and 400 at N = 16. Busy cycles count every cycle with a load, compute or C store running; host writes of operands, with the RPU idle, are not counted.

The N = 16 number is 27% above the plan's estimate. The cause is the load at the start of each block of N rows of A: A and the first B tile load together (1568 cycles for layer 1, 256 for layer 2, at both sizes), and nothing overlaps them, because there is one A buffer. The plan's N = 16 estimate leaves that load out. Per image it is 1824 / N cycles, 114 at N = 16, and 430 + 114 = 544 matches the measured 545. At N = 8 the plan included the load: its own terms (16 x 808 + 2 x 152 + 1824 cycles per 8 images) give 1882 cycles per image, and the measured 1890.6 matches; the plan's ~1.75k rounded the sum down. A second A buffer, loaded during the last tiles of the previous block, would remove most of this; it is not in milestone 1.

The plan's baseline for the old design was about 36 minutes of Verilator time for the 10k test set; it is now 16 s at N = 8.
