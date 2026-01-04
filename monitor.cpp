// monitor.cpp
// IPC Monitor - Reads statistics from shared memory

#include <iostream>
#include <iomanip>
#include <sstream>
#include <chrono>
#include <atomic>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <cstring>
#include <signal.h>
#include <ctime>

#include "protocol.h"

std::atomic<bool> g_running(true);

void signal_handler(int sig) {
    std::cout << "\n[Monitor] Received signal " << sig << ", shutting down..." << std::endl;
    g_running = false;
}

void format_bytes(uint64_t bytes, std::string& output) {
    const char* units[] = {"B", "KB", "MB", "GB", "TB"};
    int unit_index = 0;
    double size = static_cast<double>(bytes);
    
    while (size >= 1024.0 && unit_index < 4) {
        size /= 1024.0;
        unit_index++;
    }
    
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(2) << size << " " << units[unit_index];
    output = oss.str();
}

int main() {
    std::cout << "=== UDP Packet Processor Monitor ===" << std::endl;
    std::cout << "Reading statistics from shared memory..." << std::endl;
    std::cout << "Press Ctrl+C to exit\n" << std::endl;
    
    // Setup signal handler
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // Open existing shared memory
    int shm_fd = shm_open(SHM_NAME, O_RDONLY, 0666);
    if (shm_fd == -1) {
        std::cerr << "[Monitor] Failed to open shared memory: " 
                  << strerror(errno) << std::endl;
        std::cerr << "[Monitor] Make sure the server is running first!" << std::endl;
        return 1;
    }
    
    // Map shared memory
    SystemStats* stats = (SystemStats*)mmap(nullptr, SHM_SIZE, PROT_READ, 
                                             MAP_SHARED, shm_fd, 0);
    if (stats == MAP_FAILED) {
        std::cerr << "[Monitor] Failed to map shared memory: " 
                  << strerror(errno) << std::endl;
        close(shm_fd);
        return 1;
    }
    
    std::cout << "[Monitor] Connected to shared memory\n" << std::endl;
    
    uint64_t last_packets = 0;
    uint64_t last_bytes = 0;
    auto last_time = std::chrono::steady_clock::now();
    
    // Monitor loop
    while (g_running) {
        auto current_time = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            current_time - last_time).count();
        
        if (elapsed >= 1000) { // Update every second
            uint64_t packets = stats->packets_processed;
            uint64_t bytes = stats->bytes_transferred;
            uint64_t dropped = stats->dropped_packets;
            
            // Calculate throughput
            uint64_t packets_diff = packets - last_packets;
            uint64_t bytes_diff = bytes - last_bytes;
            double pps = (packets_diff * 1000.0) / elapsed; // Packets per second
            double bps = (bytes_diff * 1000.0) / elapsed;   // Bytes per second
            
            // Format output
            std::string bytes_str, throughput_str;
            format_bytes(bytes, bytes_str);
            format_bytes(static_cast<uint64_t>(bps), throughput_str);
            
            // Clear line and print stats
            std::cout << "\r[Monitor] "
                      << "Processed: " << std::setw(10) << packets << " pkts | "
                      << "Dropped: " << std::setw(6) << dropped << " | "
                      << "Total: " << std::setw(12) << bytes_str << " | "
                      << "Throughput: " << std::setw(10) << std::fixed 
                      << std::setprecision(0) << pps << " pps | "
                      << std::setw(10) << throughput_str << "/s"
                      << std::flush;
            
            last_packets = packets;
            last_bytes = bytes;
            last_time = current_time;
        }
        
        usleep(100000); // Sleep 100ms
    }
    
    std::cout << "\n[Monitor] Shutdown complete" << std::endl;
    
    // Cleanup
    munmap(stats, SHM_SIZE);
    close(shm_fd);
    
    return 0;
}

