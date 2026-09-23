// SPDX-License-Identifier: GPL-3.0-or-later
#include "../../soil_runtime.hpp"
#include "../../soil_http.hpp"
#include <cassert>
#include <iostream>
using namespace Soil;
JsonDocument config() {
    JsonDocument d;
    deserializeJson(d,R"({"draft":{"programs":[],"groups":["Normal"],"profile":{}},"site":{"timezone":"Europe/Paris"},"expectedRevision":0})");
    return d;
}
JsonDocument plan(Runtime& r, const char* mode="runtime") {
    JsonDocument d;
    deserializeJson(d,R"({"events":[{"sid":0,"mode":"runtime","status":"pending","soak":60,"net_rate":0.02,"pulses":[{"start":110,"end":170,"status":"pending"},{"start":230,"end":290,"status":"pending"}]}]})");
    d["revision"]=r.state["revision"];d["events"][0]["id"]="test/"+std::to_string(r.state["revision"].as<long>());
    d["events"][0]["mode"]=mode;return d;
}
int main() {
    std::string http="HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\n{}",body;size_t pos=0;
    assert(receiverBody([&](char* data,size_t){if(pos==http.size()) return 0;*data=http[pos++];return 1;},body));
    assert(body=="{}");
    pos=0;http.pop_back();
    assert(!receiverBody([&](char* data,size_t){if(pos==http.size()) return 0;*data=http[pos++];return 1;},body));
    char dir[]="/tmp/soil-runtime-XXXXXX";assert(mkdtemp(dir));
    std::string path=std::string(dir)+"/state.json";
    Runtime r(path);r.load(100);auto c=config();r.configure(c.as<JsonVariantConst>(),100);r.resume(100);
    auto p=plan(r);r.accept(p.as<JsonVariantConst>(),100);
    r.begin(r.due(110),110);r.started(0,110);r.finish(0,170,true);
    assert(r.state["delivery"].size()==0); // a cycle alone is not a full refill
    assert(r.state["ready"]["0"]==230);
    r.begin(r.due(230),230);r.started(0,230);r.finish(0,290,true);
    assert(r.state["delivery"].size()==1 && r.state["delivery"][0]["kind"]=="refill");
    r.finish(0,290,true);assert(r.state["delivery"].size()==1); // idempotent completion
    p["revision"]=r.state["revision"];r.accept(p.as<JsonVariantConst>(),100);
    assert(r.due(110).sid<0); // occurrence identity survives a backward clock/replan
    Runtime restored(path);restored.load(300);assert(restored.state["delivery"].size()==1);
    auto stale=plan(restored);restored.pause(301,"test");restored.accept(stale.as<JsonVariantConst>(),302);
    assert(restored.state["events"].size()==0); // asynchronous result invalidated by pause
    restored.resume(100);p=plan(restored);restored.accept(p.as<JsonVariantConst>(),100);
    restored.begin(restored.due(110),110);restored.started(0,110);restored.finish(0,120,false);
    assert(!restored.running() && restored.state["delivery"].size()==1 && restored.state["unresolved"]["0"].size());
    restored.resume(100);p=plan(restored);restored.accept(p.as<JsonVariantConst>(),100);
    restored.begin(restored.due(110),110);restored.started(0,110);
    Runtime restart(path);restart.load(130);assert(!restart.running() && restart.state["active"].isNull());
    restart.resume(100);p=plan(restart,"fixed");restart.accept(p.as<JsonVariantConst>(),100);
    restart.begin(restart.due(110),110);restart.started(0,110);restart.finish(0,170,true);
    restart.begin(restart.due(230),230);restart.started(0,230);restart.finish(0,290,true);
    assert(restart.state["delivery"].size()==1); // mist does not refill soil
    restart.resume(100);p=plan(restart,"depth");restart.accept(p.as<JsonVariantConst>(),100);
    restart.begin(restart.due(110),110);restart.started(0,110);restart.finish(0,170,true);
    assert(std::abs(restart.state["delivery"][1]["mm"].as<double>()-1.2)<1e-9);
    restart.pause(180,"test");restart.resume(100);p=plan(restart);restart.accept(p.as<JsonVariantConst>(),100);
    assert(restart.due(115).sid<0); // no catch-up
    unlink(path.c_str());rmdir(dir);std::cout<<"Durable firmware runtime tests passed\n";
}
