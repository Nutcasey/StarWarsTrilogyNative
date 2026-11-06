#include "rom_zip.h"

#include <algorithm>
#include <cstdio>
#include <map>
#include <utility>

#include "miniz.h"

namespace {

struct Chip {
    const char* name;
    uint32_t crc;
    uint32_t offset;
};
struct Region {
    std::vector<uint8_t> RomSet::*field;
    int stride, chunk;
    bool swap;
    std::vector<Chip> chips;
};

// The same table as tools/romtool.py
const std::vector<Region>& regions() {
    static const std::vector<Region> r = {
        {&RomSet::crom, 8, 2, true,
         {{"epr-21382a.20", 0x69BAF117, 0x0000000}, {"epr-21381a.19", 0x2DD34E28, 0x0000002}, {"epr-21380a.18", 0x780FB4E7, 0x0000004}, {"epr-21379a.17", 0x24DC1555, 0x0000006}}},
        {&RomSet::banked_crom, 8, 2, true,
         {{"mpr-21342.04", 0x339525CE, 0x0000000}, {"mpr-21341.03", 0xB2A269E4, 0x0000002}, {"mpr-21340.02", 0xAD36040E, 0x0000004}, {"mpr-21339.01", 0xC0CE5037, 0x0000006}, {"mpr-21346.08", 0xC8733594, 0x1000000}, {"mpr-21345.07", 0x6C183A21, 0x1000002}, {"mpr-21344.06", 0x87453D76, 0x1000004}, {"mpr-21343.05", 0x12552D07, 0x1000006}, {"mpr-21350.12", 0x486195E7, 0x2000000}, {"mpr-21349.11", 0x3D39454B, 0x2000002}, {"mpr-21348.10", 0x1F7CC5F5, 0x2000004}, {"mpr-21347.09", 0xECB6B934, 0x2000006}}},
        {&RomSet::vrom, 32, 2, false,
         {{"mpr-21359.26", 0x34EF4122, 0x0000000}, {"mpr-21360.27", 0x2882B95E, 0x0000002}, {"mpr-21361.28", 0x9B61C3C1, 0x0000004}, {"mpr-21362.29", 0x01A92169, 0x0000006}, {"mpr-21363.30", 0xE7D18FED, 0x0000008}, {"mpr-21364.31", 0xCB6A5468, 0x000000A}, {"mpr-21365.32", 0xAD5449D8, 0x000000C}, {"mpr-21366.33", 0xDEFB6B95, 0x000000E}, {"mpr-21367.34", 0xDFD51029, 0x0000010}, {"mpr-21368.35", 0xAE90FD21, 0x0000012}, {"mpr-21369.36", 0xBF17EEB4, 0x0000014}, {"mpr-21370.37", 0x2321592A, 0x0000016}, {"mpr-21371.38", 0xA68782FD, 0x0000018}, {"mpr-21372.39", 0xFC3F4E8B, 0x000001A}, {"mpr-21373.40", 0xB76AD261, 0x000001C}, {"mpr-21374.41", 0xAE6C4D28, 0x000001E}}},
        {&RomSet::sound_program, 1, 1, true,
         {{"epr-21383.21", 0x544D1E28, 0x0000000}}},
        {&RomSet::sound_samples, 1, 1, true,
         {{"mpr-21355.22", 0xC1B2D326, 0x0000000}, {"mpr-21357.24", 0x02703FAB, 0x0400000}}},
        {&RomSet::dsb_program, 1, 1, true,
         {{"epr-21384.2", 0x12FA4780, 0x0000000}}},
        {&RomSet::dsb_mpeg, 1, 1, false,
         {{"mpr-21375.18", 0x735157A9, 0x0000000}, {"mpr-21376.20", 0xE635F81E, 0x0400000}, {"mpr-21377.22", 0x720621F8, 0x0800000}, {"mpr-21378.24", 0x1FCF715E, 0x0C00000}}},
        {&RomSet::drive_program, 1, 1, false,
         {{"epr-21119.ic8", 0x65082B14, 0x0000000}}},
    };
    return r;
}

std::string crc_text(uint32_t crc) {
    char t[16];
    snprintf(t, sizeof(t), "%08x", crc);
    return t;
}

}  // namespace

std::vector<uint8_t> interleave_region(const std::vector<RomPart>& parts, int stride, int chunk, bool swap) {
    size_t size = 0;
    for (const RomPart& p : parts)
        size = std::max(size, p.offset - p.offset % stride + p.data.size() * stride / chunk);
    std::vector<uint8_t> out(size);
    for (const RomPart& p : parts) {
        std::vector<uint8_t> data = p.data;
        if (swap)   // the two bytes of each 16-bit word
            for (size_t i = 0; i + 1 < data.size(); i += 2) std::swap(data[i], data[i + 1]);
        size_t base = p.offset - p.offset % stride, lane = p.offset % stride;
        for (size_t i = 0; i < data.size(); i += chunk)
            std::copy_n(data.begin() + i, std::min<size_t>(chunk, data.size() - i),
                        out.begin() + base + (i / chunk) * stride + lane);
    }
    return out;
}

bool load_rom_zip(const std::string& zip_path, RomSet& out, std::string& error) {
    // Opened with fopen, like the rest of the program's files: miniz's own
    // open takes the path as UTF-8, and the command line is in the ANSI code page
    FILE* f = fopen(zip_path.c_str(), "rb");
    if (!f) {
        error = "cannot open " + zip_path;
        return false;
    }
    mz_zip_archive zip{};
    if (!mz_zip_reader_init_cfile(&zip, f, 0, 0)) {
        fclose(f);
        error = zip_path + " is not a valid zip";
        return false;
    }
    std::map<uint32_t, mz_uint> by_crc;   // chip CRC -> index in the zip
    for (mz_uint i = 0, n = mz_zip_reader_get_num_files(&zip); i < n; i++) {
        mz_zip_archive_file_stat st;
        if (mz_zip_reader_file_stat(&zip, i, &st) && !st.m_is_directory) by_crc.emplace(st.m_crc32, i);
    }
    bool ok = true;
    for (const Region& r : regions()) {
        std::vector<RomPart> parts;
        for (const Chip& c : r.chips) {
            auto it = by_crc.find(c.crc);
            if (it == by_crc.end()) {
                error = std::string("missing ") + c.name + " (crc " + crc_text(c.crc) + ") in " + zip_path +
                        ": not the Star Wars Trilogy ROM (swtrilgy, Rev. A) or incomplete";
                ok = false;
                break;
            }
            size_t size = 0;
            void* data = mz_zip_reader_extract_to_heap(&zip, it->second, &size, 0);
            if (!data || mz_crc32(MZ_CRC32_INIT, static_cast<const uint8_t*>(data), size) != c.crc) {
                mz_free(data);
                error = std::string("wrong CRC for ") + c.name + " inside " + zip_path;
                ok = false;
                break;
            }
            const uint8_t* bytes = static_cast<const uint8_t*>(data);
            parts.push_back({c.offset, std::vector<uint8_t>(bytes, bytes + size)});
            mz_free(data);
        }
        if (!ok) break;
        out.*r.field = interleave_region(parts, r.stride, r.chunk, r.swap);
    }
    mz_zip_reader_end(&zip);
    fclose(f);
    return ok;
}
