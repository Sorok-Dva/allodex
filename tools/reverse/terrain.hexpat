// ImHex pattern by Paulus (reverse engineering of the Allods Online terrain formats), kept as reference.
#pragma array_limit 10000000000
#pragma pattern_limit 1000000000

#pragma endian little

struct Vec3 {
    float x;
    float y;
    float z;
};

struct Vec4 {
    float x;
    float y;
    float z;
    float w;
};

struct AABB {
    Vec3 center;
    Vec3 extents;
};

struct StaticVector<T> {
    u32 offset [[comment("Relative offset from this position")]];
    u32 count;
    T data[count] @ $ - 8 + offset [[comment("Data at relative offset")]];
};

struct PairUcharUchar {
    u8 first;
    u8 second;
};

struct GrassType {
    u8 grassType;
    u8 grassSubType;
    padding[2];
    StaticVector<PairUcharUchar> xy;
};

struct WaterMaterial {
    u8 isComplex;
    u8 txInd;
    u16 vbSize;
};

struct WaterElement {
    u8 x;
    u8 y;
    u8 i;
    u8 j;
};

struct TerrainOccluder {
    Vec4 xmin;
    Vec4 xmax;
    AABB aabb;
};

// One draw call: `material` textures `size` vertices starting at `offset` in
// the shared vertex buffer. x/y are NOT world coords -- they address the 8x8
// tile inside the splat map named by TerrainMaterial.txIndex (see
// splatmap.hexpat): u = y * 8, v = x * 8, tiles handed out sequentially in
// draw order across SplatMap_0 -> _1 -> _2.
struct MaterialLink {
    u16 offset;
    u16 material;
    u8 x [[comment("splat tile row    (texel v = x * 8)")]];
    u8 y [[comment("splat tile column (texel u = y * 8)")]];
};

// A subpatch covers an 8x8-unit area with vertices on a 9x9 grid (1 unit spacing).
// x/y below are GLOBAL subpatch grid coords (map = 32x32 subpatches = 256x256 units).
// size = vertex count.
//
// `data` layout (parallel arrays, NOT interleaved):
//   [size x 4 bytes]  per vertex: nx, ny, nz, gridIdx
//       - nx/ny/nz: normal, biased u8 -> (b-128)/127
//       - gridIdx (0..80): position in 9x9 grid, COLUMN-major:
//           worldX = x*8 + gridIdx / 9
//           worldY = y*8 + gridIdx % 9
//   [size x f32]      per-vertex height (worldZ) of THIS surface
//   [size x f32]      only when the vb is isComplex (12 bytes/vertex instead of
//                     8): the height of the OPPOSITE surface at the same grid
//                     position -- i.e. the underside mesh's z. Verified exact on
//                     all 4948 complex vertices. Runtime type is
//                     Terrain::ComplexVertex { float coo[2]; vec4ub nor; ... },
//                     so coo[0] = this surface, coo[1] = the other one; it lets
//                     the rim shader know the island's thickness.
//
// indices0/indices1: u8 triangle lists, local vertex indices. These are two LODs
// of the SAME area (each covers the full 8x8 subpatch): indices0 = coarse LOD
// (references only the first ~8-12 verts; vertex array is ordered coarse-first),
// indices1 = fine LOD (references all verts). Use one or the other, never both.
// MaterialLink.offset = cumulative vertex offset in the shared vertex buffer
// (vbIndex of the material selects which TerrainVertexBuffer).
struct TerrainSubPatch {
    StaticVector<u8> indices0;
    StaticVector<u8> indices1;
    StaticVector<u8> data;
    StaticVector<MaterialLink> materials;
    u16 x;
    u16 y;
    u16 size;
    u16 odd;
};

// Patches are 32x32-unit cells (8x8 grid, centers at 16,48,...,240).
// The patch list holds TWO meshes back to back: patches [0..62] = top surface,
// patches [63..125] = "down" mesh (underside of the floating island).
struct TerrainPatch {
    AABB aabb;
    StaticVector<TerrainSubPatch> patches;
};

struct TerrainVertexBuffer {
    u16 size;
    u8 isComplex;
    u8 notUsed;
};

struct TerrainWaterPatch {
    AABB aabb;
    Vec4 height;
    Vec4 speedX;
    Vec4 speedY;
    StaticVector<WaterElement> waterElements;
    u8 i;
    u8 j;
    u8 materialId;
    u8 waterId;
};

struct TerrainGrassPatch {
    AABB aabb;
    StaticVector<GrassType> grasses;
    u16 i;
    u16 j;
};

// tex0/1/2 index TerrainPackInfo.layers (255 = unused); they are blended by
// the R/G/B channels of the splat map tile respectively (R/31, G/63, B/31,
// summing to 1 for a base pass). additive = the pass is added on top.
struct TerrainMaterial {
    u8 isComplex;
    u8 isXYZTextured;
    u8 odd;
    u8 additive;
    u8 tex0 [[comment("layer blended by splat R")]];
    u8 tex1 [[comment("layer blended by splat G")]];
    u8 tex2 [[comment("layer blended by splat B")]];
    u8 vbIndex;
    u8 txIndex [[comment("which SplatMap_N texture (0-2)")]];
};

struct TerrainSetFixed {
    StaticVector<TerrainVertexBuffer> buffers;
    StaticVector<TerrainMaterial> materials;
    StaticVector<TerrainPatch> patches;
    StaticVector<TerrainOccluder> occluders;
    StaticVector<TerrainGrassPatch> grassPatches;
    StaticVector<WaterMaterial> waterMaterials;
    StaticVector<TerrainWaterPatch> waterPatches;
};

// Main entry point
TerrainSetFixed terrainSet @ 0x08;