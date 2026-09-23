// SPDX-License-Identifier: GPL-3.0-or-later
#if defined(SOIL_SCHEDULER) && !defined(ARDUINO)
#if !defined(DEMO) || !defined(DEMO_VALVE_SIM_ONLY)
#error "Initial soil firmware integration requires the isolated valve-simulator build"
#endif
#include "soil_runtime.hpp"
#include "soil_http.hpp"
#include <memory>
#include <signal.h>
#include <sys/wait.h>
#include <sys/prctl.h>
#include "OpenSprinkler.h"
#include "program.h"
#include "main.h"
#include "utils.h"
#include "soil_scheduler.h"

extern OpenSprinkler os;
extern ProgramData pd;
namespace {
std::unique_ptr<Soil::Runtime> runtime;
pid_t worker=0;
long launched=0,nextPlan=0,lastTick=0,lastReceiverCheck=0;
std::string directory,workerPath;
Soil::JsonDocument receiver;
long utc() {return time(nullptr);}
long offset() {return (int(os.iopts[IOPT_TIMEZONE])-48)*900;}
void fail(const std::exception& e) {if(runtime) {runtime->fatal=e.what();runtime->state["enabled"]=false;} }
bool eligible(int sid) {
    if(sid<0 || sid>=os.nstations || os.is_master_station(sid) || (os.attrib_dis[sid>>3]&(1<<(sid%8)))) return false;
    StationData data;os.get_station_data(sid,&data);
    std::string expected="127.0.0.1,18080,sim/zone"+std::to_string(sid+1)+"/on,sim/zone"+std::to_string(sid+1)+"/off";
    if(os.get_station_type(sid)!=STN_TYPE_HTTP || expected!=reinterpret_cast<const char*>(data.sped)) return false;
    return true;
}
bool receiverState(int sid,bool on,bool checkSession) {
    receiver.clear();
    char request[]="GET /state HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n";
    EthernetClient client;
    if(!client.connect("127.0.0.1",18080)) return false;
    client.write(reinterpret_cast<uint8_t*>(request),strlen(request));
    std::string body;
    bool valid=Soil::receiverBody([&client](char* data,size_t count){return client.read(reinterpret_cast<uint8_t*>(data),count);},body);
    client.stop();
    if(!valid || Soil::deserializeJson(receiver,body) || receiver["service"]!="opensprinkler-valve-simulator" || !receiver["session"].is<const char*>()) return false;
    if(checkSession && runtime->state["active"]["receiverSession"]!=receiver["session"]) return false;
    if(!receiver["states"]["zone"+std::to_string(sid+1)].is<bool>()) return false;
    for(auto pair:receiver["states"].as<Soil::JsonObject>())
        if(pair.value().as<bool>()!=(on && std::string(pair.key().c_str())==std::string("zone")+std::to_string(sid+1))) return false;
    return true;
}
bool gated(int sid) {
    if(!eligible(sid) || !os.status.enabled || os.status.pause_state || os.iopts[IOPT_SCHEDULING_MODE]!=1) return true;
    if(os.status.rain_delayed && !(os.attrib_igrd[sid>>3]&(1<<(sid%8)))) return true;
    for(uint8_t i=0;i<NUM_SENSORS;i++) {
        auto type=os.iopts[sensor_iopt_keys[i].type];
        if(sensor_available(i) && (type==SENSOR_TYPE_RAIN || type==SENSOR_TYPE_SOIL) && os.sn_sensors[i].active && !(os.attrib_igs[i][sid>>3]&(1<<(sid%8)))) return true;
    }
    return false;
}
void requestPlan(long now) {
    Soil::JsonDocument request;request.set(runtime->state);
    auto s=request["source"].to<Soil::JsonObject>();
    char buffer[TMP_BUFFER_ALLOC_SIZE];
    os.sopt_load(SOPT_LOCATION,buffer);s["location"]=buffer;
    double lat,lon;
    if(sscanf(buffer,"%lf,%lf",&lat,&lon)==2) {request["location"]["latitude"]=lat;request["location"]["longitude"]=lon;}
    os.sopt_load(SOPT_WEATHERURL,buffer);s["host"]=buffer;
    os.sopt_load(SOPT_WEATHER_OPTS,buffer);s["options"]=buffer;
    request["offset"]=offset();request["transition"]=water_time_decode_signed(os.iopts[IOPT_STATION_DELAY_TIME]);
    auto eligibleSids=request["eligible"].to<Soil::JsonArray>();
    for(int sid=0;sid<os.nstations;sid++) if(eligible(sid)) eligibleSids.add(sid);
    Soil::atomic(directory+"/soil-request.json",request.as<Soil::JsonVariantConst>());
    unlink((directory+"/soil-result.json").c_str());
    worker=fork();
    if(worker<0) throw std::runtime_error("Cannot start firmware planner component");
    if(worker==0) {
        prctl(PR_SET_PDEATHSIG,SIGKILL);
        // Do not inherit the firmware listener or valve/network sockets.
        for(int fd=3;fd<1024;++fd) close(fd);
        execl("/usr/bin/python3","python3",workerPath.c_str(),(directory+"/soil-request.json").c_str(),(directory+"/soil-result.json").c_str(),nullptr);
        _exit(127);
    }
    launched=now;nextPlan=now+60;
}
}
void soil_init() {
    try {
        directory=get_data_dir();runtime.reset(new Soil::Runtime(directory+"/soil-state.json"));runtime->load(utc());
        char executable[4096];ssize_t n=readlink("/proc/self/exe",executable,sizeof(executable)-1);
        if(n<0) throw std::runtime_error("Cannot locate firmware planner");
        executable[n]=0;std::string path=executable;workerPath=path.substr(0,path.find_last_of('/'))+"/tools/firmware_scheduler/worker.py";
    } catch(const std::exception& e) {fail(e);}
}
void soil_pause(const char* reason) {
    if(!runtime) return;
    try {
        runtime->pause(utc(),reason);
    } catch(const std::exception& e) {fail(e);}
    // A storage error must never prevent the existing queue from stopping.
    for(int i=0;i<pd.nqueue;i++) if(pd.queue[i].pid==SOIL_PROGRAM_PID) pd.queue[i].dur=0;
}
void soil_started(unsigned char sid) {
    if(!runtime || runtime->state["active"].isNull() || runtime->state["active"]["sid"]!=sid) return;
    try {
        if(!receiverState(sid,true,false)) {soil_pause("Fake receiver did not confirm ON");return;}
        runtime->state["active"]["receiverSession"]=receiver["session"];
        runtime->started(sid,utc());lastReceiverCheck=utc();
    }catch(const std::exception& e){fail(e);}
}
void soil_finished(unsigned char sid,bool normal) {
    if(!runtime || runtime->state["active"].isNull() || runtime->state["active"]["sid"]!=sid) return;
    try {runtime->finish(sid,utc(),normal && receiverState(sid,false,true));nextPlan=0;}catch(const std::exception& e){fail(e);}
    if(!runtime->running()) for(int i=0;i<pd.nqueue;i++) if(pd.queue[i].pid==SOIL_PROGRAM_PID) pd.queue[i].dur=0;
}
void soil_tick() {
    if(!runtime) return;
    const long now=utc();
    try {
        if(lastTick && (now<lastTick || (now-lastTick>5 && runtime->eventRunning()))) soil_pause("Clock jump or stalled loop during watering");
        lastTick=now;
        if(!runtime->state["active"].isNull()) {
            int sid=runtime->state["active"]["sid"];
            bool found=false;
            for(int i=0;i<pd.nqueue;i++) if(pd.queue[i].pid==SOIL_PROGRAM_PID && pd.queue[i].sid==sid && pd.queue[i].dur) found=true;
            if(!found || gated(sid) || !runtime->running()) soil_pause("Queue cancelled, controller disabled, or sensor restriction");
            else if(now-lastReceiverCheck>=5 && !runtime->state["active"]["on"].isNull()) {
                lastReceiverCheck=now;
                if(!receiverState(sid,true,true)) soil_pause("Fake receiver restarted or valve state changed");
            }
        }
        if(worker) {
            int result;pid_t done=waitpid(worker,&result,WNOHANG);
            if(done==0 && now-launched>20) {kill(worker,SIGKILL);waitpid(worker,&result,0);done=worker;}
            if(done!=0) {
                worker=0;Soil::JsonDocument response;
                if(Soil::read(directory+"/soil-result.json",response)) runtime->accept(response.as<Soil::JsonVariantConst>(),now);
                else {runtime->state["events"].to<Soil::JsonArray>();runtime->state["error"]="Firmware planner failed or timed out";runtime->save();}
            }
        }
        if(!runtime->running() || os.iopts[IOPT_SCHEDULING_MODE]!=1 || !os.status.enabled || os.status.pause_state) return;
        // Existing manual/standard queue has priority over a new dispatch.
        if(pd.nqueue || worker) return;
        Soil::Pulse pulse=runtime->due(now);
        if(pulse.sid>=0) {
            if(now<runtime->state["last_off"].as<long>()+water_time_decode_signed(os.iopts[IOPT_STATION_DELAY_TIME])) {runtime->pause(now,"Valve transition interval conflict");return;}
            if(gated(pulse.sid)) {runtime->pause(now,"Valve disabled or weather/sensor restriction");return;}
            if(now<runtime->state["ready"][std::to_string(pulse.sid)].as<long>()) {runtime->pause(now,"Soak readiness conflict");return;}
            // All configured masters must remain off in this initial demo-only path.
            for(unsigned char m=0;m<NUM_MASTER_ZONES;m++) if(os.masters[m][MASOPT_SID]) throw std::runtime_error("Master station support not commissioned for soil scheduler");
            runtime->begin(pulse,now);
            auto q=pd.enqueue();if(!q) throw std::runtime_error("Station queue full");
            q->sid=pulse.sid;q->pid=SOIL_PROGRAM_PID;q->st=pulse.start+offset();q->dur=pulse.end-pulse.start;q->deque_time=q->st+q->dur;
            os.status.program_busy=1;
        } else if(now>=nextPlan && !runtime->eventRunning()) requestPlan(now);
    } catch(const std::exception& e) {fail(e);soil_pause(e.what());}
}
std::string soil_status() {
    Soil::JsonDocument out;
    if(!runtime) {out["error"]="Scheduler not initialized";return Soil::json(out.as<Soil::JsonVariantConst>());}
    out.set(runtime->state);out["service"]="opensprinkler-firmware-scheduler";out["clock"]=utc();out["fatal"]=runtime->fatal;out["planning"]=worker>0;out["enabled"]=runtime->running();
    out.remove("delivery");
    // The weather host, credentials and precise location exist only in the private worker request.
    return Soil::json(out.as<Soil::JsonVariantConst>());
}
std::string soil_configure(const char* body,size_t length) {
    Soil::JsonDocument value;
    try {
        if(!runtime) throw std::runtime_error("Scheduler not initialized");
        if(length==0 || length>65536 || Soil::deserializeJson(value,body,length)) throw std::runtime_error("Invalid or oversized JSON body");
        runtime->configure(value.as<Soil::JsonVariantConst>(),utc());nextPlan=0;
        return "{\"result\":1}";
    } catch(const std::exception& e) {value.clear();value["result"]=18;value["error"]=e.what();return Soil::json(value.as<Soil::JsonVariantConst>());}
}
std::string soil_control(const char* action) {
    try {
        if(!runtime || !action) throw std::runtime_error("Missing scheduler action");
        if(std::string(action)=="pause") soil_pause("Paused by user");
        else if(std::string(action)=="resume") {runtime->resume(utc());nextPlan=0;}
        else throw std::runtime_error("Unknown scheduler action");
        return "{\"result\":1}";
    }catch(const std::exception& e) {Soil::JsonDocument result;result["result"]=18;result["error"]=e.what();return Soil::json(result.as<Soil::JsonVariantConst>());}
}
#endif
