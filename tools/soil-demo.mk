# Isolated Pi DEMO build, with dependency tracking for quick subsequent changes.
CXX = g++
FLAGS = -DDEMO -DDEMO_VALVE_SIM_ONLY -DSMTP_OPENSSL -DSOIL_SCHEDULER \
        -DOTF_MAX_BODY_SIZE=65536 -std=c++14 -include string.h -include cstdint \
        -Iexternal/TinyWebsockets/tiny_websockets_lib/include \
        -Iexternal/OpenThings-Framework-Firmware-Library
SOURCES = main.cpp OpenSprinkler.cpp program.cpp opensprinkler_server.cpp utils.cpp weather.cpp \
          soil_scheduler.cpp gpio.cpp mqtt.cpp notifier.cpp RCSwitch.cpp ads1115.cpp \
          $(wildcard sensors/*.cpp external/TinyWebsockets/tiny_websockets_lib/src/*.cpp \
                     external/OpenThings-Framework-Firmware-Library/*.cpp)
OBJECTS = $(patsubst %.cpp,build-soil-demo/%.o,$(SOURCES)) build-soil-demo/smtp.o

.PHONY: all
all: OpenSprinkler-soil.new
OpenSprinkler-soil.new: $(OBJECTS)
	$(CXX) -o $@ $(OBJECTS) -lpthread -lmosquitto -lssl -lcrypto

build-soil-demo/%.o: %.cpp tools/soil-demo.mk
	@mkdir -p $(@D)
	$(CXX) $(FLAGS) -MMD -MP -c $< -o $@
build-soil-demo/smtp.o: smtp.c tools/soil-demo.mk
	@mkdir -p $(@D)
	$(CXX) $(FLAGS) -MMD -MP -c $< -o $@

-include $(OBJECTS:.o=.d)
