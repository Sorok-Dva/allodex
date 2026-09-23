// ImHex pattern by Paulus (reverse engineering of the Allods Online terrain formats), kept as reference.
#pragma description Nival/Heroes V terrain splat map ("*_SplatMap_N.(Texture).bin")
#pragma endian little
#pragma pattern_limit 1000000
#pragma array_limit  1000000

/*
 * ============================================================================
 *  3_3_SplatMap_<N>.(Texture).bin  -- terrain layer blend weights
 * ============================================================================
 *
 *  CONTAINER
 *  ---------
 *  The .bin is a single raw zlib stream (starts 78 9C). Decompressed it is the
 *  engine's generic texture blob, shared by every *.(Texture).bin (lightmaps,
 *  the `layers` atlas, and even 3_3_terrainDump.bin use it):
 *
 *      repeat:
 *          u32 mipsLeft        // levels still to come after this one
 *          u32 dataSize        // byte size of this level
 *          u8  data[dataSize]
 *      until mipsLeft == 0
 *
 *  Levels are stored SMALLEST FIRST, so the last block (mipsLeft == 0) is the
 *  full-resolution image and level dimensions are (width >> mipsLeft).
 *  Splat maps declare mipsNumber=1 in the .xdb, so there is exactly one block:
 *  8-byte header + 256*256*2 = 131080 bytes total.
 *
 *  PIXEL FORMAT
 *  ------------
 *  <type>C565</type>, 256x256, uncompressed 16-bit R5G6B5, row-major, 2 bytes
 *  per texel, no padding. (SplatMap_1/2 set <alphaTex>true</alphaTex> in the
 *  .xdb but there is no alpha channel in the data -- the flag is meaningless
 *  here.)
 *
 *  The three channels are BLEND WEIGHTS, not colours:
 *      R/31  -> weight of material.tex0
 *      G/63  -> weight of material.tex1
 *      B/31  -> weight of material.tex2
 *  Verified: wherever a material sets tex1 = 255 (unused) the G channel is
 *  exactly 0 over every texel it owns, likewise tex2 <-> B (0 counter-examples
 *  in 90k samples). Per texel R/31 + G/63 + B/31 == 1.0 for a base pass, or
 *  0..1 for an `additive` pass (weight of the extra decal layer).
 *
 *  IT IS AN ATLAS OF 8x8 TILES, NOT A MAP-SPACE IMAGE
 *  --------------------------------------------------
 *  This is the important part: the texture is NOT indexed by world position.
 *  It is a 32x32 grid of 8x8-texel tiles, one tile per terrain draw call
 *  (per TerrainSubPatch.materials[] entry -- see terrain.hexpat):
 *
 *      MaterialLink.material -> TerrainMaterial
 *          .txIndex          -> which SplatMap_N file       (0, 1 or 2)
 *          .tex0/.tex1/.tex2 -> layer indices into TerrainPackInfo.layers
 *                               (255 = channel unused)
 *      MaterialLink.x        -> tile ROW    (v = x * 8)
 *      MaterialLink.y        -> tile COLUMN (u = y * 8)
 *
 *  so the tile's texels live at  u = y*8 + j,  v = x*8 + i,  i,j in 0..7.
 *
 *  Tiles are handed out by a linear allocator in draw order: SplatMap_0 takes
 *  patches 0..45 (all 1024 tiles), SplatMap_1 patches 45..108 (1024 tiles),
 *  SplatMap_2 patches 108..125 (226 tiles, the rest of the file is zero).
 *  Patches 0..62 are the top surface and 63..125 the underside, which is why
 *  map 0 only ever appears on the top mesh and map 2 only on the underside.
 *
 *  IN-TILE ORIENTATION  (i = tile row, j = tile column)
 *  ----------------------------------------------------
 *      i  <->  subpatch-local world X   (the slow axis of gridIdx: worldX = x*8 + gridIdx/9)
 *      j  <->  subpatch-local world Y   (the fast axis:            worldY = y*8 + gridIdx%9)
 *
 *  The 8 samples span the patch edge-to-edge INCLUSIVE, i.e. sample i sits at
 *  local offset i * 8/7 units, so the two boundary samples are duplicated
 *  between neighbouring tiles. Measured over ~18k boundary samples:
 *      X-neighbour: A.row[7] == B.row[0]   (mean |delta| 0.00013)
 *      Y-neighbour: A.col[7] == B.col[0]   (mean |delta| 0.00017)
 *      every other pairing: mean |delta| ~0.9  (uncorrelated)
 *  A shader therefore samples the tile with a half-texel inset:
 *      uv = (tileOrigin + 0.5 + 7 * localFrac) / 256
 *
 *  USAGE
 *  -----
 *  Open the .bin directly: the zlib stream is unwrapped into the "splatmap"
 *  section (hex::dec::zlib_decompress, ImHex >= 1.30, GUI only). To parse an
 *  already-decompressed dump instead, comment out SPLAT_ZLIB_COMPRESSED at the
 *  bottom of this file.
 *
 *  Both paths were checked against 3_3_SplatMap_0 with `imhex --pl run/format`.
 */

#include <std/core.pat>
#include <std/io.pat>
#include <std/mem.pat>
#include <std/string.pat>
#include <std/sys.pat>

// From the companion .xdb (<width>/<height>). Change these for a map that
// isn't 256x256; everything else follows.
u32 WIDTH  = 256;
u32 HEIGHT = 256;

u32 TILE     = 8;                // tile edge, in texels
u32 PITCH    = WIDTH * 2;        // bytes per texel row
u32 DATA_OFF = 8;                // texels start after the level header
u32 TILE_COLS = WIDTH  / TILE;   // 32
u32 TILE_ROWS = HEIGHT / TILE;   // 32

// ---------------------------------------------------------------------------
// Texels
// ---------------------------------------------------------------------------

fn splat_weight(u16 v) {
    u32 r = (v >> 11) & 0x1F;
    u32 g = (v >>  5) & 0x3F;
    u32 b =  v        & 0x1F;
    return std::format("tex0 {:5.1f}%  tex1 {:5.1f}%  tex2 {:5.1f}%   [{:02}/{:02}/{:02}]",
                       r * 100.0 / 31.0, g * 100.0 / 63.0, b * 100.0 / 31.0, r, g, b);
};

using Texel = u16 [[format("splat_weight")]];

struct Scanline {
    Texel texel[WIDTH];
};

struct SplatImage {
    Scanline row[HEIGHT];
};

// ---------------------------------------------------------------------------
// File
// ---------------------------------------------------------------------------

struct SplatMapFile {
    u32 mipsLeft  [[comment("levels remaining after this one; splat maps have a single level -> 0")]];
    u32 dataSize  [[comment("bytes of texel data; WIDTH * HEIGHT * 2")]];

    std::assert(mipsLeft == 0, "not a single-level texture -- see the mip chain note at the top");
    std::assert(dataSize == WIDTH * HEIGHT * 2, "dataSize does not match WIDTH*HEIGHT*2 -- fix WIDTH/HEIGHT from the .xdb");

    SplatImage image;
};

// ---------------------------------------------------------------------------
// Tile view: the 8x8 block owned by one TerrainSubPatch draw call.
// Place one with   SplatTile t @ tile_addr(link.x, link.y) in splatmap;
// ---------------------------------------------------------------------------

fn tile_addr(u32 tileRow, u32 tileCol) {
    return DATA_OFF + tileRow * TILE * PITCH + tileCol * TILE * 2;
};

struct TileRow {
    Texel localY[8] [[comment("j -> subpatch-local world Y, edge to edge (j * 8/7 units)")]];
};

struct SplatTile {
    u64 origin = $;
    TileRow localX0 @ origin + 0 * PITCH;
    TileRow localX1 @ origin + 1 * PITCH;
    TileRow localX2 @ origin + 2 * PITCH;
    TileRow localX3 @ origin + 3 * PITCH;
    TileRow localX4 @ origin + 4 * PITCH;
    TileRow localX5 @ origin + 5 * PITCH;
    TileRow localX6 @ origin + 6 * PITCH;
    TileRow localX7 @ origin + 7 * PITCH;
};

// ---------------------------------------------------------------------------
// Placement
//
// The file is a raw zlib stream, so it is unpacked into the "splatmap" section
// first. Comment the #define out if you are opening an already-decompressed
// dump instead.
// ---------------------------------------------------------------------------

#define SPLAT_ZLIB_COMPRESSED

#ifdef SPLAT_ZLIB_COMPRESSED

    #include <hex/dec.pat>   // ImHex >= 1.30, GUI only (not available in the CLI)

    u8 zlibStream[std::mem::size()] @ 0x00 [[hidden]];
    std::mem::Section splatmap = std::mem::create_section("splatmap");
    hex::dec::zlib_decompress(zlibStream, splatmap);

    SplatMapFile splat @ 0x00 in splatmap;

    // Example: the tile of the first draw call (MaterialLink x = 0, y = 0).
    SplatTile tile_0_0 @ tile_addr(0, 0) in splatmap;

#endif

#ifndef SPLAT_ZLIB_COMPRESSED

    SplatMapFile splat @ 0x00;
    SplatTile tile_0_0 @ tile_addr(0, 0);

#endif
