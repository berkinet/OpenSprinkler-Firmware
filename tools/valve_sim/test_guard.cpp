#include "guard.h"
#include <cassert>
int main() {
    assert(demo_valve_sim_allowed(4, "127.0.0.1,18080,sim/zone1/on,sim/zone1/off"));
    assert(!demo_valve_sim_allowed(5, "127.0.0.1,18080,x,y"));
    assert(!demo_valve_sim_allowed(2, "127.0.0.1,18080,x,y"));
    assert(!demo_valve_sim_allowed(4, "192.0.2.1,18080,x,y"));
    assert(!demo_valve_sim_allowed(4, "localhost,18080,x,y"));
    assert(!demo_valve_sim_allowed(4, "127.0.0.1,80,x,y"));
    assert(!demo_valve_sim_allowed(4, "127.0.0.1,180800,x,y"));
    assert(!demo_valve_sim_allowed(4, "127.0.0.1.example.org,18080,x,y"));
    assert(!demo_valve_sim_allowed(4, ""));
    assert(!demo_valve_sim_allowed(4, nullptr));
}
