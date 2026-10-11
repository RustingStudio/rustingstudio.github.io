// Copy and measured stats from design-system/components/bundle.js (PROJECTS).
export type ProjectId = 'engine' | 'brain' | 'shader' | 'strata';
export type Theme = 'copper' | 'verdigris' | 'cobalt' | 'amethyst';

export interface Project {
  id: ProjectId; theme: Theme; scene: ProjectId; index: string;
  name: string; stem: string; kicker: string; short: string; lede: string;
  stats: { value: string; unit?: string; label: string }[]; statsFoot: string;
  tags: string[];
  code: { lang: 'rust' | 'bash'; title: string; text: string; hl: number[] };
  repo: string;
}

export const GH = 'https://github.com/RustingStudio/';

export const PROJECTS: Record<ProjectId, Project> = {
  engine: {
    id: 'engine', theme: 'copper', scene: 'engine', index: '01',
    name: 'RustingEngine', stem: 'Engine',
    kicker: 'Game engine / Vulkan / Physics',
    short: 'A Rust game engine with Vulkan rendering, an editor, and hybrid CPU/GPU physics.',
    lede: 'A GPU-first game engine for physics-heavy scenes. Vulkan rendering, a Blender-style editor, and hybrid physics — you decide what the CPU owns and what the GPU simulates.',
    stats: [
      { value: '2,191', unit: 'FPS', label: '10,000 GPU-simulated cubes' },
      { value: '7', label: 'CPU joint types, hinge to six-axis' },
      { value: '2', label: 'Platforms: Linux and Windows' },
    ],
    statsFoot: 'Measured on an RTX 3060.',
    tags: ['PBR + shadows', 'GPU frustum culling', 'Deterministic scenarios', 'rusting CLI'],
    code: { lang: 'rust', title: 'src/game.rs', text: 'use rusting_engine::prelude::*;\n\nfn update(scene: &mut GameScene<\'_>, time: &FrameTime) {\n    scene.object("Planet").rotate_y(0.2 * time.delta_seconds());\n}\n\nrusting_game!(update);', hl: [4] },
    repo: GH + 'RustingEngine',
  },
  brain: {
    id: 'brain', theme: 'verdigris', scene: 'brain', index: '02',
    name: 'RustingBrain', stem: 'Brain',
    kicker: 'Deep learning / CUDA / Metal',
    short: 'A deep-learning library in Rust, from small networks to transformer models.',
    lede: 'Train anything from an XOR network to a 300M-parameter transformer on one desktop GPU. No Python, no C++ build step — CUDA kernels compile at startup.',
    stats: [
      { value: '300M', label: 'Parameter LMs on a single GPU' },
      { value: '3', label: 'Backends: CPU, CUDA, Metal' },
      { value: '16', label: 'Tutorial chapters, zero to LM' },
    ],
    statsFoot: 'Matches or beats PyTorch on most RTX 3060 configurations.',
    tags: ['Flash attention', 'Mixture of Experts', 'LoRA fine-tuning', 'BF16'],
    code: { lang: 'rust', title: 'examples/xor.rs', text: 'let mut model = Network::builder()\n    .input_size(2)\n    .dense(8, Activation::Tanh)\n    .dense(1, Activation::Sigmoid)\n    .loss(Loss::BinaryCrossEntropy)\n    .optimizer(Optimizer::adam(0.05))\n    .build();', hl: [3, 4] },
    repo: GH + 'RustingBrain',
  },
  shader: {
    id: 'shader', theme: 'cobalt', scene: 'shader', index: '03',
    name: 'RustingShader', stem: 'Shader',
    kicker: 'Shader pack / GLSL / Iris',
    short: 'A cinematic Iris shader pack for Minecraft, with a black hole in the End.',
    lede: 'A cinematic shader pack for Minecraft Java Edition. Soft PCSS shadows, deferred water with caustics, volumetric clouds and light — and a gravitationally lensed black hole in the End.',
    stats: [
      { value: 'PCSS', label: 'Soft shadows, deferred lighting' },
      { value: '3', label: 'Dimensions, each lit its own way' },
      { value: 'GL 3', label: 'Runs through Iris on OpenGL 3.x' },
    ],
    statsFoot: 'Developed on an RTX 3060.',
    tags: ['Volumetric clouds', 'Water caustics', 'Lensed black hole', 'Bloom + auto-exposure'],
    code: { lang: 'bash', title: 'install', text: '# 1. Install Iris for Minecraft Java Edition\n# 2. Download the latest RustingShader release\n$ mv RustingShader.zip ~/.minecraft/shaderpacks/\n# 3. Video Settings → Shader Packs → RustingShader', hl: [3] },
    repo: GH + 'RustingShader',
  },
  strata: {
    id: 'strata', theme: 'amethyst', scene: 'strata', index: '04',
    name: 'RustingStrata', stem: 'Strata',
    kicker: 'LLM inference / CUDA / Qwen',
    short: 'A pure-Rust inference engine for Qwen3.5/3.6 MoE models that splits experts between GPU and CPU.',
    lede: 'Run Qwen3.6-35B-A3B on a 12 GB GPU faster than llama.cpp. Experts that do not fit in VRAM run on the CPU alongside the GPU, and their placement adapts to the routing it sees. No C++, no ggml — CUDA kernels compile at run time.',
    stats: [
      { value: '2,093', label: 'tok/s prefill at 4K (llama.cpp: 1,017)' },
      { value: '101', label: 'tok/s decode (llama.cpp: 65.8)' },
      { value: '111', label: 'tok/s decode with MTP drafts' },
    ],
    statsFoot: 'Qwen3.6-35B-A3B Q2_K_XL (11.7 GiB) on an RTX 3060 12 GB + Ryzen 5 7600X.',
    tags: ['Hybrid CPU/GPU MoE', 'Adaptive expert placement', 'MTP speculative decoding', 'OpenAI-compatible server'],
    code: { lang: 'bash', title: 'run', text: '$ cargo build --release\n$ strata calibrate --model $M\n$ strata chat --model $M --gpu\n$ strata serve --model $M --gpu --addr 127.0.0.1:8080', hl: [3] },
    repo: GH + 'RustingStrata',
  },
};

export const IDS: ProjectId[] = ['engine', 'brain', 'shader', 'strata'];

/** RustingScience: posts on the site, written in their own repository. Not a project, so no theme of its own. */
export const SCIENCE = {
  name: 'RustingScience', stem: 'Science', sub: 'Posts · research notes',
  lede: 'Benchmarks, experiments and research notes on Rust, GPUs and machine learning. Every number comes with the script and the hardware that produced it.',
  repo: GH + 'RustingScience',
};

/** Prefix a site path with the configured base ("/engine/docs/" → "/RustingStudioWebSite/engine/docs/"). */
export const u = (p: string) => import.meta.env.BASE_URL.replace(/\/$/, '') + '/' + p.replace(/^\//, '');
