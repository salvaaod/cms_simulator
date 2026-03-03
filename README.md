# dms_simulator

## CCVS USB-CAN Simulator

`dms_simulator.py` provides a Tkinter UI to transmit the FMS CCVS message (PGN 0xFEF1) for wheel-based speed,
parking brake switch, and brake switch using the `ECanVci.dll` interface described in `USBCAN Interface Library.docx`.

### Features

- Wheel-based vehicle speed (integer value stored in byte 3, byte 2 set to 0).
- Parking brake switch and service brake switch (on/off).
- Source address defaults to `0x00`.
- Priority defaults to `6` (J1939 priority bits, which yields `0x18FEF100` for CCVS).

### Usage

1. Place `ECanVci.dll` next to `dms_simulator.py` or provide the full path in the UI. The app shows the resolved full path so you can confirm where it is looking.
2. Run the app on Windows:

```bash
python dms_simulator.py
```

3. The app uses fixed 250 kbps timing values (Timing0 `01`, Timing1 `1C`) and fixed device/channel settings (USBCAN-II, device 0, channel 0).
4. Click **Connect**, then use **Transmit Once** or **Start Periodic**.

### Signal Encoding Notes

The simulator encodes wheel-based vehicle speed as an integer in byte 3 (byte 2 set to 0). Parking brake uses byte 1
and service brake uses byte 4 with two-bit switch fields; other bytes are set to `0xFF` (not available). Adjust the bit
placement in `build_ccvs_data` if your receiver expects different CCVS bit positions.

### CAN Field Encoding/Decoding Reference

This section describes how every field the simulator writes or reads is encoded/decoded.

#### Transmitted frames (writes)

- **CCVS (PGN 0xFEF1, ID `0x18FEF100`)**
  - **Byte 0:** `0xFF` (not available).
  - **Byte 1:** `0x00` (reserved/unused by this simulator).
  - **Byte 2:** wheel-based vehicle speed as an unsigned integer (0–255). Input is clamped to this range.
  - **Bytes 3–7:** `0xFF` (not available).
  - Source: `build_ccvs_data` in `dms_simulator.py`.
- **OEL (PGN 0xFDCC, ID `0x18FDCC42`)**
  - **Byte 1:** high nibble fixed to `0xF`, low nibble encodes turn signal state:
    - `0x0` = Off
    - `0x1` = Left
    - `0x2` = Right
  - **All other bytes:** `0xFF` (not available).
  - Source: `build_oel_data` in `dms_simulator.py`.
- **DMS (ID `0x18FFEB42`)**
  - **Active:** all bytes `0x00`.
  - **Inactive:** byte 5 set to `0x40`, all other bytes `0x00`.
  - Source: `build_dms_data` in `dms_simulator.py`.
- **EVCU4 (ID `0x0CFF3F27`)**
  - **Byte 5:** gear state encoding:
    - `0x04` = Drive
    - `0x08` = Neutral (default)
    - `0x10` = Reverse
  - **All other bytes:** `0x00`.
  - Source: `build_evcu4_data` in `dms_simulator.py`.

#### Received frames (reads)

- **DDAW_STATUS1 (ID `0x1803A758`)**
  - Uses bytes 5–7. Each two-bit field is decoded; a value of `0b01` means “active”.
  - **Byte 5:**
    - bits 1–0: Side Looking
    - bits 3–2: Looking Down
    - bits 5–4: Closing Eyes
    - bits 7–6: Yawning
  - **Byte 6:**
    - bits 1–0: Fatigue
    - bits 3–2: Smoking
    - bits 5–4: Phone
  - **Byte 7 (optional if present):**
    - bits 3–0: fatigue level (KSS mapping: `1→5`, `2→7`, `3→9`, other/0 = N/A)
    - bits 5–4: face detected (active when `0b01`)
    - bits 7–6: camera tampering (active when `0b01`)
  - Source: `parse_ddaw_status1_data` in `dms_simulator.py`.
