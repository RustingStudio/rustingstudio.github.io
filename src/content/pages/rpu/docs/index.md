---
title: "Overview"
project: "rpu"
kind: "docs"
group: "Start"
order: 0
description: "RustingPU is an 8x8 INT8 systolic-array accelerator in SystemVerilog, driven from Rust. It runs a RustingBrain MNIST MLP at 97.25% test accuracy, identical to the CPU int8 reference and 0.01 pp from f32, in 1624.3 cycles per image at 98.50% array utilization. The array size is a build parameter; at 16x16 the same network takes 406.2 cycles per image at 98.47%."
source: "https://github.com/RustingStudio/RustingPU/blob/main/README.md"
---
RustingPU is an 8x8 INT8 systolic-array accelerator in SystemVerilog, driven from Rust. It runs a RustingBrain MNIST MLP at **97.25% test accuracy**, identical to the CPU int8 reference and 0.01 pp from f32, in **1624.3 cycles per image** at **98.50% array utilization**. The array size is a build parameter; at 16x16 the same network takes 406.2 cycles per image at 98.47%.

This will not beat a GPU or your CPU on speed, and the simulation is far slower than either. The point is a complete chip design, from PE to DMA to driver, running a model trained by its own framework, with every result checked bit for bit against a software reference. The RPU does matrix multiplication and, between layers, bias, ReLU and requantization to int8; the host quantizes the input and finishes the last layer. Until milestone 2 every number comes from Verilator, not silicon.

## Numbers

MNIST, 10,000 test images, 784-128-10 MLP (ReLU, softmax) trained with RustingBrain 4.0.0 on the CPU. Measured 2026-10-15 at commit `af4bcd3`; details in [`docs/perf-log.md`](/rpu/docs/perf-log/) (milestone 1 numbers in [`docs/m1-results.md`](/rpu/docs/m1-results/)).

| | N = 8 | N = 16 |
|---|---:|---:|
| f32 accuracy | 97.26% | 97.26% |
| Host int8 accuracy | 97.25% | 97.25% |
| RPU accuracy | 97.25% | 97.25% |
| Cycles per image | 1624.3 | 406.2 |
| Array utilization | 98.50% | 98.47% |
| Wall cycles per image (host writes, reads and waits included) | 1631.4 | 414.3 |
| Host words per image, written / read | 101.5 / 5.0 | 101.5 / 6.0 |

```bash
cargo run --release --features brain --example mnist          # N = 8
RPU_N=16 cargo run --release --features brain --example mnist # N = 16
RPU_BATCH=256 cargo run --release --features brain --example mnist # batch 256 (default 64)
```

## How it works

```text
host (Rust)                          RPU (SystemVerilog, simulated by Verilator)
  RpuMlp: quantize the input           register file: CONTROL, STATUS, A/B/C base, K
  write A, B, parameters -bus-->      1 MB memory, 8*N-bit beats
  start each GEMM                      load FSM: two A and two B local banks
  read the last layer's C,             N x N array of int8 x int8 -> int32 PEs,
  dequantize, bias, softmax            output-stationary, K streamed one per cycle
                                       C drained by shifting rows, stored while the
                                       next tile computes; hidden layers requantized
                                       to int8 (bias, ReLU) in RPU memory
```

The array computes `C[i][j] = sum_k A[i][k] * B[j][k]` for N x K panels, K up to 1024. A weight matrix `[out, in]` is used as B directly. A sequencer in the RPU tiles larger matrices: A stays loaded across all output tiles of a row block, and the next B loads while the current tile computes. The full design is in [`docs/engineering.md`](/rpu/docs/engineering/).

## Build

Needs Rust, Verilator (5.052 tested) and a C++ compiler. Icarus and yosys are optional (smoke test, resource checks).

```bash
cargo test --release                   # bit-exact tests against the host int8 reference
cargo test --release --features brain  # plus the RustingBrain MLP test
RPU_N=16 cargo test --release          # another array size
RPU_N=64 RPU_LOAD_BEATS=2 cargo test --release  # a big array: 2-beat read port (1-cycle requantized rows and one-beat host writes by default above N = 16)
```

The MNIST example reads the four unpacked IDX files from `data/mnist/` (not in the repository; download them from any MNIST mirror). The first run trains the network (about 20 s) and saves it there.

## Limits

- Simulation only. No FPGA bitstream, no host link.
- INT8 matmul with bias, ReLU and requantization between layers. The input quantization, the last layer's bias and softmax run on the host. Output scales are static, calibrated on training images. No convolution, no BF16 or FP32.
- K is at most 1024 per panel; partial sums over K are not split across jobs.
- All operands must fit in the RPU memory: 1 MB up to N = 16, N / 16 MB above.
- The first load of each GEMM is only partly hidden with the board's one-beat read port: the stream starts after about K + 2N beats. A wider port (`RPU_LOAD_BEATS=2`, for bigger parts) starts it after about N.

## Roadmap

1. Milestone 2: the RPU on a Sipeed Tang Mega 60K (Gowin GW5AT-60), with the same predictions bit for bit as Verilator.
2. DDR3 for models larger than on-chip BSRAM.

## License

RustingPU is released under the [RustingPU License 1.0](https://github.com/RustingStudio/RustingPU/blob/main/LICENSE.md). You may
use, modify and distribute it, and sell boards, products and services built on
it, as long as you keep the license and credit Vasyl Trefilov as the original
author. You may not sell RustingPU itself. Changes are listed in
[CHANGELOG.md](/rpu/docs/changelog/).
