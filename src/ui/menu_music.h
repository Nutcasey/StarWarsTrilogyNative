// Music for the menus: your own third_party/menu/music.mp3 (or .wav) if there
// is one, else the game's own Main Title (data/menu_music.wav, decoded from
// the music board's ROM at launch: Dsb2::extract_track), looped while a menu is up over the backdrop (not over a paused
// game) and faded out when the game starts. Played by Windows (MCI), apart
// from the game's own sound.
#pragma once

class MenuMusic {
public:
    bool open();    // false: there is no music file
    void close();
    // Every frame: whether the music should be heard, at what volume (0..10, the
    // game's), and the seconds since the last call
    void update(bool want, int volume, double dt);

private:
    bool open_ = false, playing_ = false;
    float level_ = 0;   // the fade, 0..1
    int sent_ = -1;     // the volume last given to Windows
};
