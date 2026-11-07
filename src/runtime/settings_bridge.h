// Between the menu's settings (save/settings.ini, FrontendSettings) and the
// command-line Options: at launch the file fills the options, then the
// command line wins, and the menu shows what came out of both
#pragma once
#include "options.h"

struct FrontendSettings;

extern const float BLOOM_STRENGTH[4];   // menu levels OFF, LOW, MEDIUM, HIGH -> Options::bloom
extern const float MAX_ASPECT[5];       // WIDESCREEN 4:3, 16:9, 21:9, 32:9, 48:9 -> Options::max_aspect
int aspect_level(float max_aspect);     // and back: the level an --aspect falls in

// The graphics, sound and display options the menu keeps (the controls and
// the gun are set by app.cpp: they live outside Options)
void options_from_settings(Options& o, const FrontendSettings& ini);
void settings_from_options(FrontendSettings& s, const Options& o);
