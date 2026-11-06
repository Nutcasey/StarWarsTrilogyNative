"""Extracts the memory regions of Star Wars Trilogy (swtrilgy, Rev. A, Model 3 Step 2.1)
from the original zip, without modifying it. Writes flat binaries to data/.

Usage: python tools/romtool.py <path to swtrilgy.zip> [output folder]
"""
import os
import sys
import zipfile
import zlib

# (file name, crc32, offset) per region. Layout taken from the
# hardware interleaving format: stride/chunk/byte_swap. Checked against the
# boot code: the reset vector at 0xFFF00100 decodes and copies CROM[0:2 MB] to
# RAM. dsb_* is the Digital Sound Board 2 (68000 + MPEG music and voices);
# drive_program the Z80 of the force feedback board.
REGIONS = {
    "crom": dict(stride=8, chunk=2, swap=True, files=[
        ("epr-21382a.20", 0x69BAF117, 0x0000000),
        ("epr-21381a.19", 0x2DD34E28, 0x0000002),
        ("epr-21380a.18", 0x780FB4E7, 0x0000004),
        ("epr-21379a.17", 0x24DC1555, 0x0000006)]),
    "banked_crom": dict(stride=8, chunk=2, swap=True, files=[
        ("mpr-21342.04", 0x339525CE, 0x0000000),
        ("mpr-21341.03", 0xB2A269E4, 0x0000002),
        ("mpr-21340.02", 0xAD36040E, 0x0000004),
        ("mpr-21339.01", 0xC0CE5037, 0x0000006),
        ("mpr-21346.08", 0xC8733594, 0x1000000),
        ("mpr-21345.07", 0x6C183A21, 0x1000002),
        ("mpr-21344.06", 0x87453D76, 0x1000004),
        ("mpr-21343.05", 0x12552D07, 0x1000006),
        ("mpr-21350.12", 0x486195E7, 0x2000000),
        ("mpr-21349.11", 0x3D39454B, 0x2000002),
        ("mpr-21348.10", 0x1F7CC5F5, 0x2000004),
        ("mpr-21347.09", 0xECB6B934, 0x2000006)]),
    "vrom": dict(stride=32, chunk=2, swap=False, files=[
        ("mpr-21359.26", 0x34EF4122, 0x0000000),
        ("mpr-21360.27", 0x2882B95E, 0x0000002),
        ("mpr-21361.28", 0x9B61C3C1, 0x0000004),
        ("mpr-21362.29", 0x01A92169, 0x0000006),
        ("mpr-21363.30", 0xE7D18FED, 0x0000008),
        ("mpr-21364.31", 0xCB6A5468, 0x000000A),
        ("mpr-21365.32", 0xAD5449D8, 0x000000C),
        ("mpr-21366.33", 0xDEFB6B95, 0x000000E),
        ("mpr-21367.34", 0xDFD51029, 0x0000010),
        ("mpr-21368.35", 0xAE90FD21, 0x0000012),
        ("mpr-21369.36", 0xBF17EEB4, 0x0000014),
        ("mpr-21370.37", 0x2321592A, 0x0000016),
        ("mpr-21371.38", 0xA68782FD, 0x0000018),
        ("mpr-21372.39", 0xFC3F4E8B, 0x000001A),
        ("mpr-21373.40", 0xB76AD261, 0x000001C),
        ("mpr-21374.41", 0xAE6C4D28, 0x000001E)]),
    "sound_program": dict(stride=1, chunk=1, swap=True, files=[
        ("epr-21383.21", 0x544D1E28, 0x0000000)]),
    "sound_samples": dict(stride=1, chunk=1, swap=True, files=[
        ("mpr-21355.22", 0xC1B2D326, 0x0000000),
        ("mpr-21357.24", 0x02703FAB, 0x0400000)]),
    "dsb_program": dict(stride=1, chunk=1, swap=True, files=[
        ("epr-21384.2", 0x12FA4780, 0x0000000)]),
    "dsb_mpeg": dict(stride=1, chunk=1, swap=False, files=[
        ("mpr-21375.18", 0x735157A9, 0x0000000),
        ("mpr-21376.20", 0xE635F81E, 0x0400000),
        ("mpr-21377.22", 0x720621F8, 0x0800000),
        ("mpr-21378.24", 0x1FCF715E, 0x0C00000)]),
    "drive_program": dict(stride=1, chunk=1, swap=False, files=[
        ("epr-21119.ic8", 0x65082B14, 0x0000000)]),
}


def load_by_crc(zf):
    return {info.CRC: info for info in zf.infolist()}


def byteswap16(data):
    b = bytearray(data)
    b[0::2], b[1::2] = data[1::2], data[0::2]
    return bytes(b)


def build_region(zf, by_crc, spec):
    parts = []
    for name, crc, off in spec["files"]:
        info = by_crc.get(crc)
        if info is None:
            raise SystemExit(f"{name} (crc {crc:08x}) missing from the zip")
        data = zf.read(info)
        if zlib.crc32(data) != crc:
            raise SystemExit(f"Bad CRC in {info.filename}")
        if spec["swap"]:
            data = byteswap16(data)
        parts.append((off, data))
    stride, chunk = spec["stride"], spec["chunk"]
    size = max(off - off % stride + len(d) * stride // chunk for off, d in parts)
    out = bytearray(size)
    for off, data in parts:
        base, lane = off - off % stride, off % stride
        if stride == chunk:
            out[base:base + len(data)] = data
            continue
        for i in range(0, len(data), chunk):
            p = base + (i // chunk) * stride + lane
            out[p:p + chunk] = data[i:i + chunk]
    return bytes(out)


# Chip -> what it is, for the error when a set lacks it
NOTES = {
    "epr-21119.ic8": "force feedback board of the joystick; without it the game stops at "
                     "FAILED FEEDBACK LEVER INITIALIZE. Older swtrilgy sets do not have it",
}


def check_set(zf, by_crc):
    """Every chip of every region, before anything is written: a set with a
    chip missing must not leave a half data folder that build.bat then takes
    as extracted."""
    missing = [name for spec in REGIONS.values() for name, crc, _ in spec["files"] if crc not in by_crc]
    if not missing:
        return
    lines = [f"{zf.filename} is not a complete Star Wars Trilogy ROM (swtrilgy, Rev. A).",
             "Missing (looked up by CRC, so the file names in the zip do not matter):"]
    total = sum(len(spec["files"]) for spec in REGIONS.values())
    if len(missing) > 8:
        lines[1] = f"{len(missing)} of its {total} chips are missing: this is another game or another version."
        missing = []
    for name in missing:
        note = NOTES.get(name)
        lines.append(f"  {name}" + (f"  ({note})" if note else ""))
    lines.append("Get a current, complete swtrilgy.zip (Rev. A) and run build.bat again.")
    raise SystemExit("\n".join(lines))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "data")
    with zipfile.ZipFile(sys.argv[1]) as zf:
        by_crc = load_by_crc(zf)
        check_set(zf, by_crc)
        os.makedirs(outdir, exist_ok=True)
        # crom.bin last: build.bat takes data\crom.bin as "already extracted"
        for region in sorted(REGIONS, key=lambda r: r == "crom"):
            spec = REGIONS[region]
            data = build_region(zf, by_crc, spec)
            with open(os.path.join(outdir, region + ".bin"), "wb") as f:
                f.write(data)
            print(f"{region:14} {len(data):>10} bytes")


if __name__ == "__main__":
    main()
