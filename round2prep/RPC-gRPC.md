# RPC/gRPC

To master **RPC (Remote Procedure Calls)** and **gRPC**, you need to understand them as the "nervous system" of microservices. While the **Socket API** is about moving raw bytes, RPC is about moving **function calls** across the network.

---

## 1. RPC: The Conceptual Blueprint

The goal of RPC is to make a remote service look like a local function call in your code.

### The Standard Architecture (The "Stub" Model)

1. **Client Stub:** A local proxy that "marshals" (packs) arguments into a message.
2. **RPC Runtime:** Handles the transport (TCP/UDP).
3. **Server Skeleton:** The server-side proxy that "unmarshals" (unpacks) the message and calls the actual function.

---

## 2. gRPC: The Modern Evolution

Developed by Google, **gRPC** is the industry standard for high-performance RPC. It relies on two core technologies: **HTTP/2** and **Protocol Buffers (Protobuf)**.

### Why gRPC is "Senior Engineer" Level:

* **Protocol Buffers:** Instead of bulky JSON (text), gRPC uses a strictly typed binary format. It's much smaller and faster to parse.
* **HTTP/2:** Allows for **multiplexing** (multiple requests over one connection) and **Streaming** (Server to Client, Client to Server, or Bidirectional).
* **IDL (Interface Definition Language):** You define your service in a `.proto` file, and gRPC automatically generates the code for Python, C++, Java, etc.

---

## 3. The gRPC Workflow (Pseudo-code Simulation)

### Step 1: Define the Contract (`service.proto`)

This is the "Source of Truth" that both your Python client and C++ server will use.

```protobuf
syntax = "proto3";

service VideoService {
  // A simple RPC: One request, one response
  rpc GetMetadata (VideoRequest) returns (VideoResponse);
}

message VideoRequest {
  string video_id = 1;
}

message VideoResponse {
  string title = 1;
  int32 duration_sec = 2;
}
```

### Step 2: The Implementation (Python)

gRPC handles the network; you just write the logic.

```python
# Server-side Logic
class VideoServicer(VideoService_pb2_grpc.VideoServiceServicer):
    def GetMetadata(self, request, context):
        # request.video_id is automatically unmarshalled for you
        return VideoResponse(title="ASU Graduation 2026", duration_sec=3600)

# Client-side Call
stub = VideoService_stub(channel)
response = stub.GetMetadata(VideoRequest(video_id="123"))
print(f"Video Title: {response.title}")
```

---

## 4. Key Differences: gRPC vs. REST

This is the most common interview follow-up.

| Feature | REST | gRPC |
| --- | --- | --- |
| **Protocol** | HTTP 1.1 | HTTP/2 |
| **Payload** | JSON (Text - Heavy) | Protobuf (Binary - Light) |
| **Contract** | Optional (Swagger) | **Required** (.proto) |
| **Streaming** | No (Request/Response) | **Yes** (Bi-directional) |
| **Best For** | Public APIs (Browser compatible) | **Internal Microservices** (Performance) |

---

## 5. Interview "Curveball": Failures and Idempotency

Because RPC happens over a network, calls can fail halfway through.

* **At-most-once:** The server executes the call at most once. If the network fails, we don't know if it happened.
* **At-least-once:** We keep retrying until we get an ACK. **Danger:** If the operation isn't **Idempotent** (like "Charge $10"), you might charge the user multiple times.
* **Senior Answer:** "In a production gRPC system, I would implement **Idempotency Keys**. Even if the client retries, the server recognizes the key and ensures the operation only happens once."

---

### Complexity Analysis

* **Time Complexity:** Physically $O(RTT)$ (Round Trip Time). gRPC reduces the "serialization" time significantly compared to JSON.
* **Space Complexity:** $O(S)$ where $S$ is the size of the Protobuf message. Binary is typically 3–10x smaller than equivalent JSON.
