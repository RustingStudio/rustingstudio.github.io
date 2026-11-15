---
title: "Shader packs"
project: "engine"
kind: "docs"
group: "Guides"
order: 24
description: "A shader pack is a folder of GLSL hook files and a pack.json manifest that restyles a whole game at once: every surface, the shadows, the sky, clouds, fog, particles, the final image, and full-screen composite passes over the HDR image. Players pick a pack and a Low/Medium/High/Ultra preset in a settings menu; the game reads the same list through GameScene."
source: "https://github.com/RustingStudio/RustingEngine/blob/main/docs/shader-packs.md"
---
A shader pack is a folder of GLSL hook files and a `pack.json` manifest
that restyles a whole game at once: every surface, the shadows, the sky,
clouds, fog, particles, the final image, and full-screen composite passes
over the HDR image. Players pick a pack and a Low/Medium/High/Ultra preset
in a settings menu; the game reads the same list through `GameScene`.

Packs are **GLSL 450, not WGSL**. The engine compiles them while the game
runs, so **`glslc` (from the Vulkan SDK or the `shaderc` package) must be
on `PATH` at runtime**, or named by the `RUSTING_GLSLC` environment
variable. A machine without it falls back to the built-in shading and
shows the error banner.

## Where packs live

| Id | Folder |
| --- | --- |
| `""` | the built-in shading (no pack) |
| `<id>` | `<project>/assets/shaderpacks/<id>/`, shipped with the game |
| `user/<folder>` | `shaderpacks/<folder>/` in the user data folder, installed by the player |

`project.json` may name the default: `"shader_pack": "tiny"`. The game
starts with it, and a pack that fails falls back to it.

```rust
use rusting_engine::prelude::*;

fn update(scene: &mut GameScene<'_>, _time: &FrameTime) {
    if scene.pressed("next_pack") {
        let packs = scene.shader_packs();
        let active = scene.active_shader_pack().id;
        let at = packs.iter().position(|p| p.id == active).unwrap_or(0);
        let next = &packs[(at + 1) % packs.len()];
        if let Err(error) = scene.set_shader_pack(&next.id) {
            eprintln!("{error}");
        }
    }
}
```

| Call | Does |
| --- | --- |
| `shader_packs()` | every pack with its name, options and presets; built-in first |
| `active_shader_pack()` | the active pack's info |
| `set_shader_pack(id)` | switches pack at its `default_preset`; errors keep the current one |
| `shader_preset()`, `set_shader_preset(name)` | `Low`, `Medium`, `High`, `Ultra`, or `Custom` |
| `shader_option(id)`, `set_shader_option(id, value)` | one option, as `PackOptionValue::Bool`, `Enum` or `Slider` |
| `shader_pack_value(name)` | a `values` entry of the active pack, else of the project default |
| `shader_pack_revision()` | grows on every switch, reload, preset or option change |
| `reload_shader_pack()` | reads the files again, as F3+T does |
| `shader_pack_error()` | the last error as `file:line: message` |
| `set_shader_world(ShaderWorld { .. })` | time of day, sun, moon, weather and eye state for the `frame` block |
| `set_composite_enabled(name, on)`, `composite_enabled(name)` | turns one composite pass off or on |

F3+T reloads the active pack. Debug builds also check its files every half
second and reload when one changes.

## pack.json

```json
{
  "format": 1,
  "name": "Tiny",
  "author": "You",
  "version": "1.0",
  "description": "Shown in the menu.",
  "include": ["common.glsl"],
  "programs": {
    "terrain": { "vertex": "sway.glsl", "fragment": "blocks.glsl", "shadow": "sway.glsl" },
    "sky": { "fragment": "sky.glsl" },
    "final": { "fragment": "final.glsl" }
  },
  "composite": [
    { "name": "bloom_prep", "fragment": "half.glsl", "scale": 0.5 },
    { "name": "grade", "fragment": "grade.glsl", "scale": 1 }
  ],
  "textures": {},
  "options": [],
  "presets": { "Low": {}, "Medium": {}, "High": {}, "Ultra": {} },
  "default_preset": "High",
  "values": { "sway": [0.1] }
}
```

Every key but `format`, `name` and `presets` may be left out.

**Textures.** `textures` maps lower_snake_case names to PNG or JPEG files
inside the pack, for example `"textures": {"moon": "textures/moon.jpg"}`.
The engine stacks them top to bottom into one sRGB atlas with mipmaps (at
most 8 images and 8192 pixels on a side) and binds it to the surface and
sky hooks as `pack_textures`. Each image's rectangle in the atlas is the
constant `PACK_TEXTURE_<NAME>`; read it with
`pack_texture(PACK_TEXTURE_MOON, uv)` or `pack_texture_lod(rect, uv, lod)`,
`uv` 0..1 across the image with the top left first. Both are defined when
`RUSTING_PACK_TEXTURES` is; other hooks (fog, clouds, composite, final)
do not see the atlas. Editing an image reloads the pack.

**Programs.** `terrain`, `water`, `translucent`, `entities` and `hand`
draw surfaces and take `vertex`, `fragment` (a surface hook) and `shadow`.
`particles`, `sky`, `clouds`, `fog` and `final` take only `fragment`;
`clouds` also takes `scale` (1, 0.5 or 0.25, below). A
material picks its program with `MaterialAsset.program`; empty means
`entities` for `Opaque` and `Mask` materials and `translucent` for
`Blend`. A material's own `shader`, and a scene's `SkyShader`, `FogShader`,
`PostShader` or `ParticleShader`, always win over the pack.

**Options.** Each option has `id` (lowercase), `type`, `label`, `default`
and `cost` (`low`, `medium`, `high`, for a menu to show):

| `type` | Extra keys | GLSL sees |
| --- | --- | --- |
| `bool` | | `#define OPT_<ID> 1` or `0` |
| `enum` | `values: ["warm", "cold"]` | `OPT_<ID>_WARM 0`, `OPT_<ID>_COLD 1`, and `OPT_<ID>` the current index |
| `slider` | `min`, `max`, `step` | `#define OPT_<ID> 0.75` |

Any option may also have `hint`, a text of at most 120 characters for a
menu to show beside it (`PackOption.hint`, empty when left out). A longer
hint fails with `SHADER_PACK_INVALID`.

**Presets** must define all four of `Low`, `Medium`, `High` and `Ultra`,
each a map of option id to value; missing options take their default.

**Values** are named numbers: `"tint": [1.0, 0.9, 0.7]` becomes
`const vec3 PACK_TINT`. One number is a `float`, two to four a `vec`, more
a `float[]`. Game code reads them with `shader_pack_value`.

A malformed manifest or a hook without its header fails with
`SHADER_PACK_INVALID` and the file and line; a hook that does not compile
fails with `SHADER_PACK_COMPILE` and glslc's file and line.

## What every hook sees

Before each hook's body the engine adds, in order:

1. the `frame` uniform block (below);
2. `RUSTING_ID_MASK` and the `RUSTING_FLAG_*` vertex flags;
3. the `OPT_*` defines and `PACK_*` constants;
4. the `include` files, in order.

Mesh vertices carry a `data` word: bits 0-15 are an id (a block id),
and the flags are `RUSTING_FLAG_FOLIAGE` (bit 16), `LEAVES` (17), `WATER`
(18), `LAVA` (19), `EMISSIVE` (20), `GLASS` (21) and `METAL` (22).

The `frame` block (std140) holds `view`, `projection`, `view_projection`,
`inverse_view`, `inverse_projection`, the three `previous_*` matrices,
`camera_position` (w near), `previous_camera_position` (w far),
`sun_direction` (toward the sun, w lux), `moon_direction`, `sun_color`,
`time` (seconds, world time, day fraction, moon phase), `screen` (width,
height, 1/width, 1/height), `weather` (rain, thunder, temperature,
humidity) and `eye` (underwater, eye sky light, eye block light, frame
index), then `params[32]` (`vec4`; `RUSTING_FRAME_PARAMS` is defined as
32). The engine fills the camera, time and screen fields; the rest come
from `set_shader_world`. Until the game calls it, the sun is the first
directional light and the rest is 0. `ShaderWorld::params` are the game's
own values, `frame.params[i]` in GLSL; the engine never reads them, so a
game can pass wind, a storm front or a cloud seed without a new engine
field. Particle hooks have no `frame`.

`ShaderWorld::sky_hidden` (false by default) tells the engine no sky can be
seen, for example deep in a cave. While it is true the renderer skips the
pack's cloud layer and `sky_lut` draws and keeps their last images, so the
sky and environment light still read the old ones. When it turns false the
cloud layer draws once without history, so no stale clouds smear in. Set
it only when the sky is truly out of view: a sky that shows while it is
true stays frozen.

Surface `fragment` hooks and `sky`, `clouds` and `fog` hooks also see the
sky (guard with `#ifdef RUSTING_SKY_LUT`; vertex, shadow, composite,
particle and `final` hooks do not have it):

| Name | Is |
| --- | --- |
| `sky_param(i)` | the procedural sky settings: `[0]` xyz toward the sun, w cosine of the disc radius; `[1]` rgb sun colour times brightness, w haze; `[2]` rgb ground albedo, w sky mode; `[3]` cloud drift xz, cover, darkness |
| `sky_lut_at(dir)` | light from `dir`: the bound environment map (the pack's `sky_lut`, the sky bake or the scene's environment texture) times its intensity, else the ambient hemisphere |
| `sky_lut_lod(dir, lod)` | the same at mip `lod`, for blurry reflections |
| `sky_radiance`, `sky_sunlight`, `sky_cloud_density`, `sky_cloud_color` and the rest of the engine's `sky.glsl` | the built-in sky model |

Surface `fragment` hooks also have `RUSTING_WATER_DEPTH` and two globals the
built-in water sets before the hook runs, -1 elsewhere:
`rusting_water_view_depth` (metres of water the view ray crosses to the
surface behind) and `rusting_water_floor_depth` (height of the water above
that surface).

## Hooks

Each file starts with `#rusting <hook> 1`.

**`vertex`** (surface programs' `vertex` and `shadow`):

```glsl
void vertex(VertexInput i, inout VertexOutput o);
```

`VertexInput` has `position`, `world_position`, `normal`, `uv`, `color`,
`block_id`, `flags` and `time`; `o` starts as the built-in result and holds
`world_position`, `normal` and `color`. The shadow pass uses the
program's `shadow` hook, else its `vertex` hook, else the built-in, so
swaying leaves cast swaying shadows. Materials with a `Mask` alpha mode cast
alpha-tested shadows: the shadow pass drops texels where base colour
texture alpha times material and vertex alpha (after the hook) is below
`alpha_cutoff`, at the same uv as the main pass, so leaf atlases cast
dappled shadows. `Blend` materials cast no shadow, and `Opaque` ones stay
depth-only.

**`surface`**, **`sky`**, **`fog`**, **`particle`**, **`post`**: the
material and scene shaders from `rusting docs show guide/surface-shaders`.
In a pack, `SurfaceInput` also has `block_id` and `flags`. A surface hook
can set `s.subsurface` (rgb tint, a thickness in metres) to let the sun
through leaves and grass; guard it with `#ifdef RUSTING_SURFACE_SUBSURFACE`.
A pack's `sky`
hook replaces the background as a scene `SkyShader` does, so in a scene
without a sky `color` starts black.

**`clouds`** draws over the sky shader's result:

```glsl
void clouds(SkyInput i, inout vec3 color);
```

**Cloud layer.** With `"clouds": {"fragment": "clouds.glsl", "scale":
0.5}` (or 0.25) the same file is compiled with `#define RUSTING_CLOUD_LAYER
1` and runs once per frame as its own full-screen pass at that fraction of
the screen (rounded up), so expensive ray-marched clouds cost a half or a
sixteenth of the pixels. It defines `cloud_layer` instead of `clouds`:

```glsl
struct CloudLayerInput { vec3 direction; float time; vec2 uv; vec2 texel; };
void cloud_layer(CloudLayerInput i, inout vec4 layer);
vec4 cloud_layer_history(vec2 uv);          // last frame's layer, bilinear
vec2 cloud_layer_previous_uv(vec3 direction); // where `direction` was last frame
```

`direction` is the world-space view ray, `time` the same seconds as
`SkyInput.time`, `uv` the layer pixel's centre (0 to 1, top left 0) and
`texel` one layer pixel. `layer` starts as `(0, 0, 0, 1)`: `rgb` is light
the clouds add and `a` how much sky shows through. The sky shader then
does `sky = sky * layer.a + layer.rgb` with the layer sampled bilinearly
at the screen position, after the `sky` hook and before fog. History is
two ping-pong images, cleared to `(0, 0, 0, 1)` when made or resized;
`cloud_layer_previous_uv` uses last frame's camera rotation only (clouds
are at infinity), and returns -1 when the direction was behind the camera.
The hook sees the same things as a `clouds` hook: `frame`, the pack
prelude, `RUSTING_SKY_LUT`, `sky_param`, `sky_lut_at`, `sky_lut_lod` and
`sky.glsl`. One file serves both modes:

```glsl
#rusting clouds 1
#ifdef RUSTING_CLOUD_LAYER
void cloud_layer(CloudLayerInput i, inout vec4 layer) {
    vec4 last = cloud_layer_history(cloud_layer_previous_uv(i.direction));
    // ... march, then blend with `last` for temporal smoothing
}
#else
void clouds(SkyInput i, inout vec3 color) { /* cheap inline clouds */ }
#endif
```

The layer also gets a tiling 3D noise texture for volumetric clouds
(Nubis style), with `#define RUSTING_CLOUD_NOISE 1`:

```glsl
vec4 cloud_noise(vec3 p); // 128^3 RGBA8, trilinear, repeats every 1.0 of p
```

`r` is Perlin-Worley (a 4-octave Perlin fbm pushed out by inverted
Worley, 4 cells per tile) for the base shape, and `g`, `b`, `a` are
inverted Worley fbm at 4, 8 and 16 cells per tile for carving and
detail erosion. It is made once on the CPU at start (about 0.4 s on all
cores) and uploaded once. Guard its use with `#ifdef
RUSTING_CLOUD_NOISE` if the pack also runs on older engines.

GPU timing shows the pass as `Clouds`, after `SkyLut` and before the main
`Scene` pass. Clouds in the layer show wherever the sky does, including
screen-space reflections of it. `scale` 1 or no `scale` keeps the inline
`clouds` hook and adds no pass.

**`sky_lut`** draws the sky into a 256 x 128 equirectangular image every
frame (`u = atan(d.z, d.x) / 2pi + 0.5`, `v = acos(d.y) / pi`, mipmapped):

```glsl
struct SkyLutInput { vec3 direction; vec2 uv; float time; };
void sky_lut(SkyLutInput i, inout vec3 color);
```

`color` starts as `sky_radiance(i.direction, sky_param(0).xyz,
sky_param(1).rgb, sky_param(1).w, sky_param(2).rgb)`; the hook sees `frame`,
`sky_param` and `sky.glsl`, not `sky_lut_at`. When the scene has a
procedural sky and no environment texture, the image replaces the sky bake
as the environment map (intensity 1) that lighting, reflections and
`sky_lut_at` read. Otherwise it is not drawn. GPU timing shows it as
`SkyLut`. If it fails to build, the engine prints why and keeps the bake.

**`composite`** runs on the whole linear HDR image after the main pass and
before bloom:

```glsl
void composite(CompositeInput i, inout vec4 color);
```

`CompositeInput` has `uv`, `pixel`, `texel` and `time`; `color` starts as
`color_at(i.uv)`. Helpers: `color_at(uv)`, `depth_at(uv)`,
`view_position_at(uv)`, `world_position_at(uv)`, `normal_at(uv)`,
`history_at(uv)` (last frame's result; the engine keeps it only when a
pack file calls it), `shadow_at(world_position)` and `composite_at(k, uv)`
(the output of pass `k`). A pass with `scale` 0.5 or 0.25 renders smaller,
for later passes to read with `composite_at`. A `scale` 1 pass replaces the
image that `color_at` reads and that bloom and tone mapping take. GPU
timing shows the chain as `Composite`.

**Turning passes off.** A pass with `"when": ["rain", "glow"]` runs only
while at least one of those options is on: a bool that is true, an enum
that is not its first value, or a slider above 0. An id that is not an
option fails with `SHADER_PACK_INVALID` and the line. Game code can also
turn a pass off by name with `scene.set_composite_enabled("rain", false)`;
`composite_enabled(name)` is true until then. The setting lasts across
option, preset and pack changes, and a name the pack lacks is kept for a
later pack. A pass that is off draws nothing and costs nothing: at `scale`
1 the image passes through unchanged, and with every pass off the chain
adds no copy and `Composite` shows 0 ms. A smaller pass that is off keeps
its last contents, so a later pass that reads it with `composite_at` must
carry the same `when` (or be turned off with it).

## Cost

With no pack the engine draws exactly as before. A pack with empty hooks
draws the same pixels as no pack. A pack without `composite` adds no
passes. A `sky_lut` program adds one 256 x 128 draw and its mip chain per
frame, well under 0.1 ms. A cloud layer adds one draw at its `scale`;
with an empty hook it costs about 0.006 ms at 1920 x 1080 (`scale` 0.25),
so the price is the hook's own work on a quarter or a sixteenth of the
pixels. Its `cloud_noise` texture takes 8 MB of GPU memory. Pipelines are cached per program and pack
revision, so changing an option rebuilds only once.

Press F3 in a game window for the performance overlay: the fps line, then
`gpu` with the frame's total, then one line per GPU pass of at least
0.005 ms in frame order (`Shadow` with its cascades summed beneath it,
`SkyLut`, `Clouds`, `Scene` with `opaque`, `terrain`, `foliage` and
`sky` beneath it, `Composite`, ...). The window title keeps only the fps
line.

## When a pack fails

The engine prints the error, switches to the project's default pack (or
the built-in shading when the default is the one failing), and draws a red
banner at the top left:

```text
Shader pack tiny failed: final.glsl:4: 'tnt' : undeclared identifier (using built-in)
```

Fix the file and press F3+T, or save it in a debug build.

## Known limits

- The depth prepass that ambient occlusion reads uses the built-in vertex
  shader, so occlusion does not follow a vertex hook's sway.
- `textures` reach only the surface and sky hooks.
- `Surface.subsurface` lights only from directional lights; point and spot
  lights ignore it.
- A `Mask` program's shadow pass runs a fragment test, so it costs more
  than an opaque one's depth-only draw (about 0.03 ms on a forest at
  4096 x 4096).
- Soft shadows widen with the distance to the blocker only for the sun;
  spot and point light shadows keep a fixed 1.5-texel blur.
- The cloud layer keeps one history pair: with several cameras in a
  frame (split screen), each camera's history is another camera's layer.
  Resizing the window or reloading the pack restarts the history. The
  layer is sized from the whole render target, not each viewport.
- A cloud layer hook cannot read the scene camera's push constants
  (`camera.*`); use `frame` instead.
- The `sky_lut` image holds the sky without clouds or the sun disc, as the
  sky bake does, unless the hook adds them; the background is still drawn
  by the `sky` program.

## The tiny pack

`docs/examples/shaderpacks/tiny/` sways vertices flagged foliage and gives
the final image a sepia tone with a bool, an enum and a slider option.
Copy it to `assets/shaderpacks/tiny/` and set `"shader_pack": "tiny"` in
`project.json` to try it.
