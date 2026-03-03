import ctypes
import os
import platform
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk, messagebox


USBCAN_II = 4
PGN_CCVS = 0x00FEF1
PGN_OEL = 0x00FDCC
DEFAULT_DEVICE_TYPE = USBCAN_II
DEFAULT_DEVICE_INDEX = 0
DEFAULT_CAN_INDEX = 0
DEFAULT_DLL_NAME = "ECanVci.dll"
TIMING0_250K = 0x01
TIMING1_250K = 0x1C
CCVS_PRIORITY = 6
CCVS_SOURCE_ADDRESS = 0x00
OEL_PRIORITY = 6
OEL_SOURCE_ADDRESS = 0x42
EVCU4_FRAME_ID = 0x0CFF3F27
DMS_FRAME_ID = 0x18FFEB42
DDAW_STATUS1_FRAME_ID = 0x1803A758
MAX_RX_FRAMES = 100


def j1939_id(priority: int, pgn: int, source_address: int) -> int:
    return ((priority & 0x7) << 26) | ((pgn & 0x3FFFF) << 8) | (source_address & 0xFF)


def build_ccvs_data(speed_value: int) -> list[int]:
    speed_byte = max(0, min(int(speed_value), 0xFF))
    data = [0xFF] * 8
    data[1] = 0x00
    data[2] = speed_byte
    return data


def build_oel_data(turn_signal_state: int) -> list[int]:
    data = [0xFF] * 8
    data[1] = 0xF0 | (turn_signal_state & 0x0F)
    return data


def build_evcu4_data(gear_state: str) -> list[int]:
    gear_map = {
        "Drive": 0x04,
        "Neutral": 0x08,
        "Reverse": 0x10,
    }
    data = [0x00] * 8
    data[5] = gear_map.get(gear_state, 0x08)
    return data


def build_dms_data(active: bool) -> list[int]:
    if active:
        return [0x00] * 8
    data = [0x00] * 8
    data[5] = 0x40
    return data


@dataclass
class DDAWStatus:
    events: list[str]
    face_detected: bool | None
    camera_tampering: bool | None
    fatigue_level: int | None


def parse_ddaw_status1_data(data: list[int]) -> DDAWStatus:
    if len(data) < 7:
        return DDAWStatus(events=[], face_detected=None, camera_tampering=None, fatigue_level=None)
    byte5 = data[5]
    byte6 = data[6]
    byte7 = data[7] if len(data) > 7 else None

    def is_active(bits: int) -> bool:
        return bits == 0b01

    events: list[str] = []
    if is_active(byte5 & 0b11):
        events.append("Side Looking")
    if is_active((byte5 >> 2) & 0b11):
        events.append("Looking Down")
    if is_active((byte5 >> 4) & 0b11):
        events.append("Closing Eyes")
    if is_active((byte5 >> 6) & 0b11):
        events.append("Yawning")
    if is_active(byte6 & 0b11):
        events.append("Fatigue")
    if is_active((byte6 >> 2) & 0b11):
        events.append("Smoking")
    if is_active((byte6 >> 4) & 0b11):
        events.append("Phone")

    face_detected = None
    camera_tampering = None
    fatigue_level = None
    if byte7 is not None:
        fatigue_level = byte7 & 0x0F
        face_detected = is_active((byte7 >> 4) & 0b11)
        camera_tampering = is_active((byte7 >> 6) & 0b11)

    return DDAWStatus(
        events=events,
        face_detected=face_detected,
        camera_tampering=camera_tampering,
        fatigue_level=fatigue_level,
    )


class CAN_OBJ(ctypes.Structure):
    _fields_ = [
        ("ID", ctypes.c_uint),
        ("TimeStamp", ctypes.c_uint),
        ("TimeFlag", ctypes.c_ubyte),
        ("SendType", ctypes.c_ubyte),
        ("RemoteFlag", ctypes.c_ubyte),
        ("ExternFlag", ctypes.c_ubyte),
        ("DataLen", ctypes.c_ubyte),
        ("Data", ctypes.c_ubyte * 8),
        ("Reserved", ctypes.c_ubyte * 3),
    ]


class INIT_CONFIG(ctypes.Structure):
    _fields_ = [
        ("AccCode", ctypes.c_uint),
        ("AccMask", ctypes.c_uint),
        ("Reserved", ctypes.c_uint),
        ("Filter", ctypes.c_ubyte),
        ("Timing0", ctypes.c_ubyte),
        ("Timing1", ctypes.c_ubyte),
        ("Mode", ctypes.c_ubyte),
    ]


@dataclass
class DeviceConfig:
    dll_path: str
    device_type: int
    device_index: int
    can_index: int
    timing0: int
    timing1: int


class USBCANDevice:
    def __init__(self, config: DeviceConfig) -> None:
        self.config = config
        self.dll = ctypes.WinDLL(config.dll_path)
        self._bind_functions()

    def _bind_functions(self) -> None:
        self.dll.OpenDevice.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
        self.dll.OpenDevice.restype = ctypes.c_uint
        self.dll.CloseDevice.argtypes = [ctypes.c_uint, ctypes.c_uint]
        self.dll.CloseDevice.restype = ctypes.c_uint
        self.dll.InitCAN.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(INIT_CONFIG),
        ]
        self.dll.InitCAN.restype = ctypes.c_uint
        self.dll.StartCAN.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
        self.dll.StartCAN.restype = ctypes.c_uint
        self.dll.Transmit.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(CAN_OBJ),
            ctypes.c_ulong,
        ]
        self.dll.Transmit.restype = ctypes.c_ulong
        self.dll.Receive.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(CAN_OBJ),
            ctypes.c_ulong,
            ctypes.c_int,
        ]
        self.dll.Receive.restype = ctypes.c_ulong

    def open(self) -> None:
        result = self.dll.OpenDevice(self.config.device_type, self.config.device_index, 0)
        if result == 0:
            raise RuntimeError("OpenDevice failed.")
        init_config = INIT_CONFIG(
            AccCode=0,
            AccMask=0xFFFFFFFF,
            Reserved=0,
            Filter=0,
            Timing0=self.config.timing0,
            Timing1=self.config.timing1,
            Mode=0,
        )
        if self.dll.InitCAN(
            self.config.device_type,
            self.config.device_index,
            self.config.can_index,
            ctypes.byref(init_config),
        ) == 0:
            raise RuntimeError("InitCAN failed.")
        if self.dll.StartCAN(self.config.device_type, self.config.device_index, self.config.can_index) == 0:
            raise RuntimeError("StartCAN failed.")

    def close(self) -> None:
        self.dll.CloseDevice(self.config.device_type, self.config.device_index)

    def send(self, frame_id: int, data: list[int]) -> int:
        can_obj = CAN_OBJ()
        can_obj.ID = frame_id
        can_obj.TimeStamp = 0
        can_obj.TimeFlag = 0
        can_obj.SendType = 0
        can_obj.RemoteFlag = 0
        can_obj.ExternFlag = 1
        can_obj.DataLen = len(data)
        for index, value in enumerate(data):
            can_obj.Data[index] = value
        return int(
            self.dll.Transmit(
                self.config.device_type,
                self.config.device_index,
                self.config.can_index,
                ctypes.byref(can_obj),
                1,
            )
        )

    def receive(self, max_frames: int, wait_time_ms: int = 0) -> list[CAN_OBJ]:
        buffer = (CAN_OBJ * max_frames)()
        received = int(
            self.dll.Receive(
                self.config.device_type,
                self.config.device_index,
                self.config.can_index,
                buffer,
                max_frames,
                wait_time_ms,
            )
        )
        return list(buffer[:received])


class SimulatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("DMS ADDW CAN Simulator")
        self.device: USBCANDevice | None = None
        self.send_job: str | None = None
        self.distraction_job: str | None = None
        self.poll_job: str | None = None
        self.is_connected = False
        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.columnconfigure(2, weight=1)
        self.status_text = tk.StringVar(value="Status: Disconnected")
        ttk.Label(main, textvariable=self.status_text).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.always_on_top = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            main,
            text="Always on top",
            variable=self.always_on_top,
            command=self.toggle_always_on_top,
        ).grid(row=0, column=2, sticky="e", pady=(0, 8))

        ttk.Label(main, text="Speed (integer)").grid(row=1, column=0, sticky="w")
        self.speed = tk.StringVar(value="0")
        ttk.Entry(main, textvariable=self.speed).grid(row=1, column=1, sticky="ew")

        self.dms_active = tk.BooleanVar(value=True)
        ttk.Checkbutton(main, text="DMS Activation", variable=self.dms_active).grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        ttk.Label(main, text="Turn Signal Switch").grid(row=3, column=0, sticky="w")
        self.turn_signal_state = tk.StringVar(value="Off")
        ttk.Combobox(
            main,
            textvariable=self.turn_signal_state,
            values=["Off", "Left", "Right"],
            state="readonly",
        ).grid(row=3, column=1, sticky="ew")

        ttk.Label(main, text="Send Interval (ms)").grid(row=4, column=0, sticky="w")
        self.interval_ms = tk.IntVar(value=250)
        ttk.Entry(main, textvariable=self.interval_ms).grid(row=4, column=1, sticky="ew")

        ttk.Label(main, text="Distraction Hold (sec)").grid(row=5, column=0, sticky="w")
        self.distraction_hold_seconds = tk.IntVar(value=2)
        ttk.Entry(main, textvariable=self.distraction_hold_seconds).grid(row=5, column=1, sticky="ew")

        ttk.Label(main, text="CCVS Frame ID").grid(row=6, column=0, sticky="w")
        self.ccvs_frame_id_text = tk.StringVar(value="0x18FEF100")
        ttk.Label(main, textvariable=self.ccvs_frame_id_text).grid(row=6, column=1, sticky="w")

        ttk.Label(main, text="CCVS Data Bytes").grid(row=7, column=0, sticky="w")
        self.ccvs_data_bytes_text = tk.StringVar(value="FF FF FF FF FF FF FF FF")
        ttk.Label(main, textvariable=self.ccvs_data_bytes_text).grid(row=7, column=1, sticky="w")

        ttk.Label(main, text="OEL Frame ID").grid(row=8, column=0, sticky="w")
        self.oel_frame_id_text = tk.StringVar(value="0x18FDCC42")
        ttk.Label(main, textvariable=self.oel_frame_id_text).grid(row=8, column=1, sticky="w")

        ttk.Label(main, text="OEL Data Bytes").grid(row=9, column=0, sticky="w")
        self.oel_data_bytes_text = tk.StringVar(value="FF FF FF FF FF FF FF FF")
        ttk.Label(main, textvariable=self.oel_data_bytes_text).grid(row=9, column=1, sticky="w")

        ttk.Label(main, text="DMS Frame ID").grid(row=10, column=0, sticky="w")
        self.dms_frame_id_text = tk.StringVar(value="0x18FFEB42")
        ttk.Label(main, textvariable=self.dms_frame_id_text).grid(row=10, column=1, sticky="w")

        ttk.Label(main, text="DMS Data Bytes").grid(row=11, column=0, sticky="w")
        self.dms_data_bytes_text = tk.StringVar(value="00 00 00 00 00 00 00 00")
        ttk.Label(main, textvariable=self.dms_data_bytes_text).grid(row=11, column=1, sticky="w")

        ttk.Label(main, text="EVCU4 Gear").grid(row=12, column=0, sticky="w")
        self.evcu4_gear = tk.StringVar(value="Neutral")
        ttk.Combobox(
            main,
            textvariable=self.evcu4_gear,
            values=["Drive", "Neutral", "Reverse"],
            state="readonly",
        ).grid(row=12, column=1, sticky="ew")

        ttk.Label(main, text="EVCU4 Frame ID").grid(row=13, column=0, sticky="w")
        self.evcu4_frame_id_text = tk.StringVar(value=f"0x{EVCU4_FRAME_ID:08X}")
        ttk.Label(main, textvariable=self.evcu4_frame_id_text).grid(row=13, column=1, sticky="w")

        ttk.Label(main, text="EVCU4 Data Bytes").grid(row=14, column=0, sticky="w")
        self.evcu4_data_bytes_text = tk.StringVar(value="00 00 00 00 00 08 00 00")
        ttk.Label(main, textvariable=self.evcu4_data_bytes_text).grid(row=14, column=1, sticky="w")

        buttons = ttk.Frame(main)
        buttons.grid(row=15, column=0, columnspan=2, pady=8, sticky="ew")
        self.connect_button = ttk.Button(buttons, text="Connect", command=self.connect)
        self.connect_button.grid(row=0, column=0, padx=4)
        self.disconnect_button = ttk.Button(buttons, text="Disconnect", command=self.disconnect)
        self.disconnect_button.grid(row=0, column=1, padx=4)
        self.start_button = ttk.Button(buttons, text="Start Periodic", command=self.start_periodic)
        self.start_button.grid(row=0, column=2, padx=4)
        self.stop_button = ttk.Button(buttons, text="Stop Periodic", command=self.stop_periodic)
        self.stop_button.grid(row=0, column=3, padx=4)
        self._update_button_states()

        distraction_panel = ttk.Frame(main, padding=(16, 0, 0, 0))
        distraction_panel.grid(row=1, column=2, rowspan=15, sticky="n")
        distraction_panel.columnconfigure(0, weight=1)
        ttk.Label(distraction_panel, text="Last Event Detected").grid(row=0, column=0, sticky="w")
        self.last_event_text = tk.StringVar(value="None")
        ttk.Label(distraction_panel, textvariable=self.last_event_text).grid(row=1, column=0, sticky="w", pady=(0, 12))
        self.distraction_text = tk.StringVar(value="")
        ttk.Label(
            distraction_panel,
            textvariable=self.distraction_text,
            font=("TkDefaultFont", 24, "bold"),
            foreground="red",
            width=12,
        ).grid(row=2, column=0, sticky="w")
        self.face_status_text = tk.StringVar(value="")
        self.face_status_label = ttk.Label(
            distraction_panel,
            textvariable=self.face_status_text,
            font=("TkDefaultFont", 24, "bold"),
            foreground="red",
        )
        self.face_status_label.grid(row=3, column=0, sticky="w")
        self.camera_status_text = tk.StringVar(value="")
        self.camera_status_label = ttk.Label(
            distraction_panel,
            textvariable=self.camera_status_text,
            font=("TkDefaultFont", 24, "bold"),
            foreground="green",
        )
        self.camera_status_label.grid(row=4, column=0, sticky="w")
        self.kss_status_text = tk.StringVar(value="")
        self.kss_status_label = ttk.Label(
            distraction_panel,
            textvariable=self.kss_status_text,
            font=("TkDefaultFont", 24, "bold"),
            foreground="green",
        )
        self.kss_status_label.grid(row=5, column=0, sticky="w")

        self.root.minsize(630, 0)

        self.root.after(200, self.refresh_preview)

    def toggle_always_on_top(self) -> None:
        self.root.attributes("-topmost", self.always_on_top.get())

    def resolve_dll_path(self) -> str:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, DEFAULT_DLL_NAME)

    def connect(self) -> None:
        if platform.system().lower() != "windows":
            messagebox.showerror("Unsupported OS", "This simulator requires Windows to load ECanVci.dll.")
            return
        try:
            resolved_path = self.resolve_dll_path()
            if not os.path.exists(resolved_path):
                raise RuntimeError(f"ECanVci.dll not found at: {resolved_path}")
            config = DeviceConfig(
                dll_path=resolved_path,
                device_type=DEFAULT_DEVICE_TYPE,
                device_index=DEFAULT_DEVICE_INDEX,
                can_index=DEFAULT_CAN_INDEX,
                timing0=TIMING0_250K,
                timing1=TIMING1_250K,
            )
            self.device = USBCANDevice(config)
            self.device.open()
        except Exception as exc:
            messagebox.showerror("Connection Failed", str(exc))
            self.device = None
            return
        self.status_text.set("Status: Connected - Device opened and CAN started.")
        self.is_connected = True
        self.start_periodic()
        self._schedule_poll()
        self._update_button_states()

    def disconnect(self) -> None:
        self.stop_periodic()
        self._stop_poll()
        self._clear_distraction()
        self.face_status_text.set("")
        self.camera_status_text.set("")
        self.kss_status_text.set("")
        if self.device:
            self.device.close()
        self.device = None
        self.is_connected = False
        self.status_text.set("Status: Disconnected - Device closed.")
        self._update_button_states()

    def start_periodic(self) -> None:
        if not self.device:
            messagebox.showwarning("Not Connected", "Connect to a device first.")
            return
        if self.send_job is None:
            self._schedule_send()
        self._update_button_states()

    def stop_periodic(self) -> None:
        if self.send_job is not None:
            self.root.after_cancel(self.send_job)
            self.send_job = None
        self._update_button_states()

    def _schedule_poll(self) -> None:
        self.poll_job = self.root.after(100, self._poll_can)

    def _stop_poll(self) -> None:
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None

    def _poll_can(self) -> None:
        if self.device:
            frames = self.device.receive(MAX_RX_FRAMES)
            for frame in frames:
                if frame.ID == DDAW_STATUS1_FRAME_ID:
                    data = list(frame.Data[: frame.DataLen])
                    status = parse_ddaw_status1_data(data)
                    kss_text, kss_value = self._kss_text(status.fatigue_level)
                    event_text = " + ".join(status.events) if status.events else "None"
                    self.last_event_text.set(event_text)
                    self.kss_status_text.set(f"KSS: {kss_text}")
                    if kss_value is not None and kss_value > 8:
                        self.kss_status_label.configure(foreground="red")
                    else:
                        self.kss_status_label.configure(foreground="green")
                    if status.face_detected is not None:
                        if status.face_detected:
                            self.face_status_text.set("FACE")
                            self.face_status_label.configure(foreground="green")
                        else:
                            self.face_status_text.set("FACE")
                            self.face_status_label.configure(foreground="red")
                    if status.camera_tampering is not None:
                        if status.camera_tampering:
                            self.camera_status_text.set("CAMERA")
                            self.camera_status_label.configure(foreground="red")
                        else:
                            self.camera_status_text.set("CAMERA")
                            self.camera_status_label.configure(foreground="green")
                    if status.events:
                        self._show_distraction(status.events)
        self._schedule_poll()

    def _kss_text(self, fatigue_level: int | None) -> tuple[str, int | None]:
        kss_map = {
            0: ("N/A", None),
            1: ("5", 5),
            2: ("7", 7),
            3: ("9", 9),
        }
        if fatigue_level is None:
            return kss_map[0]
        return kss_map.get(fatigue_level, kss_map[0])

    def _schedule_send(self) -> None:
        try:
            interval = max(10, int(self.interval_ms.get()))
        except tk.TclError:
            interval = 250
        self.send_job = self.root.after(interval, self._send_and_reschedule)

    def _send_and_reschedule(self) -> None:
        if self.device:
            for frame_id, data in self.current_frames():
                self.device.send(frame_id, data)
        self._schedule_send()

    def current_ccvs_frame(self) -> tuple[int, list[int]]:
        frame_id = j1939_id(CCVS_PRIORITY, PGN_CCVS, CCVS_SOURCE_ADDRESS)
        speed_text = self.speed.get().strip()
        if speed_text:
            try:
                speed_value = int(speed_text)
            except ValueError:
                speed_value = 0
        else:
            speed_value = 0
        data = build_ccvs_data(speed_value)
        return frame_id, data

    def current_oel_frame(self) -> tuple[int, list[int]]:
        frame_id = j1939_id(OEL_PRIORITY, PGN_OEL, OEL_SOURCE_ADDRESS)
        turn_signal_map = {"Off": 0, "Left": 1, "Right": 2}
        turn_signal_state = turn_signal_map.get(self.turn_signal_state.get(), 0)
        data = build_oel_data(turn_signal_state)
        return frame_id, data

    def current_evcu4_frame(self) -> tuple[int, list[int]]:
        data = build_evcu4_data(self.evcu4_gear.get())
        return EVCU4_FRAME_ID, data

    def current_dms_frame(self) -> tuple[int, list[int]]:
        data = build_dms_data(self.dms_active.get())
        return DMS_FRAME_ID, data

    def _show_distraction(self, event_names: list[str]) -> None:
        try:
            duration_ms = max(0, int(float(self.distraction_hold_seconds.get()) * 1000))
        except (tk.TclError, ValueError):
            duration_ms = 2000
        self.distraction_text.set("\n".join(event_names))
        if self.distraction_job is not None:
            self.root.after_cancel(self.distraction_job)
        self.distraction_job = self.root.after(duration_ms, self._clear_distraction)

    def _clear_distraction(self) -> None:
        if self.distraction_job is not None:
            self.root.after_cancel(self.distraction_job)
            self.distraction_job = None
        self.distraction_text.set("")

    def current_frames(self) -> list[tuple[int, list[int]]]:
        return [
            self.current_ccvs_frame(),
            self.current_oel_frame(),
            self.current_dms_frame(),
            self.current_evcu4_frame(),
        ]

    def refresh_preview(self) -> None:
        ccvs_frame_id, ccvs_data = self.current_ccvs_frame()
        oel_frame_id, oel_data = self.current_oel_frame()
        dms_frame_id, dms_data = self.current_dms_frame()
        evcu4_frame_id, evcu4_data = self.current_evcu4_frame()
        self.ccvs_frame_id_text.set(f"0x{ccvs_frame_id:08X}")
        self.ccvs_data_bytes_text.set(" ".join(f"{byte:02X}" for byte in ccvs_data))
        self.oel_frame_id_text.set(f"0x{oel_frame_id:08X}")
        self.oel_data_bytes_text.set(" ".join(f"{byte:02X}" for byte in oel_data))
        self.dms_frame_id_text.set(f"0x{dms_frame_id:08X}")
        self.dms_data_bytes_text.set(" ".join(f"{byte:02X}" for byte in dms_data))
        self.evcu4_frame_id_text.set(f"0x{evcu4_frame_id:08X}")
        self.evcu4_data_bytes_text.set(" ".join(f"{byte:02X}" for byte in evcu4_data))
        self.root.after(200, self.refresh_preview)

    def _update_button_states(self) -> None:
        if self.is_connected:
            self.connect_button.state(["disabled"])
            self.disconnect_button.state(["!disabled"])
        else:
            self.connect_button.state(["!disabled"])
            self.disconnect_button.state(["disabled"])
        if self.send_job is None:
            if self.is_connected:
                self.start_button.state(["!disabled"])
            else:
                self.start_button.state(["disabled"])
            self.stop_button.state(["disabled"])
        else:
            self.start_button.state(["disabled"])
            self.stop_button.state(["!disabled"])


def main() -> None:
    root = tk.Tk()
    app = SimulatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
