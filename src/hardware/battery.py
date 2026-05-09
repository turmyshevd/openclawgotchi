"""
UPS HAT (C) battery reader — INA219 over I2C.

Optional hardware addon: https://www.waveshare.com/wiki/UPS_HAT_(C)

Returns voltage, current, charge state and a 0-100 percentage based on
the **single 18650 cell** Waveshare ships with the UPS HAT (C)
(3.0 V empty → 4.2 V full). Auto-detects the sensor; if absent or
I2C is disabled, every public function returns ``None`` without
raising — callers can use ``is_available()`` to gate UI.

Adapted from Waveshare's INA219.py demo, simplified to a single-shot
reader (the bot polls infrequently — no need for shared state).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# Default I2C address of the INA219 on the UPS HAT (C).
# Override with env OCG_UPS_ADDR (hex) and OCG_UPS_BUS (int) if needed.
import os

UPS_I2C_ADDR = int(os.environ.get("OCG_UPS_ADDR", "0x43"), 0)
UPS_I2C_BUS = int(os.environ.get("OCG_UPS_BUS", "1"))

# INA219 register addresses
_REG_CONFIG       = 0x00
_REG_SHUNTVOLTAGE = 0x01
_REG_BUSVOLTAGE   = 0x02
_REG_POWER        = 0x03
_REG_CURRENT      = 0x04
_REG_CALIBRATION  = 0x05

# Configuration: 16V FSR, 32V gain disabled, 12-bit ADC, continuous
# bus + shunt mode. Calibration assumes 0.1Ω shunt → 0.1 mA per LSB.
_CONFIG_VAL      = 0x199F
_CALIBRATION_VAL = 4096
_CURRENT_LSB_MA  = 0.1   # mA per current register LSB
_POWER_LSB_MW    = 2.0   # mW per power register LSB
_BUS_VOLTAGE_LSB = 0.004  # 4 mV per bus voltage register LSB (after >> 3)


@dataclass
class BatteryReading:
    voltage_v: float       # bus voltage at battery terminals (V)
    current_ma: float      # current into battery (positive = charging)
    power_mw: float        # power on the bus (mW)
    percentage: int        # 0-100 estimate based on voltage curve
    charging: bool         # True when current is flowing in (positive)
    raw: dict              # raw register values for debugging

    def emoji(self) -> str:
        if self.charging:
            return "🔌"
        if self.percentage >= 80:
            return "🔋"
        if self.percentage >= 40:
            return "🪫"
        return "❗🪫"

    def short(self) -> str:
        return f"{self.emoji()} {self.percentage}% / {self.voltage_v:.2f}V"

    def long(self) -> str:
        state = "charging" if self.charging else "discharging"
        return (
            f"{self.emoji()} {self.percentage}% — {self.voltage_v:.2f} V, "
            f"{self.current_ma:+.0f} mA ({state}, {self.power_mw:.0f} mW)"
        )


def _open_bus():
    """Open SMBus connection lazily (smbus2 is optional dep)."""
    try:
        from smbus2 import SMBus
    except ImportError:
        log.debug("smbus2 not installed; battery support disabled")
        return None
    try:
        return SMBus(UPS_I2C_BUS)
    except (FileNotFoundError, PermissionError, OSError) as e:
        # /dev/i2c-N missing or unreadable → I2C not enabled, no UPS HAT
        log.debug(f"I2C bus {UPS_I2C_BUS} unavailable: {e}")
        return None


def _read_word(bus, reg: int) -> int:
    """Read a big-endian 16-bit word from an INA219 register."""
    data = bus.read_i2c_block_data(UPS_I2C_ADDR, reg, 2)
    return (data[0] << 8) | data[1]


def _write_word(bus, reg: int, value: int) -> None:
    bus.write_i2c_block_data(UPS_I2C_ADDR, reg, [(value >> 8) & 0xFF, value & 0xFF])


def _calibrate(bus) -> None:
    _write_word(bus, _REG_CALIBRATION, _CALIBRATION_VAL)
    _write_word(bus, _REG_CONFIG, _CONFIG_VAL)


def _percentage_from_voltage(volts: float) -> int:
    """Map bus voltage of a 1S 18650 cell to a 0–100 percentage.

    UPS HAT (C) is a single-cell (1S) design. Empty ≈ 3.0 V,
    full ≈ 4.2 V. Linear approximation — close enough for a status
    indicator; real Li-ion cells have a non-linear discharge curve
    but the user mostly cares about "low / mid / high".
    """
    pct = (volts - 3.0) / (4.2 - 3.0) * 100.0
    return max(0, min(100, int(round(pct))))


def is_available() -> bool:
    """Quick probe — True if I2C bus and INA219 respond."""
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


def read() -> Optional[BatteryReading]:
    """Take a single battery reading. Returns None if hardware not present."""
    bus = _open_bus()
    if bus is None:
        return None
    try:
        _calibrate(bus)

        # Bus voltage register: top 13 bits hold mV / 4 (i.e. 4 mV LSB after >> 3).
        bus_raw = _read_word(bus, _REG_BUSVOLTAGE)
        voltage_v = ((bus_raw >> 3) * _BUS_VOLTAGE_LSB)

        # Current register is signed two's complement; positive = into battery.
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
            charging=current_ma > 30,  # tiny positive readings are noise
            raw={"bus": bus_raw, "current": cur_raw, "power": pwr_raw},
        )
    except OSError as e:
        log.warning(f"INA219 read failed (UPS HAT not present?): {e}")
        return None
    except Exception as e:
        log.error(f"Battery read error: {e}")
        return None
    finally:
        try:
            bus.close()
        except Exception:
            pass
