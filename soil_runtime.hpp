// SPDX-License-Identifier: GPL-3.0-or-later
// Linux firmware's durable execution journal. No controller or network I/O here.
#pragma once
#include <algorithm>
#include <cmath>
#include <ctime>
#include <fstream>
#include <string>
#include <stdexcept>
#include <fcntl.h>
#include <unistd.h>
#include "ArduinoJson.hpp"

namespace Soil {
using namespace ArduinoJson;
inline std::string json(JsonVariantConst value) { std::string s; serializeJson(value, s); return s; }
inline void atomic(const std::string& path, JsonVariantConst value) {
    const std::string body=json(value), temp=path+".tmp";
    int fd=open(temp.c_str(), O_WRONLY|O_CREAT|O_TRUNC, 0600);
    if(fd<0) throw std::runtime_error("Cannot open scheduler checkpoint");
    size_t n=0;
    while(n<body.size()) {
        ssize_t count=write(fd, body.data()+n, body.size()-n);
        if(count<=0) { close(fd); throw std::runtime_error("Cannot write scheduler checkpoint"); }
        n+=count;
    }
    int result=fsync(fd); close(fd);
    if(result || rename(temp.c_str(), path.c_str())) throw std::runtime_error("Cannot commit scheduler checkpoint");
    const auto slash=path.find_last_of('/');
    int dir=open((slash==std::string::npos?".":path.substr(0,slash)).c_str(), O_RDONLY);
    if(dir<0) throw std::runtime_error("Cannot open scheduler checkpoint directory");
    result=fsync(dir); close(dir);
    if(result) throw std::runtime_error("Cannot sync scheduler checkpoint directory");
}
inline bool read(const std::string& path, JsonDocument& doc) {
    std::ifstream stream(path);
    if(!stream) return false;
    stream.seekg(0,std::ios::end);
    if(stream.tellg()>4*1024*1024) throw std::runtime_error("Scheduler file exceeds limit");
    stream.seekg(0);
    if(deserializeJson(doc,stream)) throw std::runtime_error("Invalid scheduler JSON checkpoint");
    return true;
}

struct Pulse { int event=-1, pulse=-1, sid=-1; long start=0, end=0; };

class Runtime {
public:
    JsonDocument state;
    std::string path, fatal;
    explicit Runtime(const std::string& path):path(path) {}
    void log(const char* kind, long now, const char* detail="", int sid=-1) {
        auto items=state["records"].is<JsonArray>()?state["records"].as<JsonArray>():state["records"].to<JsonArray>();
        auto item=items.add<JsonObject>(); item["kind"]=kind; item["at"]=now; item["detail"]=detail; item["sid"]=sid;
        while(items.size()>100) items.remove(0);
    }
    void save() { state["revision"]=state["revision"].as<long>()+1; atomic(path,state.as<JsonVariantConst>()); }
    void load(long now) {
        if(!read(path,state)) {state["version"]=1;state["enabled"]=false;state["revision"]=0;return;}
        if(state["version"]!=1) throw std::runtime_error("Unsupported scheduler checkpoint");
        bool interrupted=false;
        for(auto e:state["events"].as<JsonArray>()) if(e["status"]=="running") {
            interrupted=true;
            const auto sid=e["sid"].as<int>();
            state["unresolved"][std::to_string(sid)].to<JsonArray>().add("Restart during an event; delivery needs reconciliation");
            state["ready"][std::to_string(sid)]=now+e["soak"].as<long>();
        }
        state["events"].to<JsonArray>(); state.remove("active");
        if(interrupted) {state["enabled"]=false;log("interrupted",now,"Restart: incomplete events receive no refill credit");}
        log("restart",now);save();
    }
    void configure(JsonVariantConst value, long now) {
        if(!value["draft"]["programs"].is<JsonArrayConst>() || !value["draft"]["groups"].is<JsonArrayConst>() ||
           !value["site"]["timezone"].is<const char*>()) throw std::runtime_error("draft and named site timezone are required");
        if(value["draft"]["programs"].size()>200) throw std::runtime_error("Too many programs");
        if(value["expectedRevision"].is<long>() && value["expectedRevision"]!=state["configRevision"])
            throw std::runtime_error("Controller configuration changed; load it before saving");
        if(!state["active"].isNull() || eventRunning()) throw std::runtime_error("Pause the scheduler before changing configuration");
        // Initial state/profile changes need a new deliberate baseline, not a
        // reinterpretation of old delivery records under a different soil model.
        if(!state["draft"].isNull() && (state["site"].as<JsonVariantConst>()!=value["site"] ||
             state["draft"]["profile"].as<JsonVariantConst>()!=value["draft"]["profile"]) && !value["resetBalance"].as<bool>())
            throw std::runtime_error("Site/profile changed: explicitly initialize new soil balances");
        bool reset=state["draft"].isNull() || value["resetBalance"].as<bool>();
        state["enabled"]=false;state["draft"]=value["draft"];state["site"]=value["site"];
        state["configRevision"]=state["configRevision"].as<long>()+1;
        state["events"].to<JsonArray>(); state.remove("plan"); state.remove("error");
        if(reset) {
            state["anchor"]=now;state["delivery"].to<JsonArray>();state["unresolved"].to<JsonObject>();
        }
        log("configuration",now,reset?"Saved; initial soil baseline reset":"Saved; soil baseline retained");save();
    }
    bool running() const {return fatal.empty() && state["enabled"].as<bool>();}
    bool eventRunning() const {
        for(auto e:state["events"].as<JsonArrayConst>()) if(e["status"]=="running") return true;
        return false;
    }
    void pause(long now, const char* reason) {
        for(auto e:state["events"].as<JsonArray>()) if(e["status"]=="running") {
            int sid=e["sid"];
            if(e["mode"]!="fixed") state["unresolved"][std::to_string(sid)].to<JsonArray>().add("Interrupted event; soil delivery needs reconciliation");
            state["ready"][std::to_string(sid)]=now+e["soak"].as<long>();
            e["status"]="interrupted";
        }
        state.remove("active");state["enabled"]=false;log("paused",now,reason);save();
    }
    void resume(long now) {
        if(state["draft"].isNull()) throw std::runtime_error("Save configuration first");
        state["events"].to<JsonArray>();state["enabled"]=true;state.remove("error");log("resumed",now);save();
    }
    void accept(JsonVariantConst result, long now) {
        if(result["revision"]!=state["revision"]) return; // stale async planning snapshot
        if(!result["weather"].isNull()) state["weather"]=result["weather"];
        state["error"]=result["error"];
        if(result["error"].isNull()) {
            state["events"]=result["events"];
            for(auto event:state["events"].as<JsonArray>())
                if(!state["consumed"][event["id"].as<std::string>()].isNull()) event["status"]="complete";
            state["plan"]=result;
            state["plan"].remove("weather");state["plan"].remove("events");
        } else state["events"].to<JsonArray>();
        log("planned",now,result["error"]|"Updated plan from real OS weather");save();
    }
    Pulse due(long now) {
        Pulse out;
        if(!running() || !state["active"].isNull()) return out;
        long earliest=0;
        auto events=state["events"].as<JsonArray>();
        for(size_t ei=0;ei<events.size();++ei) {
            auto e=events[ei]; if(e["status"]!="pending" && e["status"]!="running") continue;
            auto pulses=e["pulses"].as<JsonArray>();
            for(size_t pi=0;pi<pulses.size();++pi) {
                auto p=pulses[pi]; if(p["status"]!="pending") continue;
                long start=p["start"],end=p["end"];
                if(start>now) break;
                if(now>start+1 || end<=now) {
                    e["status"]="interrupted";
                    if(pi>0 && e["mode"]!="fixed") state["unresolved"][std::to_string(e["sid"].as<int>())].to<JsonArray>().add("Missed remaining cycle; no full refill credited");
                    log("skipped",now,"Missed start; no catch-up",e["sid"]);save();break;
                }
                if(earliest==0 || start<earliest) {earliest=start;out={int(ei),int(pi),e["sid"].as<int>(),start,end};}
                break;
            }
        }
        return out;
    }
    void begin(const Pulse& p, long now) {
        auto e=state["events"][p.event];e["status"]="running";e["pulses"][p.pulse]["status"]="queued";
        state["consumed"][e["id"].as<std::string>()]=now;
        auto a=state["active"].to<JsonObject>();a["event"]=p.event;a["pulse"]=p.pulse;a["sid"]=p.sid;a["end"]=p.end;a["start"]=p.start;
        log("queued",now,"Firmware station queue",p.sid);save(); // intent durable before ON
    }
    void started(int sid,long now) {
        if(state["active"]["sid"]!=sid || state["active"].isNull()) return;
        state["active"]["on"]=now;log("on",now,"Firmware output activated",sid);save();
    }
    void finish(int sid,long now,bool normal) {
        if(state["active"].isNull() || state["active"]["sid"]!=sid) return;
        auto a=state["active"];
        long on=a["on"]|0L, expected=a["end"].as<long>()-a["start"].as<long>();
        if(!normal || !on || now-on<expected || now>a["end"].as<long>()+2) {pause(now,"Interrupted or uncertain duration; no full refill credited");return;}
        auto e=state["events"][a["event"].as<int>()];
        e["pulses"][a["pulse"].as<int>()]["status"]="done";
        state["ready"][std::to_string(sid)]=now+e["soak"].as<long>();
        state["last_off"]=now;
        auto delivery=state["delivery"].as<JsonArray>();
        if(delivery.size()>=10000) throw std::runtime_error("Delivery journal requires a new soil baseline");
        if(e["mode"]!="runtime" && e["mode"]!="fixed") {
            auto d=delivery.add<JsonObject>();d["sid"]=sid;d["at"]=now;d["kind"]="depth";d["mm"]=expected*e["net_rate"].as<double>();
        }
        bool complete=true;
        for(auto p:e["pulses"].as<JsonArray>()) if(p["status"]!="done") complete=false;
        if(complete) {
            e["status"]="complete";
            if(e["mode"]=="runtime") {auto d=delivery.add<JsonObject>();d["sid"]=sid;d["at"]=now;d["kind"]="refill";}
            log("completed",now,e["mode"]=="runtime"?"Complete runtime event: assumed refill":"Complete event",sid);
        }
        state.remove("active");log("off",now,"Firmware output stopped",sid);save();
    }
};
}
