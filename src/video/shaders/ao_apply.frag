#version 450
// Ambient occlusion, second step: the raw occlusion (half resolution, each
// texel taken at the top left pixel of its 2x2 block) is smoothed over the
// 3x3 texels around, without mixing across depth edges, and multiplied into
// the image of the game world (the colour target blends with dst * src).
#extension GL_GOOGLE_include_directive : require
#include "ao_common.glsl"

layout(location = 0) out vec4 out_factor;

void main() {
    vec2 frag = gl_FragCoord.xy;
    float d = texelFetch(depth_tex, ivec2(frag), 0).r;
    if (d <= 0.0) {
        out_factor = vec4(1.0);
        return;
    }
    float z = AO_NEAR / d;
    ivec2 size = textureSize(ao_tex, 0), full = textureSize(depth_tex, 0);
    ivec2 centre = ivec2(frag) / 2;
    float sum = 0.0, weight = 0.0;
    for (int y = -1; y <= 1; y++)
        for (int x = -1; x <= 1; x++) {
            ivec2 q = clamp(centre + ivec2(x, y), ivec2(0), size - 1);
            float dq = texelFetch(depth_tex, min(q * 2, full - 1), 0).r;   // where that texel was taken
            if (dq <= 0.0) continue;
            float w = exp(-abs(AO_NEAR / dq - z) / (0.03 * z));
            sum += texelFetch(ao_tex, q, 0).r * w;
            weight += w;
        }
    float open = weight > 0.0 ? sum / weight : 1.0;
    out_factor = vec4(vec3(mix(1.0, open, ao.params.y)), 1.0);
}
