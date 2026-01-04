# Makefile for Secure Multi-Threaded UDP Packet Processor

CXX = g++
CXXFLAGS = -std=c++11 -Wall -Wextra -O2 -pthread
LDFLAGS = -pthread -lrt

# Source files
SERVER_SRC = server.cpp
MONITOR_SRC = monitor.cpp
PROTOCOL_H = protocol.h

# Executables
SERVER_BIN = server
MONITOR_BIN = monitor

# Default target
all: $(SERVER_BIN) $(MONITOR_BIN)

# Build server
$(SERVER_BIN): $(SERVER_SRC) $(PROTOCOL_H)
	$(CXX) $(CXXFLAGS) -o $(SERVER_BIN) $(SERVER_SRC) $(LDFLAGS)

# Build monitor
$(MONITOR_BIN): $(MONITOR_SRC) $(PROTOCOL_H)
	$(CXX) $(CXXFLAGS) -o $(MONITOR_BIN) $(MONITOR_SRC) $(LDFLAGS)

# Clean build artifacts
clean:
	rm -f $(SERVER_BIN) $(MONITOR_BIN)

# Install (optional - just makes executables executable)
install: all
	chmod +x $(SERVER_BIN) $(MONITOR_BIN)
	chmod +x client.py

# Run server (for testing)
run-server: $(SERVER_BIN)
	./$(SERVER_BIN)

# Run monitor (for testing)
run-monitor: $(MONITOR_BIN)
	./$(MONITOR_BIN)

.PHONY: all clean install run-server run-monitor

