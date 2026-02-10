#!/usr/bin/env python3
"""
UDP Packet Generator Client
Generates encrypted UDP packets matching the custom protocol
"""

import random
import socket
import struct
import time
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Log to client.log in project directory (dashboard can tail this file)
PROJECT_DIR = Path(__file__).resolve().parent
LOG_FILE = PROJECT_DIR / "client.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger(__name__)

# Protocol constants (must match protocol.h and server MAX_BUFFER_SIZE)
MAGIC_WORD = 0xDEADBEEF
UDP_PORT = 8080
ENCRYPTION_KEY = 0xAA  # XOR key (must match server)
MAX_BUFFER_SIZE = 4096  # server limit
PACKET_HEADER_SIZE = 12

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
    # seq_num is uint16_t: wrap to 0-65535 so long runs don't overflow
    seq_16 = seq_num & 0xFFFF
    # Build packet (without checksum first)
    packet = struct.pack('>I H H', MAGIC_WORD, seq_16, payload_len)
    packet += encrypted_payload
    
    # Calculate checksum (excluding the checksum field itself)
    checksum = calculate_checksum(packet)
    
    # Insert checksum before payload
    packet = struct.pack('>I H H I', MAGIC_WORD, seq_16, payload_len, checksum)
    packet += encrypted_payload
    
    return packet


def create_invalid_packet(seq_num, payload_data, kind):
    """
    Create a packet that the server will reject (for testing drop handling).
    kind: 'magic' | 'checksum' | 'too_small' | 'too_large' | 'size_mismatch'
    No extra work vs create_packet — preserves p99 latency.
    """
    seq_16 = seq_num & 0xFFFF
    encrypted = encrypt_payload(payload_data, ENCRYPTION_KEY)
    payload_len = len(encrypted)

    if kind == "magic":
        bad_magic = 0xDEADBEE0  # wrong magic
        packet = struct.pack(">I H H", bad_magic, seq_16, payload_len)
        packet += b"\x00\x00\x00\x00"  # wrong checksum
        packet += encrypted
        return packet

    if kind == "checksum":
        packet = struct.pack(">I H H", MAGIC_WORD, seq_16, payload_len)
        packet += encrypted
        bad_checksum = (calculate_checksum(packet) + 1) & 0xFFFFFFFF
        return struct.pack(">I H H I", MAGIC_WORD, seq_16, payload_len, bad_checksum) + encrypted

    if kind == "too_small":
        # Less than sizeof(PacketHeader)=12 bytes
        return struct.pack(">I H", MAGIC_WORD, seq_16)[:8]

    if kind == "too_large":
        # Exceeds server MAX_BUFFER_SIZE (4096)
        big_payload = bytes([0xAA] * (MAX_BUFFER_SIZE - PACKET_HEADER_SIZE + 1))
        enc_big = encrypt_payload(big_payload, ENCRYPTION_KEY)
        plen = len(enc_big)
        packet = struct.pack(">I H H", MAGIC_WORD, seq_16, plen)
        packet += enc_big
        cs = calculate_checksum(packet)
        return struct.pack(">I H H I", MAGIC_WORD, seq_16, plen, cs) + enc_big

    if kind == "size_mismatch":
        # Header says payload_len=100 but send only 50 bytes
        declared_len = 100
        short_payload = encrypted[:50] if len(encrypted) >= 50 else encrypted
        packet = struct.pack(">I H H", MAGIC_WORD, seq_16, declared_len)
        packet += short_payload
        cs = calculate_checksum(packet)
        return struct.pack(">I H H I", MAGIC_WORD, seq_16, declared_len, cs) + short_payload

    return create_packet(seq_num, payload_data)


# Invalid packet kinds for random drop injection (matches server drop reasons)
INVALID_KINDS = ("magic", "checksum", "too_small", "too_large", "size_mismatch")
# Display names for stats (order matches INVALID_KINDS)
INVALID_DISPLAY_NAMES = {
    "magic": "Magic word",
    "checksum": "Checksum",
    "too_small": "Too small",
    "too_large": "Too large",
    "size_mismatch": "Size mismatch",
}


def send_packets(host='localhost', port=8080, rate=1000, duration=None, payload_size=100, invalid_fraction=0.0):
    """
    Send UDP packets at specified rate.
    Optionally inject invalid packets (invalid_fraction) that the server will drop; no extra latency.
    
    Args:
        host: Target host
        port: Target port
        rate: Packets per second
        duration: Duration in seconds (None = infinite)
        payload_size: Size of payload in bytes
        invalid_fraction: Fraction of packets to send as invalid (0.0–1.0); server will drop them. Keeps p99 low.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Create a sample payload
    payload = b'X' * payload_size

    seq_num = 0
    packet_count = 0
    invalid_count = 0
    invalid_counts = {k: 0 for k in INVALID_KINDS}
    start_time = time.time()
    interval = 1.0 / rate

    logger.info("Starting packet generation:")
    logger.info("  Target: %s:%s", host, port)
    logger.info("  Rate: %s packets/second", rate)
    logger.info("  Payload size: %s bytes", payload_size)
    logger.info("  Duration: %s", 'infinite' if duration is None else f'{duration} seconds')
    if invalid_fraction > 0:
        logger.info("  Invalid (drop) fraction: %.2f%% (magic/checksum/size)", invalid_fraction * 100)
    logger.info("  Press Ctrl+C to stop")

    try:
        while True:
            packet_start = time.time()

            # With small probability send an invalid packet (server will drop); no extra latency
            if invalid_fraction > 0 and random.random() < invalid_fraction:
                kind = random.choice(INVALID_KINDS)
                packet = create_invalid_packet(seq_num, payload, kind)
                invalid_count += 1
                invalid_counts[kind] += 1
            else:
                packet = create_packet(seq_num, payload)
            sock.sendto(packet, (host, port))

            seq_num += 1
            packet_count += 1

            # Rate limiting (unchanged — same one packet per iteration, good p99)
            elapsed = time.time() - packet_start
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Log statistics every second
            if packet_count % max(1, rate) == 0:
                elapsed_total = time.time() - start_time
                actual_rate = packet_count / elapsed_total if elapsed_total > 0 else 0
                msg = f"Sent: {packet_count} packets | Rate: {actual_rate:.1f} pps | Time: {elapsed_total:.1f}s"
                if invalid_count > 0:
                    msg += f" | Invalid (drop): {invalid_count}"
                logger.info(msg)
                print(f"\r{msg}", end='', flush=True)
            
            # Check duration
            if duration is not None and (time.time() - start_time) >= duration:
                break
                
    except KeyboardInterrupt:
        logger.info("Stopping packet generation...")
        print("\n\nStopping packet generation...")
    finally:
        elapsed_total = time.time() - start_time
        avg_rate = packet_count / elapsed_total if elapsed_total > 0 else 0
        valid_count = packet_count - invalid_count
        valid_pct = 100 * valid_count / packet_count if packet_count else 0
        invalid_pct = 100 * invalid_count / packet_count if packet_count else 0

        logger.info("Statistics: Total sent=%s, Invalid (drop)=%s, Time=%.2fs, Avg rate=%.2f pps",
                   packet_count, invalid_count, elapsed_total, avg_rate)
        print(f"\n\nStatistics:")
        print(f"  Total packets sent: {packet_count}")
        print(f"  Valid (good) packets: {valid_count} ({valid_pct:.2f}%)")
        print(f"  Invalid (drop) packets: {invalid_count} ({invalid_pct:.2f}%)")
        breakdown_str = ""
        if invalid_count > 0:
            print(f"  Invalid breakdown (% of total invalid, count/total invalid):")
            for kind in INVALID_KINDS:
                n = invalid_counts[kind]
                pct_invalid = 100 * n / invalid_count
                label = INVALID_DISPLAY_NAMES[kind]
                print(f"    - {label}: {pct_invalid:.1f}% of invalid ({n}/{invalid_count})")
            # Log parseable line for dashboard
            breakdown_str = " ".join(f"{k}={v}" for k, v in invalid_counts.items())
            logger.info("INVALID_BREAKDOWN %s", breakdown_str)
        print(f"  Total time: {elapsed_total:.2f} seconds")
        print(f"  Average rate: {avg_rate:.2f} packets/second")
        sock.close()

        # Append client run statistics to client.log (shown in dashboard Client log tab)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n--- Client run statistics ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
                f.write(f"  Total packets sent: {packet_count}\n")
                f.write(f"  Valid (good): {valid_count} ({valid_pct:.2f}%)\n")
                f.write(f"  Invalid (drop): {invalid_count} ({invalid_pct:.2f}%)\n")
                if invalid_count > 0:
                    f.write("  Invalid breakdown (% of total invalid, count/total):\n")
                    for kind in INVALID_KINDS:
                        n = invalid_counts[kind]
                        pct = 100 * n / invalid_count
                        label = INVALID_DISPLAY_NAMES[kind]
                        f.write(f"    - {label}: {pct:.1f}% ({n}/{invalid_count})\n")
                    f.write(f"  INVALID_BREAKDOWN {breakdown_str}\n")
                f.write(f"  Time: {elapsed_total:.2f}s, Avg rate: {avg_rate:.2f} pps\n")
        except (OSError, NameError):
            pass  # server.log missing or not writable; ignore

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
    parser.add_argument('--invalid-fraction', type=float, default=0.0,
                       help='Fraction of packets to send as invalid (server drops them); 0=off (default), e.g. 0.01=1%%')
    
    args = parser.parse_args()
    
    send_packets(
        host=args.host,
        port=args.port,
        rate=args.rate,
        duration=args.duration,
        payload_size=args.payload_size,
        invalid_fraction=max(0.0, min(1.0, args.invalid_fraction)),
    )

if __name__ == '__main__':
    main()

