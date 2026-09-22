// Optional isolation for the dedicated DEMO test build. No DNS or redirects.
#ifndef OS_DEMO_VALVE_SIM_GUARD_H
#define OS_DEMO_VALVE_SIM_GUARD_H
#include <cstring>
inline bool demo_valve_sim_allowed(unsigned char type, const char *data) {
    const char prefix[] = "127.0.0.1,18080,";
    return type == 4 && data && std::strncmp(data, prefix, sizeof(prefix)-1) == 0;
}
#endif
