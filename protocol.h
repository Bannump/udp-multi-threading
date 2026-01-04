// protocol.h
#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>

// Shared Memory Key
#define SHM_NAME "/telecom_shm"
#define SHM_SIZE 1024

// Custom Packet Structure (12 bytes header + payload)
// Shows capability to handle packed structures
struct __attribute__((packed)) PacketHeader {
    uint32_t magic_word;  // 0xDEADBEEF (Sync marker)
    uint16_t seq_num;     // Sequence number
    uint16_t payload_len; // Length of data
    uint32_t checksum;    // CRC32 or simple sum for verification
};

// Shared Statistics Structure for IPC
struct SystemStats {
    uint64_t packets_processed;
    uint64_t bytes_transferred;
    uint64_t dropped_packets;
};

#endif

