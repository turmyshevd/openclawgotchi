"""
Battery reader. Supports two HATs, selected by OCG_BATTERY_HAT:
  - "waveshare" (default): UPS HAT (C) via INA219 over I2C.
  - "pisugar2": PiSugar 2 via the pisugar-server TCP socket.

This is optional hardware support. If the HAT, I2C bus, or socket is absent,
all public functions degrade to None/False without raising.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# Backend selection (read inline, matching the OCG_UPS_* convention below).
BATTERY_HAT = os.environ.get("OCG_BATTERY_HAT", "waveshare").strip().lower()

UPS_I2C_ADDR = int(os.environ.get("OCG_UPS_ADDR", "0x43"), 0)
UPS_I2C_BUS = int(os.environ.get("OCG_UPS_BUS", "1"))

PISUGAR_HOST = os.environ.get("OCG_PISUGAR_HOST", "127.0.0.1")
PISUGAR_PORT = int(os.environ.get("OCG_PISUGAR_PORT", "8423"))

_REG_CONFIG = 0x00
_REG_BUSVOLTAGE = 0x02
_REG_POWER = 0x03
_REG_CURRENT = 0x04
_REG_CALIBRATION = 0x05

_CONFIG_VAL = 0x199F
_CALIBRATION_VAL = 4096
_CURRENT_LSB_MA = 0.1
_POWER_LSB_MW = 2.0
_BUS_VOLTAGE_LSB = 0.004


@dataclass
class BatteryReading:
    voltage_v: float
    current_ma: float
    power_mw: float
    percentage: int
    charging: bool
    raw: dict

    def emoji(self) -> str:
        if self.charging:
            return "CHG"
        if self.percentage >= 80:
            return "BAT"
        if self.percentage >= 40:
            return "LOW"
        return "CRIT"

    def short(self) -> str:
        return f"{self.percentage}%/{self.voltage_v:.2f}V"

    def long(self) -> str:
        state = "charging" if self.charging else "discharging"
        return (
            f"{self.emoji()} {self.percentage}% - {self.voltage_v:.2f} V, "
            f"{self.current_ma:+.0f} mA ({state}, {self.power_mw:.0f} mW)"
        )


def _open_bus():
    try:
        from smbus2 import SMBus
    except ImportError:
        log.debug("smbus2 not installed; battery support disabled")
        return None
    try:
        return SMBus(UPS_I2C_BUS)
    except (FileNotFoundError, PermissionError, OSError) as e:
        log.debug("I2C bus %s unavailable: %s", UPS_I2C_BUS, e)
        return None


def _read_word(bus, reg: int) -> int:
    data = bus.read_i2c_block_data(UPS_I2C_ADDR, reg, 2)
    return (data[0] << 8) | data[1]


def _write_word(bus, reg: int, value: int) -> None:
    bus.write_i2c_block_data(UPS_I2C_ADDR, reg, [(value >> 8) & 0xFF, value & 0xFF])


def _calibrate(bus) -> None:
    _write_word(bus, _REG_CALIBRATION, _CALIBRATION_VAL)
    _write_word(bus, _REG_CONFIG, _CONFIG_VAL)


def _percentage_from_voltage(volts: float) -> int:
    pct = (volts - 3.0) / (4.2 - 3.0) * 100.0
    return max(0, min(100, int(round(pct))))


def _waveshare_available() -> bool:
    bus = _open_bus()
    if bus is None:
        return False
    try:
        bus.read_i2c_block_data(UPS_I2C_ADDR, _REG_CONFIG, 2)
        return True
    except Exception:
        return False
    finally:
        try:
            bus.close()
        except Exception:
            pass


def _read_waveshare() -> Optional[BatteryReading]:
    bus = _open_bus()
    if bus is None:
        return None
    try:
        _calibrate(bus)
        bus_raw = _read_word(bus, _REG_BUSVOLTAGE)
        voltage_v = (bus_raw >> 3) * _BUS_VOLTAGE_LSB

        cur_raw = _read_word(bus, _REG_CURRENT)
        if cur_raw > 0x7FFF:
            cur_raw -= 0x10000
        current_ma = cur_raw * _CURRENT_LSB_MA

        pwr_raw = _read_word(bus, _REG_POWER)
        power_mw = pwr_raw * _POWER_LSB_MW

        return BatteryReading(
            voltage_v=voltage_v,
            current_ma=current_ma,
            power_mw=power_mw,
            percentage=_percentage_from_voltage(voltage_v),
            charging=current_ma > 30,
            raw={"bus": bus_raw, "current": cur_raw, "power": pwr_raw},
        )
    except OSError as e:
        log.warning("INA219 read failed: %s", e)
        return None
    except Exception as e:
        log.error("Battery read error: %s", e)
        return None
    finally:
        try:
            bus.close()
        except Exception:
            pass


# --- PiSugar 2 backend (pisugar-server TCP socket) ---

def _pisugar_query(fields: list[str]) -> Optional[dict]:
    """
    Query pisugar-server over TCP. Sends `get <field>` for each field on one
    connection and parses the `key: value` responses. Returns {field: value}
    strings, or None on any socket/parse failure (silent degradation).
    """
    import socket

    try:
        with socket.create_connection((PISUGAR_HOST, PISUGAR_PORT), timeout=2) as sock:
            sock.settimeout(2)
            sock.sendall("".join(f"get {f}\n" for f in fields).encode())

            buf = b""
            result: dict = {}
            while len(result) < len(fields):
                chunk = sock.recv(1024)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    key, sep, value = line.decode(errors="replace").strip().partition(": ")
                    if sep:
                        result[key] = value
            return result or None
    except (OSError, ValueError) as e:
        log.debug("PiSugar query failed: %s", e)
        return None


def _pisugar2_available() -> bool:
    return _pisugar_query(["battery"]) is not None


def _read_pisugar2() -> Optional[BatteryReading]:
    data = _pisugar_query(["battery", "battery_v", "battery_i", "battery_charging"])
    if not data or "battery" not in data:
        return None
    try:
        percentage = int(round(float(data["battery"])))
        voltage_v = float(data.get("battery_v", 0.0))
        # battery_i is amps (PiSugar2-only); tolerate absence.
        current_ma = float(data.get("battery_i", 0.0)) * 1000.0
        # Trust the server's charging flag — battery_i sign is unreliable here.
        charging = data.get("battery_charging", "false").lower() == "true"
        power_mw = abs(voltage_v * current_ma)
        return BatteryReading(
            voltage_v=voltage_v,
            current_ma=current_ma,
            power_mw=power_mw,
            percentage=max(0, min(100, percentage)),
            charging=charging,
            raw=dict(data),
        )
    except (ValueError, KeyError) as e:
        log.warning("PiSugar parse failed: %s", e)
        return None


# --- Public API (dispatches on configured backend) ---

def is_available() -> bool:
    if BATTERY_HAT == "pisugar2":
        return _pisugar2_available()
    return _waveshare_available()


def read() -> Optional[BatteryReading]:
    if BATTERY_HAT == "pisugar2":
        return _read_pisugar2()
    return _read_waveshare()
