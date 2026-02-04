// Package protocol defines the UDP packet and shared-memory layout
// to match the C++ protocol.h exactly for interoperability.
package protocol

import "encoding/binary"

// Shared memory (must match protocol.h)
const (
	SHMName = "/telecom_shm"
	SHMSize = 1024
)

// PacketHeader is the 12-byte packed header (must match C++ struct).
// Client sends in big-endian (network byte order).
type PacketHeader struct {
	MagicWord  uint32 // 0xDEADBEEF
	SeqNum     uint16
	PayloadLen uint16
	Checksum   uint32
}

const PacketHeaderSize = 12

// SystemStats is the shared-memory stats layout (must match C++ struct).
// Field order and padding match protocol.h for IPC with C++ monitor.
type SystemStats struct {
	PacketsProcessed uint64
	BytesTransferred uint64
	DroppedPackets   uint64
	StartTimeSec     uint64
	IsRunning        bool
	Padding          [7]byte
	ThreadLoad       [4]uint64
}

// ParseHeader reads header from buffer (big-endian). Buffer must be at least PacketHeaderSize bytes.
func ParseHeader(buf []byte) (magic uint32, seqNum uint16, payloadLen uint16, checksum uint32) {
	magic = binary.BigEndian.Uint32(buf[0:4])
	seqNum = binary.BigEndian.Uint16(buf[4:6])
	payloadLen = binary.BigEndian.Uint16(buf[6:8])
	checksum = binary.BigEndian.Uint32(buf[8:12])
	return
}
