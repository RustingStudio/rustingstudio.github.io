---
title: "Changelog"
project: "rpu"
kind: "docs"
group: "Reference"
order: 4
description: "The first public release. Every number below comes from Verilator, not silicon; the measurements and their commits are in docs/perf-log.md."
source: "https://github.com/RustingStudio/RustingPU/blob/main/CHANGELOG.md"
---
## 1.0.0

The first public release. Every number below comes from Verilator, not
silicon; the measurements and their commits are in
[`docs/perf-log.md`](/rpu/docs/perf-log/).

### The accelerator

- An N x N output-stationary systolic array of int8 x int8 -> int32 PEs, N a
  build parameter (4 to 64 tested), K up to 1024 per panel.
- A GEMM sequencer that tiles larger matrices: A stays loaded across a row
  block, the next B tile loads while the current one computes, and the next
  GEMM starts while the last one drains.
- Bias, ReLU and requantization to int8 between layers in hardware, so hidden
  layers stay in RPU memory.
- A 1 MB simulated memory (N / 16 MB above N = 16) with a configurable read
  latency and one read port shared by the loads and the host.
- Build parameters through the environment: `RPU_N`, `RPU_READ_LATENCY`,
  `RPU_LOAD_BEATS`, `RPU_QUANT_PARTS`, `RPU_HOST_WORDS`.

### The driver

- `Rpu`, a Rust wrapper over the Verilated model, with cycle, wall-cycle and
  host-word counters.
- `RpuMlp` (feature `brain`) runs a RustingBrain MLP on the RPU.
- Every result is checked with `==` against the host int8 reference in
  `quant`.

### Results

MNIST 784-128-10 MLP, 10,000 test images, batch 64:

- 97.25% accuracy on the RPU, equal to host int8 and 0.01 pp from f32.
- N = 8: 1890.6 cycles per image at milestone 1, 1624.3 now, 84.63% to 98.50%
  array utilization.
- N = 16: 545.0 to 406.2 cycles per image, 73.39% to 98.47% utilization.
- N = 64 (`RPU_LOAD_BEATS=2`): 26.8 cycles per image, 99.49% utilization.
