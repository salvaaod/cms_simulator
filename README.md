# cms_simulator

## CMS CAN Simulator (J1939-based)

`cms_simulator.py` simulates the following CMS CAN signals over the underlying J1939 protocol:

- **Speed**: PGN `0xFEF1` / SPN `84` (Wheel-Based Vehicle Speed)
- **Gear**: PGN `0xF005` / SPN `523` (Transmission Current Gear)
- **Turn Signals**: PGN `0xFE41` / SPN `2369` (Right), SPN `2367` (Left)
- **Open Doors**: PGN `0xFE4E` / SPN `1821` (Position of Doors)
- **Class IV/V View Switching**: PGN `0xFF00` (Camera View Command in byte 0)

The simulator UI and transmit loop are focused on the signals above.

## Usage

1. Place `ECanVci.dll` next to `cms_simulator.py` (or provide a full DLL path in the app).
2. Run on Windows:

```bash
python cms_simulator.py
```

3. Click **Connect**.
4. Set the values for speed, gear, turn signals, door position, and Class IV/V camera command.
5. Use **Start Periodic** to begin transmission and **Stop Periodic** to stop.

## J1939 Encoding Used

### 1) Speed (PGN `0xFEF1`, SPN `84`)

- Data length: 2 bytes
- Resolution: `1/256 km/h` per bit
- Range clamped in app to `0..250.996 km/h`
- Encoded as little-endian raw value in bytes 2-3 of the 8-byte payload

### 2) Gear (PGN `0xF005`, SPN `523`)

- Data length: 1 byte
- Resolution: `1 gear value/bit`, offset `-125`
- App options:
  - Reverse -> raw `124`
  - Neutral -> raw `125`
  - Drive -> raw `126`
  - Park -> raw `251`
- Encoded in byte 4

### 3) Turn Signals (PGN `0xFE41`, SPN `2369` right / `2367` left)

- Each SPN is 2 bits
- Values used by app:
  - `00` = De-activate
  - `01` = Activate
- Right turn signal is encoded in byte 2 bits 5-6
- Left turn signal is encoded in byte 2 bits 7-8

### 4) Door Position (PGN `0xFE4E`, SPN `1821`)

- Data length: 4 bits
- App options:
  - Open -> `0000`
  - Closing -> `0001`
  - Closed -> `0010`
  - Error -> `1110`
  - Not available -> `1111`
- Encoded in byte 1 low nibble

### 5) Class IV/V View Switching (PGN `0xFF00`)

- Data length: 8 bytes
- Camera View Command encoded in byte 0:
  - `0x00` = Retain
  - `0x04` = Switch to Class IV camera view
  - `0x05` = Switch to Class V camera view

## CAN/Hardware Defaults

- Device type: USBCAN-II (`4`)
- Device index: `0`
- CAN channel: `0`
- Bit rate timing: `250 kbps` (`Timing0=0x01`, `Timing1=0x1C`)
- Frame format: Extended CAN ID (29-bit)
- Default J1939 priority: `6`
- Default source address: `0x00`
