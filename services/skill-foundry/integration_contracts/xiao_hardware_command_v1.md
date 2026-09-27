# Elfred XIAO Hardware Command Contract v1

This contract extends the validated XIAO ESP32-S3 hardware-to-PC stream without
changing its protocol-v2 data frames, ACK frames, or existing control routes.

## Boundary

The existing firmware keeps these meanings:

```text
GET  /api/status  stream and device status
POST /api/start   start hardware-to-PC data streaming
POST /api/stop    stop hardware-to-PC data streaming
GET  /stream      authenticated binary WebSocket stream
```

Physical output commands use separate routes. In particular,
`/api/stop` MUST NOT be treated as a physical-device emergency stop.

```text
POST /api/hardware/command
GET  /api/hardware/commands/{commandId}
POST /api/hardware/stop
```

All requests carry the same header already used by the validated stream:

```text
X-Xiao-Token: <12-64 character device token>
```

The token, Wi-Fi credentials, device address, command payloads, and Journal text
must not be logged or committed.

## Capability discovery

`GET /api/status` retains its current fields and adds:

```json
{
  "ok": true,
  "stream_protocol_version": 2,
  "command_protocol_version": "elfred-xiao-command-v1",
  "device_id": "xiao-a1b2c3",
  "board_profile": "xiao-esp32s3",
  "capabilities": ["notify", "stop"]
}
```

If `command_protocol_version` is absent, Elfred reports
`firmware_incompatible`: the existing input stream remains usable, but software
output is not armed.

## Command

Example `POST /api/hardware/command` body:

```json
{
  "protocolVersion": "elfred-xiao-command-v1",
  "commandId": "haction_...",
  "idempotencyKey": "haction_...",
  "runId": "hrun_...",
  "actionId": "haction_...",
  "adapterId": "pendant",
  "deviceId": "xiao-a1b2c3",
  "command": "notify",
  "preset": "journal_ready",
  "parameters": {
    "title": "Journal ready"
  },
  "issuedAt": "2026-08-01T00:00:00+00:00",
  "expiresAt": "2026-08-01T00:05:00+00:00",
  "payloadSha256": "..."
}
```

`payloadSha256` covers the stable physical intent only: protocol, command and
idempotency IDs, action ID, adapter/device IDs, command, preset, and parameters.
It deliberately excludes `runId` and timestamps so an Elfred retry sends the
same idempotent intent. The device must reject an existing `commandId` paired
with a different digest.

The device validates, in order:

1. token and request size;
2. protocol and target `deviceId`;
3. expiry time;
4. command/preset/parameter allowlist;
5. digest and idempotency record;
6. local safety interlocks.

No command may contain a shell command, file path, arbitrary GPIO number, robot
coordinate, printer address, or executable code. Firmware maps approved presets
to board-specific GPIO, PWM, UART, I2C, or SPI operations.

## Receipt

The POST returns the terminal receipt immediately or HTTP 202 with:

```json
{
  "protocolVersion": "elfred-xiao-command-v1",
  "commandId": "haction_...",
  "status": "accepted"
}
```

Elfred polls the receipt route until a terminal state. Allowed states are:

```text
accepted -> queued -> running -> completed
                              -> failed
rejected | expired | cancelled
```

Replaying an identical command returns its existing receipt and must not repeat
the physical action. Firmware should retain a bounded command-ID/digest/receipt
cache; hazardous devices should persist it across reboot.

## Stop and board replacement

`POST /api/hardware/stop` uses the same envelope with command `stop` and preset
`emergency_stop`. It is independent from stream stop. A physical emergency-stop
and hardware interlocks remain authoritative.

Elfred does not expose GPIO assignments. Board model, pins, buses, actuators,
and calibration live behind the device firmware. XIAO ESP32-S3, Sense, Plus, or
a later controller can therefore replace one another without changing Journal,
planning, Run, or Adapter contracts.
