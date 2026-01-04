#!/usr/bin/env python3
"""
UDP Packet Generator Client
Generates encrypted UDP packets matching the custom protocol
"""

import socket
import struct
import time
import sys
import argparse

# Protocol constants (must match protocol.h)
MAGIC_WORD = 0xDEADBEEF
UDP_PORT = 8080
ENCRYPTION_KEY = 0xAA  # XOR key (must match server)

def calculate_checksum(data):
    """Calculate simple checksum (sum of all bytes)"""
    return sum(data) & 0xFFFFFFFF

def encrypt_payload(payload, key):
    """Encrypt payload using XOR"""
    return bytes([b ^ key for b in payload])

def create_packet(seq_num, payload_data):
    """
    Create a packet matching the PacketHeader structure
    struct PacketHeader {
        uint32_t magic_word;  // 0xDEADBEEF
        uint16_t seq_num;     // Sequence number
        uint16_t payload_len; // Length of data
        uint32_t checksum;    // CRC32 or simple sum
    };
    """
    # Encrypt payload
    encrypted_payload = encrypt_payload(payload_data, ENCRYPTION_KEY)
    payload_len = len(encrypted_payload)
    
    # Build packet (without checksum first)
    packet = struct.pack('>I H H', MAGIC_WORD, seq_num, payload_len)
    packet += encrypted_payload
    
    # Calculate checksum (excluding the checksum field itself)
    checksum = calculate_checksum(packet)
    
    # Insert checksum before payload
    packet = struct.pack('>I H H I', MAGIC_WORD, seq_num, payload_len, checksum)
    packet += encrypted_payload
    
    return packet

def send_packets(host='localhost', port=8080, rate=1000, duration=None, payload_size=100):
    """
    Send UDP packets at specified rate
    
    Args:
        host: Target host
        port: Target port
        rate: Packets per second
        duration: Duration in seconds (None = infinite)
        payload_size: Size of payload in bytes
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Create a sample payload
    payload = b'X' * payload_size
    
    seq_num = 0
    packet_count = 0
    start_time = time.time()
    interval = 1.0 / rate
    
    print(f"Starting packet generation:")
    print(f"  Target: {host}:{port}")
    print(f"  Rate: {rate} packets/second")
    print(f"  Payload size: {payload_size} bytes")
    print(f"  Duration: {'infinite' if duration is None else f'{duration} seconds'}")
    print(f"  Press Ctrl+C to stop\n")
    
    try:
        while True:
            packet_start = time.time()
            
            # Create and send packet
            packet = create_packet(seq_num, payload)
            sock.sendto(packet, (host, port))
            
            seq_num += 1
            packet_count += 1
            
            # Rate limiting
            elapsed = time.time() - packet_start
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
            
            # Print statistics every second
            if packet_count % rate == 0:
                elapsed_total = time.time() - start_time
                actual_rate = packet_count / elapsed_total if elapsed_total > 0 else 0
                print(f"\rSent: {packet_count} packets | "
                      f"Rate: {actual_rate:.1f} pps | "
                      f"Time: {elapsed_total:.1f}s", end='', flush=True)
            
            # Check duration
            if duration is not None and (time.time() - start_time) >= duration:
                break
                
    except KeyboardInterrupt:
        print("\n\nStopping packet generation...")
    finally:
        elapsed_total = time.time() - start_time
        print(f"\n\nStatistics:")
        print(f"  Total packets sent: {packet_count}")
        print(f"  Total time: {elapsed_total:.2f} seconds")
        print(f"  Average rate: {packet_count / elapsed_total:.2f} packets/second")
        sock.close()

def main():
    parser = argparse.ArgumentParser(
        description='UDP Packet Generator for testing the packet processor'
    )
    parser.add_argument('--host', default='localhost',
                       help='Target host (default: localhost)')
    parser.add_argument('--port', type=int, default=UDP_PORT,
                       help=f'Target port (default: {UDP_PORT})')
    parser.add_argument('--rate', type=int, default=1000,
                       help='Packets per second (default: 1000)')
    parser.add_argument('--duration', type=float, default=None,
                       help='Duration in seconds (default: infinite)')
    parser.add_argument('--payload-size', type=int, default=100,
                       help='Payload size in bytes (default: 100)')
    
    args = parser.parse_args()
    
    send_packets(
        host=args.host,
        port=args.port,
        rate=args.rate,
        duration=args.duration,
        payload_size=args.payload_size
    )

if __name__ == '__main__':
    main()

