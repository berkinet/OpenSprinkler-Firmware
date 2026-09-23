// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#if defined(SOIL_SCHEDULER) && !defined(ARDUINO)
#include <string>
constexpr unsigned char SOIL_PROGRAM_PID=98;
void soil_init();
void soil_tick();
void soil_started(unsigned char sid);
void soil_finished(unsigned char sid, bool normal);
void soil_pause(const char* reason);
std::string soil_status();
std::string soil_configure(const char* body, size_t length);
std::string soil_control(const char* action);
#else
inline void soil_init() {}
inline void soil_tick() {}
inline void soil_started(unsigned char) {}
inline void soil_finished(unsigned char, bool) {}
inline void soil_pause(const char*) {}
#endif
