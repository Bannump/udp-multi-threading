// server.cpp
// Secure, Multi-Threaded UDP Packet Processor with IPC Monitoring

#include <iostream>
#include <thread>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <cstring>
#include <cstdlib>
#include <cerrno>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <signal.h>

#include "protocol.h"

// Constants
#define UDP_PORT 8080
#define MAX_BUFFER_SIZE 4096
#define MAX_PAYLOAD_SIZE (MAX_BUFFER_SIZE - sizeof(PacketHeader))
#define NUM_WORKER_THREADS 4
#define ENCRYPTION_KEY 0xAA  // Simple XOR key

// Global state
std::atomic<bool> g_running(true);
std::queue<std::pair<uint8_t*, size_t>> g_packet_queue;
std::mutex g_queue_mutex;
std::condition_variable g_queue_cv;
SystemStats* g_stats = nullptr;
int g_shm_fd = -1;

// Thread-safe queue operations
void push_packet(uint8_t* data, size_t len) {
    std::lock_guard<std::mutex> lock(g_queue_mutex);
    uint8_t* packet = new uint8_t[len];
    memcpy(packet, data, len);
    g_packet_queue.push({packet, len});
    g_queue_cv.notify_one();
}

bool pop_packet(uint8_t*& data, size_t& len) {
    std::unique_lock<std::mutex> lock(g_queue_mutex);
    g_queue_cv.wait(lock, [] { return !g_packet_queue.empty() || !g_running; });
    
    if (!g_running && g_packet_queue.empty()) {
        return false;
    }
    
    auto pair = g_packet_queue.front();
    g_packet_queue.pop();
    data = pair.first;
    len = pair.second;
    return true;
}

// Calculate simple checksum (sum of all bytes)
uint32_t calculate_checksum(const uint8_t* data, size_t len) {
    uint32_t sum = 0;
    for (size_t i = 0; i < len; i++) {
        sum += data[i];
    }
    return sum;
}

// Decrypt payload using XOR
void decrypt_payload(uint8_t* payload, size_t len) {
    for (size_t i = 0; i < len; i++) {
        payload[i] ^= ENCRYPTION_KEY;
    }
}

// Process a single packet
void process_packet(uint8_t* buffer, size_t bytes_received) {
    // Buffer overflow protection
    if (bytes_received > MAX_BUFFER_SIZE) {
        std::cerr << "[Worker] Packet too large: " << bytes_received 
                  << " bytes (max: " << MAX_BUFFER_SIZE << ")" << std::endl;
        if (g_stats) {
            g_stats->dropped_packets++;
        }
        return;
    }
    
    // Parse packet header
    if (bytes_received < sizeof(PacketHeader)) {
        std::cerr << "[Worker] Packet too small: " << bytes_received 
                  << " bytes (min: " << sizeof(PacketHeader) << ")" << std::endl;
        if (g_stats) {
            g_stats->dropped_packets++;
        }
        return;
    }
    
    PacketHeader* header = reinterpret_cast<PacketHeader*>(buffer);
    
    // Verify magic word
    if (header->magic_word != 0xDEADBEEF) {
        std::cerr << "[Worker] Invalid magic word: 0x" 
                  << std::hex << header->magic_word << std::dec << std::endl;
        if (g_stats) {
            g_stats->dropped_packets++;
        }
        return;
    }
    
    // Verify payload length
    size_t expected_size = sizeof(PacketHeader) + header->payload_len;
    if (bytes_received < expected_size) {
        std::cerr << "[Worker] Packet size mismatch. Expected: " 
                  << expected_size << ", received: " << bytes_received << std::endl;
        if (g_stats) {
            g_stats->dropped_packets++;
        }
        return;
    }
    
    // Verify checksum
    uint32_t calculated_checksum = calculate_checksum(buffer, bytes_received - sizeof(uint32_t));
    if (calculated_checksum != header->checksum) {
        std::cerr << "[Worker] Checksum mismatch. Expected: " 
                  << header->checksum << ", calculated: " << calculated_checksum << std::endl;
        if (g_stats) {
            g_stats->dropped_packets++;
        }
        return;
    }
    
    // Decrypt payload
    uint8_t* payload = buffer + sizeof(PacketHeader);
    decrypt_payload(payload, header->payload_len);
    
    // Update statistics (thread-safe)
    if (g_stats) {
        g_stats->packets_processed++;
        g_stats->bytes_transferred += bytes_received;
    }
    
    // Simulate processing work
    // In a real system, this would do actual packet processing
}

// Worker thread function
void worker_thread(int thread_id) {
    std::cout << "[Worker " << thread_id << "] Started" << std::endl;
    
    while (g_running) {
        uint8_t* buffer = nullptr;
        size_t len = 0;
        
        if (pop_packet(buffer, len)) {
            process_packet(buffer, len);
            delete[] buffer;
        }
    }
    
    std::cout << "[Worker " << thread_id << "] Stopped" << std::endl;
}

// Listener thread function (Producer)
void listener_thread(int sockfd) {
    std::cout << "[Listener] Started on port " << UDP_PORT << std::endl;
    
    uint8_t buffer[MAX_BUFFER_SIZE];
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);
    
    while (g_running) {
        ssize_t bytes_received = recvfrom(sockfd, buffer, MAX_BUFFER_SIZE, 0,
                                          (struct sockaddr*)&client_addr, &addr_len);
        
        if (bytes_received < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                // Non-blocking socket, no data available
                usleep(1000); // Small sleep to prevent busy-waiting
                continue;
            } else {
                std::cerr << "[Listener] recvfrom error: " << strerror(errno) << std::endl;
                break;
            }
        }
        
        if (bytes_received > 0) {
            // Push packet to queue
            push_packet(buffer, bytes_received);
        }
    }
    
    std::cout << "[Listener] Stopped" << std::endl;
}

// Setup shared memory for IPC
bool setup_shared_memory() {
    // Create shared memory object
    g_shm_fd = shm_open(SHM_NAME, O_CREAT | O_RDWR, 0666);
    if (g_shm_fd == -1) {
        std::cerr << "[Server] Failed to create shared memory: " 
                  << strerror(errno) << std::endl;
        return false;
    }
    
    // Set size
    if (ftruncate(g_shm_fd, SHM_SIZE) == -1) {
        std::cerr << "[Server] Failed to set shared memory size: " 
                  << strerror(errno) << std::endl;
        close(g_shm_fd);
        return false;
    }
    
    // Map shared memory
    g_stats = (SystemStats*)mmap(nullptr, SHM_SIZE, PROT_READ | PROT_WRITE, 
                                  MAP_SHARED, g_shm_fd, 0);
    if (g_stats == MAP_FAILED) {
        std::cerr << "[Server] Failed to map shared memory: " 
                  << strerror(errno) << std::endl;
        close(g_shm_fd);
        return false;
    }
    
    // Initialize statistics
    memset(g_stats, 0, sizeof(SystemStats));
    
    std::cout << "[Server] Shared memory initialized" << std::endl;
    return true;
}

// Cleanup shared memory
void cleanup_shared_memory() {
    if (g_stats && g_stats != MAP_FAILED) {
        munmap(g_stats, SHM_SIZE);
    }
    if (g_shm_fd != -1) {
        close(g_shm_fd);
    }
    shm_unlink(SHM_NAME);
    std::cout << "[Server] Shared memory cleaned up" << std::endl;
}

// Signal handler for graceful shutdown
void signal_handler(int sig) {
    std::cout << "\n[Server] Received signal " << sig << ", shutting down..." << std::endl;
    g_running = false;
    g_queue_cv.notify_all();
}

// Setup UDP socket
int setup_udp_socket() {
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) {
        std::cerr << "[Server] Failed to create socket: " << strerror(errno) << std::endl;
        return -1;
    }
    
    // Set socket to non-blocking
    int flags = fcntl(sockfd, F_GETFL, 0);
    if (flags < 0 || fcntl(sockfd, F_SETFL, flags | O_NONBLOCK) < 0) {
        std::cerr << "[Server] Failed to set non-blocking: " << strerror(errno) << std::endl;
        close(sockfd);
        return -1;
    }
    
    // Bind to port
    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(UDP_PORT);
    
    if (bind(sockfd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "[Server] Failed to bind to port " << UDP_PORT 
                  << ": " << strerror(errno) << std::endl;
        close(sockfd);
        return -1;
    }
    
    std::cout << "[Server] UDP socket bound to port " << UDP_PORT << std::endl;
    return sockfd;
}

int main() {
    std::cout << "=== Secure Multi-Threaded UDP Packet Processor ===" << std::endl;
    
    // Setup signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // Setup shared memory
    if (!setup_shared_memory()) {
        return 1;
    }
    
    // Setup UDP socket
    int sockfd = setup_udp_socket();
    if (sockfd < 0) {
        cleanup_shared_memory();
        return 1;
    }
    
    // Start worker threads
    std::vector<std::thread> workers;
    for (int i = 0; i < NUM_WORKER_THREADS; i++) {
        workers.emplace_back(worker_thread, i + 1);
    }
    
    // Start listener thread
    std::thread listener(listener_thread, sockfd);
    
    // Wait for threads
    listener.join();
    for (auto& worker : workers) {
        worker.join();
    }
    
    // Cleanup
    close(sockfd);
    cleanup_shared_memory();
    
    std::cout << "[Server] Shutdown complete" << std::endl;
    return 0;
}

