#include "text_hd.h"

#include "../common/fnv1a.h"

#include <cstdio>
#include <cstring>

#include "image_io.h"

namespace {

uint64_t pattern_hash(const uint8_t* p) { return fnv1a_bytes(p, 32); }
}  // namespace

bool TextHD::init(const std::string& dir) {
    FILE* f = fopen((dir + "/glyphs.txt").c_str(), "r");
    if (!f) return false;
    if (!png_load(dir + "/atlas.png", atlas_w, atlas_h, atlas_rgba)) {
        fprintf(stderr, "[text] could not read %s/atlas.png\n", dir.c_str());
        fclose(f);
        return false;
    }
    glyphs_.assign(0x8000, Glyph{});
    char line[256];
    static char big[4096];
    while (fgets(big, sizeof(big), f)) {
        memcpy(line, big, sizeof(line) - 1);
        line[sizeof(line) - 1] = 0;
        if (big[0] == 'G' && big[1] == ' ') {
            Group gr;
            unsigned w, h, top, bottom, edge;
            int n = 0;
            if (sscanf(big + 2, "%u %u %x %x %x%n", &w, &h, &top, &bottom, &edge, &n) < 5 || w * h == 0 || w * h > 16)
                continue;
            gr.w = int(w), gr.h = int(h);
            gr.top = uint8_t(top), gr.bottom = uint8_t(bottom), gr.edge = uint8_t(edge);
            const char* p = big + 2 + n;
            for (unsigned k = 0; k < w * h; k++) {
                unsigned pat, slot;
                unsigned long long hash;
                int used = 0;
                if (sscanf(p, " %x:%llx:%u%n", &pat, &hash, &slot, &used) < 3) break;
                p += used;
                gr.pattern.push_back(pat);
                gr.hash.push_back(hash);
                gr.slot.push_back(uint16_t(slot));
                static const uint8_t zero[32] = {};
                gr.blank.push_back(hash == pattern_hash(zero));
            }
            if (gr.pattern.size() == w * h) groups.push_back(std::move(gr));
            continue;
        }
        unsigned pattern, slot, top, bottom, edge;
        unsigned long long hash;
        if (line[0] == '#' ||
            sscanf(line, "%x %llx %u %x %x %x", &pattern, &hash, &slot, &top, &bottom, &edge) != 6 ||
            pattern >= glyphs_.size())
            continue;
        Glyph& g = glyphs_[pattern];
        g.hash = hash;
        g.slot = uint16_t(slot);
        g.top = uint8_t(top);
        g.bottom = uint8_t(bottom);
        g.edge = uint8_t(edge);
        g.used = true;
        count_++;
    }
    fclose(f);
    if (count_ || !groups.empty())
        printf("[text] %d high-resolution text patterns, %zu groups\n", count_, groups.size());
    return count_ > 0 || !groups.empty();
}

const TextHD::Glyph* TextHD::find(uint32_t pattern, const uint8_t* vram) const {
    if (pattern >= glyphs_.size() || !glyphs_[pattern].used) return nullptr;
    const Glyph& g = glyphs_[pattern];
    return pattern_hash(vram + pattern * 32) == g.hash ? &g : nullptr;
}
