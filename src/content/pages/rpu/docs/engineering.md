---
title: "Design"
project: "rpu"
kind: "docs"
group: "Reference"
order: 1
description: "This is the engineering reference for the RPU. It describes the active code, how the simulation is wired, and the rules that keep Rust and RTL in agreement. It started as Hint.md (the BF16 design) and was rewritten for the int8 design of milestone 1. The plan is docs/plan-milestone-1.md; measured numbers per phase are in docs/progress.md."
source: "https://github.com/RustingStudio/RustingPU/blob/main/docs/engineering.md"
---
This is the engineering reference for the RPU. It describes the active code, how the simulation is wired, and the rules that keep Rust and RTL in agreement. It started as `Hint.md` (the BF16 design) and was rewritten for the int8 design of milestone 1. The plan is `docs/plan-milestone-1.md`; measured numbers per phase are in `docs/progress.md`.

## 1. Current design

The RPU is an N x N int8 systolic array (N = 8 by default) driven from Rust through a Verilator model:

```text
Rust API (src/lib.rs)
  -> C ABI in verilated_wrapper/
  -> Verilator model of rtl/rpu_top.sv
       register file, panel buffers, load / compute / store FSMs
       rtl/rpu_sim_memory.sv   external memory model, 8*N-bit beats, 1 MB up to N = 16
                               and N / 16 MB above, LOAD_BEATS beats per read
       rtl/rpu_array.sv        N x N output-stationary array + input skew
         rtl/int8_cell.sv      one PE: int8 x int8 -> int32 accumulate
         rtl/delay_cell.sv     skew registers
```

The array computes an NT GEMM: `C[i][j] = sum_k A[i][k] * B[j][k]`, with A and B both N x K, 1 <= K <= KMAX (1024). Each PE holds a running int32 sum and a shadow register with the finished sum of the tile before, so one tile drains while the next streams. Larger matrices are tiled by Rust; the physical array does not grow.

`cargo test` builds the RTL with Verilator and links it into the crate. There is no FPGA driver yet (milestone 2). `rpu_sim_memory.sv` stands in for the on-chip BSRAM store.

The public API:

```rust
use rusting_pu::{Rpu, TILE};

let mut rpu = Rpu::new()?;
let c = rpu.matmul_nt_i8(&a, &b, m, n, k)?; // A m x k, B n x k, C m x n, all row-major
```

Lower-level methods:

```text
upload_b(base, b, n, k)           write B once; returns a ResidentB handle
matmul_resident(a, m, &b, scratch) GEMM against a resident B; A and C go from `scratch`
upload_a(base, a, m, k) / read_a  write int8 A as panels; returns a ResidentA handle
gemm_i32(&a, &b, c_base)          C = A * B^T, read back as int32
start_gemm_i32(..) / read_i32(&c) the same in two steps: start, then read
gemm_requant(&a, &b, params, out) requantized int8 output stays in memory as the
                                  next GEMM's ResidentA; nothing is read back;
                                  returns once started
sync()                            wait until every started GEMM is done
run_tile_i8(a, b)                 one N x N x N tile
run_panel_i8(a, b, k)             one N x k x N panel job
preload_panel_i8(bank, a, b, k)   load A and B into a local bank, return when loaded
start(bank) / read_c(bank)
cycles()                          busy cycles since the last START
active_cycles() / busy_cycles()   free-running counters since reset
host_words_written() / _read()    host bus traffic since new (reads: memory only)
busy() / done() / load_busy() / compute_busy() / status()
```

`gemm_requant` and `start_gemm_i32` return once the GEMM registers are written, so the host may prepare the next GEMM while it runs (section 8). The driver keeps the memory ranges and the C tile count of each GEMM it started that may still run. Before it touches one of those ranges it waits, on TILES_DONE, for the last GEMM that uses it and for every GEMM started before that one: a host read of a C that may still be written, a host write to an A, B or C that may still be read or written, and a GEMM that reads such a C or writes such a range. A requantized GEMM uses the QPARAM set the one before did not use, and waits for the last GEMM on its own set before it writes the parameters. `preload_panel_i8` and `start` wait for DONE first.

`src/quant.rs` holds the host side of the int8 contract: symmetric per-row quantization, the reference `matmul_nt_i8`, dequantization and the requantization rule (`Requant`, section 6). Every RTL result is compared with `==` against it.

## 2. Build and test

Tools: `rustc`/`cargo`, Verilator (5.052 is tested), Icarus (`iverilog`, `vvp`) for the smoke test, and yosys for the resource checks.

```bash
cargo build
cargo test --release
cargo fmt --all --check
cargo clippy --all-targets -- -D warnings
cargo run --release                     # one tile, checked against the host reference
cargo run --release --example baseline  # cycle counts, see docs/progress.md
```

Build-time parameters are environment variables read by `build.rs`:

```bash
RPU_N=16 cargo test --release            # array size (default 8)
RPU_READ_LATENCY=10 cargo test --release # memory read latency in cycles (default 1)
RPU_LOAD_BEATS=2 cargo test --release    # beats per load request (default 1, must divide N)
RPU_QUANT_PARTS=1 cargo test --release   # store cycles per requantized C row (1 to 4, default 1 above N = 16, else 4)
RPU_HOST_WORDS=2 cargo test --release    # 64-bit words per host memory write (divides ceil(N / 8), default a whole beat above N = 16, else 1)
```

They become `-GN` / `-GREAD_LATENCY` / `-GLOAD_BEATS` / `-GQUANT_PARTS` / `-GHOST_WORDS` for Verilator and are re-exported to Rust, so `TILE` always equals the RTL `N`. `build.rs` clears the Verilator `obj_dir` before each run; stale generated files from another N do not compile.

Icarus smoke test of the array alone (N = 4):

```bash
iverilog -g2012 -o tpu_sim rtl/delay_cell.sv rtl/int8_cell.sv rtl/rpu_array.sv sim/tb_tpu.sv
vvp -n tpu_sim   # prints PASS: 4x4 int8 tile bit-exact
```

Lint:

```bash
verilator --lint-only -Wall -GN=8 --top-module rpu_top \
  rtl/int8_cell.sv rtl/delay_cell.sv rtl/rpu_array.sv rtl/rpu_sim_memory.sv rtl/rpu_top.sv
```

Simulated cycles are RTL cycles, not wall-clock time. The Verilator run time says nothing about FPGA speed.

## 3. Register and memory protocol

The top-level host port is a synchronous memory-mapped bus with 32-bit word addresses and 64-bit data: `mem_we`, `mem_addr`, `mem_wdata`, `mem_rdata`, `mem_re`, `mem_rvalid`, `mem_rwords`, `mem_ready`. A write happens on the clock edge with `mem_we` and `mem_ready` high (so each host write costs one cycle in simulation unless it waits). The memory has one write port, as a BSRAM in simple dual-port mode has, and the C store goes first: `mem_ready` is low while a store writes a beat, and a host memory write holds its inputs until it is high again. Register writes never wait. The simulated memory stops the simulation if the host and the store ever write in one cycle. Register reads are combinational on `mem_rdata`. A memory read goes through the memory's one read port, which the loads share: with `mem_re` high the host holds `mem_addr` until a cycle with `mem_ready` high, which is low while a load issues a read; the words come on `mem_rwords` with `mem_rvalid` READ_LATENCY cycles later, and the host may send one read per cycle. The simulated memory stops the simulation if the host and a load ever read in one cycle (`docs/perf-log.md`, item 29).

### Register map

| Word address | Name | Write | Read |
|---:|---|---|---|
| 0 | CONTROL | command bits | 0 |
| 1 | STATUS | ignored | status bits |
| 2 | A_BASE | A panel beat address | A_BASE |
| 3 | B_BASE | B panel beat address | B_BASE |
| 4 | C_BASE | C tile beat address | C_BASE |
| 5 | K_LEN | K of the next load (reset value N) | K_LEN |
| 6 | ACTIVE | ignored | cycles the array streamed since reset |
| 7 | BUSY | ignored | cycles busy (load, compute or store) since reset |
| 8 | PANEL | beats per panel for GEMM: N * ceil(K/N) | 0 |
| 9 | TILES | GEMM size: row blocks in bits 15:0, B tiles in bits 31:16; bits 33:32 the beats per C row that an int32 store of the last B tile skips (0 with QUANT) | 0 |
| 10 | TILES_DONE | ignored | C tiles stored since reset, in START order (32 bits, wraps) |
| `0x0800_0000 + p` | QPARAM | requantization parameters of one column (see below) | 0 |
| `0x1000_0000 + w` | memory | 64-bit word w | 64-bit word w |

### CONTROL bits

```text
bit 0 START    compute on the selected banks; if the B bank is not loaded, load first.
               Taken while a compute runs: the new compute waits for it
bit 1 BANK     local B bank 0 or 1
bit 2 PRELOAD  load into the selected banks; may overlap a compute on the other banks
bit 3 KEEP_A   the load fetches only B; the A banks keep their contents
bit 4 A_BANK   local A bank 0 or 1: the bank a load fills and a compute reads
bit 5 KEEP_B   the load fetches only A; B bank BANK keeps its contents and is
               marked valid at the end (ignored with KEEP_A)
bit 6 GEMM     run a whole tiled GEMM (see section 8); write it with no other bit
               except QUANT and QSET
bit 7 QUANT    store each C row requantized to int8 (section 6) as one beat;
               with GEMM, in the A panel layout of the next GEMM
bit 8 QSET     with QUANT: the QPARAM set the store reads
```

QPARAM holds one 64-bit word per output column: bias in bits 31:0 (int32, in the accumulator domain), mult in bits 47:32 (u16), shift in bits 53:48 (at most 48), relu in bit 54. The words of B tile j are in L = ceil(N/P) lanes, P = QUANT_PARTS; column `j*N + part*L + lane` (part 0..P-1) is at `0x0800_0000 + ((j*P + part) << LANE_W) + lane`, LANE_W = clog2(L) (1 when L = 1). There are two sets: set 1 starts at `0x0800_0000 + (P * ceil(KMAX/N) << LANE_W)`, and a requantized GEMM reads the set of its CONTROL QSET bit, so the host can write the parameters of the next GEMM while one runs on the other set. The parameters live in LUT RAM, 2 * P * ceil(KMAX/N) words per lane. The board keeps P = 4; P = 1 stores a requantized row in one cycle with N lanes (`docs/perf-log.md`, item 18). Columns past n keep stale parameters; that is harmless (see the memory layout).

During a GEMM the sequencer drives START and PRELOAD itself and moves A_BASE, B_BASE and C_BASE as it goes. **Do not write registers until GEMM_READY**: the sequencer is idle and the last tile is loaded and taken by the compute, which latches its K, bases and flags. BUSY stays high and DONE low until the last tile is stored.

There are two local A buffers and two local B buffers. A B bank is marked valid when its load ends; the A banks are not tracked. **Never load A into the A bank of a running compute** (a load without KEEP_A and with the same A_BANK): it overwrites the A the compute is reading. `preload_panel_i8` and `start` use the same number for both banks.

Each panel row keeps both A banks in one memory, A bank 1 from beat `ROW_BEATS`. The A read address is one register (`stream_a_addr`), so yosys folds it into a synchronous BSRAM read port. An address made of two registers with different enables (`{bank, beat}`) is not folded and the memory goes to LUT RAM; the B panels are mapped that way today (see `docs/perf-log.md`, item 3).

### STATUS bits

```text
bit 0 BUSY            load, compute, drain, store or GEMM sequencer running
bit 1 DONE            compute finished, drained and C stored, no GEMM running
bit 2 LOAD_BUSY
bit 3 COMPUTE_BUSY    CLEAR or STREAM; the settle and drain after it do not count
bit 4 LOCAL_VALID_0   bank 0 loaded and not yet computed
bit 5 LOCAL_VALID_1
bit 6 STORE_BUSY      C store running (overlaps the next compute)
bit 7 GEMM_READY      no GEMM sequencer running and no load pending: the
                      registers may take the next GEMM
```

### Memory layout

Memory moves 8*N-bit beats (N int8 values in N/8 host words rounded up, lowest word first; when N is not a multiple of 8, the top bytes of a beat's last word are padding). Base registers hold beat addresses. A load request reads LOAD_BEATS consecutive beats from an address rounded down to a multiple of LOAD_BEATS, so A_BASE and B_BASE must be multiples of LOAD_BEATS (`run_gemm` checks it). The board keeps LOAD_BEATS = 1; 2 is the wide read port of a bigger part (`docs/perf-log.md`, item 14). A host memory write or read moves HOST_WORDS words from a multiple of HOST_WORDS in one cycle: one on the board, a whole beat above N = 16 (items 23 and 29).

- A and B panels: N rows of `ceil(K/N)` beats each, stored column by column: beat c of rows 0..N-1, then beat c + 1 (`pack_panels`). Beat c of a row holds k = cN .. cN + N - 1, k = cN in the lowest byte, zero padded past K. A load reads one column of A and then the same column of B, so the stream can read column c before the later columns arrive.
- C tile: row-major int32, 4 beats per row (two int32 per host word, low half first). In a GEMM without QUANT, the last B tile stores only the first 4 - TILES[33:32] beats of each row, and the other beats keep what was there; `run_gemm` sets TILES[33:32] so that these are the beats that hold columns below n. `gemm_i32` reads back only the rows below m and, per row, the beats that hold the columns below n.
- Requantized output (QUANT): one int8 beat per row. With GEMM, row i of tile (r, j) goes to beat C_BASE + r * nt * N + j * N + i, which is beat column j of A block r of the next GEMM with K = n. Padding rows and columns hold requantized garbage; the next GEMM streams only k < K and its padding rows are never read back.

Rust decides where operands live. `preload_panel_i8` uses a fixed per-bank layout (A, B, C of each bank). `matmul_nt_i8` writes B (all its tiles) from beat 0, then calls `matmul_resident` with the scratch area right after B: all A blocks, then a C area with one tile per output tile. `RpuMlp` uploads each layer's weights once, back to back from beat 0, and puts the scratch area after the last layer; each batch writes only its activations. A `ResidentB` remembers which `Rpu` it was uploaded to, and `matmul_resident` panics if the scratch area overlaps B. After `RpuMlp::calibrate`, a batch writes its input A after the weights, and each fused layer writes its int8 output right after its input; the last layer's C goes after that and is the only data read back.

### State machines

```text
load (issue and receive sides, one request of LOAD_BEATS beats per cycle):
  per beat column: the A rows (unless KEEP_A) into A bank A_BANK, then the B
  rows (unless KEEP_B) into B bank BANK; at the end the B bank is marked
  valid, unless the load came from START

launch (one START waiting for the compute):
  a START on a loaded bank, or a START that loads, is held until the compute is
  IDLE or FINISH and its operands are far enough in: at once for a loaded bank;
  for a load, once K + 2N responses are in (A and B, LOAD_BEATS = 1),
  2N / LOAD_BEATS + 1 (A and B, LOAD_BEATS > 1) or N / LOAD_BEATS + 1 (one
  panel), or at the end of the load (see below)

compute:
  IDLE -> CLEAR   set up the stream; wait while it could end before the tile
                  before it leaves the settle (see below)
       -> STREAM  K cycles, one k per cycle from the local panels; the last k
                  carries the last flag
       -> FINISH  (a held START streams from here)

settle (separate, starts when a STREAM ends; runs while the tile before shifts):
  OPERAND_STAGES + 2N - 2 + PE_LATENCY - 1 cycles (2N) until the last sum lands in
  the shadow registers, then wait until the drain is idle and the C store of the
  tile before is done, and hand the tile to the drain

drain:
  IDLE -> SHIFT   N cycles, the shadows shift one row down per cycle into mem_c,
                  row N-1 first; row q shifts in the first q cycles only
       -> IDLE

store (separate, starts with SHIFT and follows it from row N-1 down to row 0, at
most one row per cycle, so it reads each row of mem_c after the drain wrote it):
  4N beats, one per cycle; the memory never stalls a store write (host writes wait for it). The last B tile of
  a GEMM stores 4 - TILES[33:32] beats per row, so (4 - skip)N cycles. With QUANT,
  QUANT_PARTS cycles per row: each cycle reads the parameters of L columns and requantizes
  them in five register stages (read; bias add and multiply; rounding add;
  shift; clamp), then one beat per row is written
```

## 4. Systolic dataflow

During stream cycle k, row i of the array gets `A[i][k]` and column j gets `B[j][k]`, one cycle later: the bytes picked from the panel beats go through an operand register (`OPERAND_STAGES = 1`) first, together with the last flag. Without it, the multipliers of the PEs in row 0 and column 0 (no skew register in front) would start from the panel read and lane multiplexer, the deepest logic in the design (see `docs/perf-log.md`, item 6). `rpu_array.sv` skews row i and column j by i and j cycles so matching values meet at PE (i, j).

Each `int8_cell` is two stages (`PE_LATENCY = 2`):

```text
product      <= a_in * b_in                (int16)
last_product <= last_in
sum          <= last_product ? 0 : sum + sign_extend(product)
accumulator  <= drain ? acc_in                                  (the shadow)
              : last_product ? sum + sign_extend(product) : accumulator
a_out <= a_in;  b_out <= b_in;  last_out <= last_in
```

The last flag enters with the last k of a tile and goes through the same skew as row i of A, so it reaches each PE with that PE's last product. The PE then moves the finished sum into the shadow register and restarts its running sum at zero, and the next tile's first product can arrive the cycle after. Outside STREAM the array gets zeros, so the running sums stay zero between tiles; the array is reset only with the RPU.

The settle time `OPERAND_STAGES + 2N - 2 + PE_LATENCY - 1` is exact: the last k reaches PE (N-1, N-1) after the operand register and 2N - 2 skew cycles, and its shadow takes the sum with the last product, one cycle later. One cycle shorter loses the last sum of PE (N-1, N-1); the tests include a case where only the last k is nonzero to catch that. During SHIFT each shadow loads the shadow of the PE above, so the bottom row `c_row` delivers C row N-1, then N-2, ..., one per cycle. Row q shifts only in the first q cycles of SHIFT (`drain_rows`): after that it holds row 0 of the tile and no row above it is left to move down, so its shadow is free for the next tile.

The settle has its own registers (`settle_valid`, `settle_count`), so one tile can settle while the tile before it shifts and stores; it hands over to SHIFT once its last sum has landed, the drain is idle and the store with its first three requantization stages is done. The next STREAM must not end before that hand-over, or its sums would overwrite shadows the settling tile still holds. So CLEAR starts the STREAM once its end, `K` cycles away, is no earlier than the hand-over: `SETTLE_LAST - settle_count` cycles away while no shift or store runs, else at most `STORE_BOUND = 1 + 4N + 3` cycles (one cycle to start the store, at most 4N beats one per cycle, then q1 to q3), which is more than the settle. The rule is exact while nothing runs: one cycle earlier trips the simulation check `a stream ends while the tile before it still settles`. The new sums are then safe with one cycle to spare: the last k leaves PE (0, 0) two cycles after the stream ends, and PE (q, j) q + j cycles later, after shift q. `STORE_BOUND` is an upper bound, not exact: the tests pass with it down to 26 of 36 at N = 8 (`docs/perf-log.md`, item 28). Before item 27 the STREAM started early only with K >= 3N; item 27 let it start once the whole drain ended in time.

## 5. File overview

- `Cargo.toml`: crate `rusting_pu`, build dependency `cc`. The optional `brain` feature adds `rusting_brain` (crates.io); the default build has no runtime dependency.
- `build.rs`: runs Verilator on the five active RTL files with `rpu_top` as top, compiles the generated C++ and the wrapper. Update its file list when RTL files change.
- `src/lib.rs`: FFI, `Rpu`, memory packing, the GEMM scheduler and the hardware tests.
- `src/quant.rs`: quantization and the reference int8 GEMM.
- `src/brain.rs` (feature `brain`): `RpuMlp`, a RustingBrain dense network with int8 weights; `predict_batch` runs the matmuls on the RPU, `predict_batches` runs batches in turn with the next one started during the last GEMM of the one before, `predict_batch_host` on the host reference, and `calibrate` fixes static output scales so the hidden layers run fused on the RPU.
- `src/main.rs`: one-tile demo. `examples/baseline.rs`: cycle counts. `examples/mnist.rs` (feature `brain`): MNIST end to end, see `docs/m1-results.md`.
- `verilated_wrapper/`: the C ABI (`rpu_new/free/reset/tick/cycles/write/read/busy/done`). Keep Verilator types out of Rust. When top-level ports change, update the wrapper and the Rust FFI together.
- `rtl/`: the five active files above. `sim/tb_tpu.sv`: Icarus smoke test. The old BF16 and integer experiments were deleted in phase 10; git history keeps them.

## 6. Int8 contract

- Inputs are int8 in [-127, 127] (symmetric quantization never produces -128; the RTL handles -128 too).
- Products are int16, accumulators int32. K = 1024 at 127 * 127 is 16,516,096, far from overflow.
- The RTL result must equal `quant::matmul_nt_i8` exactly. Use `==`, never a tolerance.
- Weights get one symmetric scale per output row (per row of B), the RustingBrain rule. Activations get one scale for the whole batch. Dequantization is host-side.
- Requantization (QUANT), per column j: `y = clamp(round((acc + bias[j]) * mult[j] / 2^shift[j]), relu ? 0 : -127, 127)`, ties rounded up (add 2^(shift-1), shift right arithmetically). `quant::Requant::apply` is the reference; the RTL must equal it exactly. `Requant::new` turns `acc * acc_scale + bias` with output scale `out_scale` into mult in [2^15, 2^16) and a shift, and the bias into the accumulator domain (`round(bias / acc_scale)`).
- `RpuMlp::calibrate` fixes each fused layer's output scale to `absmax / 127` of its output on calibration inputs (a static scale, as a TPU uses). The input of the first layer keeps a per-batch scale.

## 7. Changing N

N is one build parameter: `RPU_N`. It does not need to be a multiple of 8 or a power of 2: a beat that does not fill its last 64-bit host word is padded in memory. Tests pass at N = 4, 8, 12, 16, 24, 32 and 64. Resources grow with N^2 (see `docs/resources.md`); at N = 16 the LUT-only mapping is too large for the GW5AT-LV60, so N = 16 needs DSPs. The memory model holds 64K beats from N = 16 on (`MEM_BYTES`, N / 16 MB above N = 16), so the beat address width, not the operands that fit, is what grows. KMAX stays 1024 at every N, so at N = 64 a panel row is only 16 beats deep (`docs/perf-log.md`, item 13).

When Verilator reports width warnings after a change, size the counter and its terminal constant with the same `$clog2` width and cast explicitly. Do not disable width warnings globally.

## 8. Scheduling larger matrices

`matmul_resident` writes the A blocks (B is already resident), waits for GEMM_READY, then writes K_LEN, A_BASE, B_BASE, C_BASE (of tile 0), PANEL and TILES and sets CONTROL GEMM: 7 register writes per GEMM. It then reads C, which waits for DONE. The A blocks lie PANEL beats apart from A_BASE, the B tiles PANEL beats apart from B_BASE, and C tile (r, j) is at C_BASE + (r * nt + j) * 4N, with nt the B tile count in TILES. The sequencer in `rpu_top.sv` runs the schedule that the Rust driver ran before, with the same cycle count; the driver then wrote about 4 registers per tile (`docs/perf-log.md`, item 11):

```text
tile t = (row block r, B tile j); j runs forwards in even row blocks and
  backwards in odd ones, so the last B of a block is the first of the next
START tile 0 on the A and B banks that the last tile before (of this GEMM or the
                                      one before) did not use (loads A0 + B0;
                                      streams once K + 2N beats are in)
for each tile t:
  wait until the load of t is done and the compute has taken t
  if tile t+1 is in the same row block: START it with KEEP_A on the other
                                        B bank (loads only its B)
  else:                                 START it with KEEP_B on the other
                                        A bank (loads only A(r+1)); B bank stays
  (the load overlaps the stream of t; t+1 streams when t ends)
  (the settle, drain and store of t overlap the stream of t+1)
DONE; the host reads all C tiles
```

Layer 1 of the MLP for batch 8 (8x784 x 784x128) streams 93.21% of its busy cycles at N = 8. The overhead is the part of the first A + B load that the first stream does not overlap (K + 2N beats, about 800 cycles), a few cycles per tile (the read latency of each load and the START handshake) and the settle, drain and store of the last tile. With more than one row block, only the first block's A + B load is exposed: at a row block change only the next A loads (K beats, the same as a B preload), because the next block starts with the B tile the block before ended with. Before that order, the next block's A + B load (2K cycles) overlapped one tile (K cycles), and about K cycles per later block stayed exposed (`docs/perf-log.md`, item 9).

The first stream of a GEMM starts before its load ends (`docs/perf-log.md`, item 12). A load brings one beat per cycle; beat b arrives at most one cycle after beat b - 1, because the issue side never stops and the memory never stalls a read. With A and B, column c is complete at beat 2N(c + 1), and the stream reads it from cycle Nc after it starts, so the stream may start once Kp + N - 2 beats are in, with Kp = N * ceil(K/N) <= K + N - 1. The launch waits for K + 2N beats: 3 more than the worst case. With one panel (KEEP_A or KEEP_B) the bound is N - 2 beats and the launch waits for N + 1. The tests pass with both thresholds 3 lower and fail with 4 lower. With LOAD_BEATS > 1 a response brings LOAD_BEATS rows of one column, so column c is complete at response R(c + 1), R = PN / LOAD_BEATS for P panels. Once R <= N the load is at least as fast as the stream and column 0 decides: the bound is R - 2 responses and the launch waits for R + 1 (N + 1 for A and B at LOAD_BEATS = 2). The exposed part of the first load drops from K + 2N to about N cycles; the tests pass with these thresholds 3 lower and fail with 4 lower too (`docs/perf-log.md`, item 14). **A memory that can stall a read (DDR) breaks this**: it needs a stall-aware check or a launch at the end of the load.

A GEMM may start while the GEMM before it still streams, drains and stores its last tile (`docs/perf-log.md`, item 20). Its tile 0 loads into the banks that tile does not use, as a tile of the same GEMM would. This is needed even though the compute has taken that tile: with a short K it can wait in COMPUTE_CLEAR behind the drain and store of the tile before it, and a load into its banks would overwrite data it has not streamed yet (the test `next_gemm_leaves_the_banks_of_a_waiting_tile_alone`). `RpuMlp::predict_batches` uses this across batches: it starts the first layer of batch b + 1, writes the input of batch b + 2, starts the last layer of batch b and only then reads the output of batch b - 1. Layer 2 of batch b reads the output of layer 1 of batch b, so the host waits for that GEMM before it starts layer 2; layer 1 of batch b + 1 is queued by then, so the RPU does not idle while the host waits. The activations lie in three memory slots, `b % 3`: the C of batch b - 1 stays unread while batches b and b + 1 run, and the input of batch b + 2 goes over that of batch b - 1, which no running GEMM reads. When three slots do not fit (N = 12, batch 256) two do, and the input write waits for the first layer of batch b.

Each local B bank keeps a tag of the B panel that a GEMM tile loaded into it: K and the beats from its B_BASE to B_BASE + PANEL (`docs/perf-log.md`, item 22). A host write or a C write into those beats clears the tag; a manual load leaves none, because PANEL then holds no B extent. When tile 0 of a GEMM finds its own B_BASE and K_LEN in the tag of its B bank, it loads only A and launches after N / LOAD_BEATS + 1 beats instead of K + 2N. In the MLP this hits for layer 1 of every batch but the first: with an even row block count layer 1 ends on its B tile 0, layer 2 with one B tile runs on the other bank, and layer 1 of the next batch starts on the bank that still holds its B tile 0. With two or more B tiles in layer 2 (N = 8) the bank is overwritten and nothing hits.

K must fit in one panel (K <= KMAX). Partial sums over K are not split across jobs.

## 9. Common problems

- `Invalid module instantiation` near an instance name: the name is a SystemVerilog keyword. Use `pe_cell`, not `cell`.
- Wrong results only for some K or N: check the settle time and the beat/lane counters first. A one-cycle-short settle loses the last product.
- Verilator `SELRANGE` on a part-select of a 2-D packed array: copy the row into a flat `logic [W-1:0]` first, then part-select.
- Yosys has no slang plugin here: use packed array ports.
- Icarus cannot index packed arrays with a non-constant loop variable: use a flat bit view.
- A rebuild with a different `RPU_N` fails in generated C++: `build.rs` clears `obj_dir`; if it still fails, `cargo clean`.

## 10. Development order

1. Keep every bit-exact test passing at N = 8 and N = 16, and at READ_LATENCY 1 and 10.
2. Change one RTL behaviour at a time.
3. Add a Rust test that compares with `==` against the host reference, and check that it fails when the change is broken (mutation).
4. Run fmt, clippy, `cargo test --release`, the lint and the Icarus smoke test.
5. Record measured cycles in `docs/progress.md`. If a number contradicts the plan, record the real number and its cause.

The key invariant: the Rust packing, the register protocol and the RTL memory layout must agree. If they disagree, the RPU produces plausible but wrong matrices.
