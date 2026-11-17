---
title: "Overview"
project: "runner"
kind: "docs"
group: "Start"
order: 0
description: "Runs released Rusting models. Inference only, in Rust, on RustingBrain. No Python."
source: "https://github.com/RustingStudio/RustingRunner/blob/main/README.md"
---
Runs released Rusting models. Inference only, in Rust, on
[RustingBrain](https://github.com/RustingStudio/RustingBrain). No Python.

One model so far:

| Command | Model | Does |
|---|---|---|
| `rusting-runner 3d` | Kaze-3D-v0.1 | one image in, one mesh (GLB) out |

Kaze-3D-v0.1 here is geometry only: the GLB has positions and normals, no
texture and no colours.

## Requirements

- A Rust toolchain, 1.88 or newer.
- For the GPU build: an NVIDIA card and the CUDA toolkit; see RustingBrain's
  [INSTALL_CUDA.md](https://github.com/RustingStudio/RustingBrain/blob/main/INSTALL_CUDA.md).
  Without one it runs on the CPU.

## Build

RustingBrain is taken from the directory next to this one:

```bash
git clone https://github.com/RustingStudio/RustingBrain
git clone https://github.com/RustingStudio/RustingRunner
cd RustingRunner
cargo build --release                  # CPU
cargo build --release --features cuda  # NVIDIA
```

The binary is `target/release/rusting-runner`.

## Weights

1. Kaze-3D-v0.1 from Hugging Face,
   [`rusting-studio/Kaze-3D-v0.1`](https://huggingface.co/rusting-studio/Kaze-3D-v0.1).
   The runner reads `flow.safetensors` and `vae.safetensors` from that
   directory; the settings in `configs/` are also stored inside the two files.
2. The image encoder, CLIP ViT-B/16, is not part of that repository. Fetch
   `model.safetensors` from
   [`openai/clip-vit-base-patch16`](https://huggingface.co/openai/clip-vit-base-patch16)
   and put it at `Kaze-3D-v0.1/clip-vit-base-patch16/model.safetensors`, or
   name it with `--clip`.
   The file is not on that repository's main branch; it is in its
   safetensors pull request:

   ```bash
   hf download openai/clip-vit-base-patch16 model.safetensors --revision refs/pr/17 \
       --local-dir Kaze-3D-v0.1/clip-vit-base-patch16
   ```

```
Kaze-3D-v0.1/
  flow.safetensors
  vae.safetensors
  configs/flow-100m.json
  configs/vae-32m.json
  clip-vit-base-patch16/model.safetensors
```

## Run

```bash
rusting-runner 3d --weights Kaze-3D-v0.1 --image my-object.png --out my-object.glb
```

| Flag | Default | |
|---|---|---|
| `--weights` | | the release directory above |
| `--image` | | the input image, PNG or JPEG |
| `--out` | `out.glb` | the mesh |
| `--clip` | `<weights>/clip-vit-base-patch16/model.safetensors` | the CLIP checkpoint |
| `--seed` | 0 | the noise the shape is sampled from |
| `--steps` | 28 | sampling steps |
| `--guidance` | 4 | classifier-free guidance scale |
| `--resolution` | 128 | the marching grid along one axis |
| `--faces` | 50000 | the face budget the mesh is simplified to; 0 keeps every face |
| `--cuda` | | the NVIDIA device, e.g. `--cuda 0`; needs the `cuda` build |

Steps 28, guidance 4 and resolution 128 are the settings the model was
evaluated with.

### Input

One 512×512 RGBA image. The model was trained on renders of single objects on
a plain background. Photos, scenes and several objects in one image are
outside what it has seen.

The alpha is composited over white, and the image is resized to 224×224
without cropping, so an image that is not square is stretched. An image
without alpha is used as it is; give it a white background.

### Output

A binary glTF (`.glb`) with one mesh inside the cube ±1.05: positions, normals
and triangles, with a plain white material.

The shape is the same every time for the same image, seed and settings on the
same device: with `--faces 0` the file is byte for byte the same. The
simplification to `--faces` chooses between equally cheap edges in an order
that changes from run to run, so two simplified meshes of one shape have the
same number of faces but not the same vertices.

On an NVIDIA card the image encoder computes in half precision, so the CPU and
the card do not give the same mesh for the same seed.

### Time

One generation with the defaults took 46 seconds on the CPU alone: a Ryzen 5
7600X (6 cores), release build, while the machine was running other jobs. Not
measured on a card here.

## Check

```bash
cargo test --release
```

marches a sphere's field into a mesh, simplifies it, writes the GLB and reads
it back; it needs no weights. With the weights in place,

```bash
KAZE_WEIGHTS=Kaze-3D-v0.1 KAZE_IMAGE=my-object.png cargo test --release -- --ignored
```

runs the whole pipeline once.

## Licences

- This code: see [LICENSE.md](https://github.com/RustingStudio/RustingRunner/blob/main/LICENSE.md).
- The Kaze-3D-v0.1 weights: Apache-2.0.
- The CLIP weights: MIT, from OpenAI; not redistributed here.
