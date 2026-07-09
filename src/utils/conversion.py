from fabric.utils import logger
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple

import httpx


class CurrencyCache:
    """Thread-safe currency exchange rate cache with background updates."""

    def __init__(self):
        # {base_currency: {rates_data, timestamp}}
        self._cache: Dict[str, Dict] = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = 3600  # 1 hour in seconds
        self._request_timeout = 2  # 2 seconds for faster response
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="currency"
        )
        self._pending_requests: Dict[str, threading.Event] = {}

    def get_rate(self, from_code: str, to_code: str) -> Optional[Tuple[float, float]]:
        """
        Get exchange rate from cache or fetch if needed.
        Returns (rate, cache_age_seconds) or None if unavailable.
        """
        from_lower = from_code.lower()
        to_lower = to_code.lower()

        if from_lower == to_lower:
            return 1.0, 0.0

        current_time = time.time()

        with self._cache_lock:
            # Check if we have fresh cached data
            if from_lower in self._cache:
                cache_entry = self._cache[from_lower]
                cache_age = current_time - cache_entry["timestamp"]

                if cache_age < self._cache_ttl and to_lower in cache_entry["rates"]:
                    rate = cache_entry["rates"][to_lower]["rate"]
                    return rate, cache_age

            # Check if we're already fetching this currency
            if from_lower in self._pending_requests:
                # Don't wait, return cached data if available (even if stale)
                if (
                    from_lower in self._cache
                    and to_lower in self._cache[from_lower]["rates"]
                ):
                    cache_entry = self._cache[from_lower]
                    cache_age = current_time - cache_entry["timestamp"]
                    rate = cache_entry["rates"][to_lower]["rate"]
                    return rate, cache_age
                return None

            # Start background fetch
            self._pending_requests[from_lower] = threading.Event()

        # Submit background task to fetch rates
        self._executor.submit(self._fetch_rates_background, from_lower)

        # Return stale cached data if available
        with self._cache_lock:
            if (
                from_lower in self._cache
                and to_lower in self._cache[from_lower]["rates"]
            ):
                cache_entry = self._cache[from_lower]
                cache_age = current_time - cache_entry["timestamp"]
                rate = cache_entry["rates"][to_lower]["rate"]
                return rate, cache_age

        return None

    def _fetch_rates_background(self, from_code: str):
        """Fetch exchange rates in background thread."""
        try:
            url = f"https://www.floatrates.com/daily/{from_code}.json"
            if self._request_timeout is None:
                self._request_timeout = 5
            response = httpx.get(
                url,
                timeout=10,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                },
            )
            if response.status_code == 200:
                try:
                    rates_data = response.json()
                    current_time = time.time()
                    with self._cache_lock:
                        self._cache[from_code] = {
                            "rates": rates_data,
                            "timestamp": current_time,
                        }
                except Exception as je:
                    logger.error(f"Failed to parse JSON for {from_code}: {je}")
            else:
                print(
                    f"Background fetch for {from_code} returned status {
                        response.status_code
                    }"
                )

        except Exception as e:
            logger.error(f"Background currency fetch failed for {from_code}: {e}")
        finally:
            # Mark request as complete
            with self._cache_lock:
                if from_code in self._pending_requests:
                    self._pending_requests[from_code].set()
                    del self._pending_requests[from_code]

    def cleanup(self):
        """Cleanup resources."""
        self._executor.shutdown(wait=False)
        with self._cache_lock:
            self._cache.clear()
            self._pending_requests.clear()


# Global currency cache instance
_currency_cache = CurrencyCache()


class Units:
    def __init__(self):
        self.WEIGHT_CHART: dict[str, tuple[float, float]] = {
            "kilogram": (1, 1),
            "kg": (1, 1),
            "tonne": (1000, 0.001),
            "ton": (1000, 0.001),
            "gram": (1e-3, 1e3),
            "g": (1e-3, 1e3),
            "milligram": (1e-6, 1e6),
            "mg": (1e-6, 1e6),
            "metric-ton": (1000, 0.001),
            "metric-tonne": (1000, 0.001),
            "long-ton": (1016.04608, 0.0009842073),
            "short-ton": (907.184, 0.0011023122),
            "pound": (0.453592, 2.2046244202),
            "lb": (0.453592, 2.2046244202),
            "stone": (6.35029, 0.1574731728),
            "st": (6.35029, 0.1574731728),
            "ounce": (0.0283495, 35.273990723),
            "oz": (0.0283495, 35.273990723),
            "carrat": (0.0002, 5000),
            "ct": (0.0002, 5000),
            "atomic-mass-unit": (1.660540199e-27, 6.022136652e26),
        }

        self.LENGTH_CHART: dict[str, float] = {
            # meter
            "m": 1,
            "M": 1,
            "meter": 1,
            # kilometer
            "km": 1e3,
            "KM": 1e3,
            "kilometer": 1e3,
            # centimeter
            "cm": 1e-2,
            "CM": 1e-2,
            "centimeter": 1e-2,
            # millimeter
            "mm": 1e-3,
            "MM": 1e-3,
            "millimeter": 1e-3,
            # micrometer
            "um": 1e-6,
            "UM": 1e-6,
            "micrometer": 1e-6,
            # nanometer
            "nm": 1e-9,
            "NM": 1e-9,
            "nanometer": 1e-9,
            # mile
            "mi": 1609.344,
            "MI": 1609.344,
            "mile": 1609.344,
            # yard
            "yd": 0.9144,
            "YD": 0.9144,
            "yard": 0.9144,
            # foot
            "ft": 0.3048,
            "FT": 0.3048,
            "foot": 0.3048,
            "feet": 0.3048,
            # inch
            "in": 0.0254,
            "IN": 0.0254,
            "inch": 0.0254,
            "inches": 0.0254,
            # nautical mile
            "nmi": 1852,
            "NMI": 1852,
            "nautical-mile": 1852,
        }

        self.STORAGE_TYPE_CHART: dict[str, float] = {
            "bit": 1,
            "byte": 8,
            "B": 8,
            "kilobyte": 8192,
            "KB": 8192,
            "megabyte": 8388608,
            "MB": 8388608,
            "gigabyte": 8589934592,
            "GB": 8589934592,
            "terabyte": 8796093022208,
            "TB": 8796093022208,
            "petabyte": 9007199254740992,
            "PB": 9007199254740992,
            "exabyte": 9223372036854775808,
            "EB": 9223372036854775808,
        }

        self.TEMPERATURE_CHART = {
            "celsius": (lambda v: v + 273.15, lambda v: v - 273.15),
            "c": (lambda v: v + 273.15, lambda v: v - 273.15),
            "fahrenheit": (
                lambda v: (v - 32) * 5 / 9 + 273.15,
                lambda v: (v - 273.15) * 9 / 5 + 32,
            ),
            "f": (
                lambda v: (v - 32) * 5 / 9 + 273.15,
                lambda v: (v - 273.15) * 9 / 5 + 32,
            ),
            "kelvin": (lambda v: v, lambda v: v),
            "k": (lambda v: v, lambda v: v),
            "rankine": (lambda v: v * 5 / 9, lambda v: v * 9 / 5),
            "reaumur": (lambda v: v * 5 / 4 + 273.15, lambda v: (v - 273.15) * 4 / 5),
        }

        self.TIME_CHART: dict[str, float] = {
            "second": 1,
            "s": 1,
            "minute": 60,
            "min": 60,
            "m": 60,
            "hour": 3600,
            "h": 3600,
            "milisecond": 1e-3,
            "ms": 1e-3,
            "day": 86400,
            "d": 86400,
            "week": 604800,
            "w": 604800,
            "fortnight": 1209600,
            "month": 2628000,  # Approximation (30.44 days)
            "mo": 2628000,  # Approximation (30.44 days)
            "year": 31536000,  # Approximation (365 days)
            "yr": 31536000,  # Approximation (365 days)
            "decade": 315360000,  # Approximation (10 years)
            "dec": 315360000,  # Approximation (10 years)
            "century": 3153600000,  # Approximation (100 years)
            "cent": 3153600000,  # Approximation (100 years)
            "millennium": 31536000000,  # Approximation (1000 years)
            "millenia": 31536000000,  # Approximation (1000 years)
        }

        self.LIQUID_VOLUME_CHART: dict[str, float] = {
            "liter": 1,
            "l": 1,
            "milliliter": 1e-3,
            "ml": 1e-3,
            "gallon": 3.78541,
            "quart": 0.946353,
            "pint": 0.473176,
            "fluid-ounce": 0.0295735,
            "fl-oz": 0.0295735,
            "oz": 0.0295735,
            "ounce": 0.0295735,
            "cup": 0.236588,
            "tablespoon": 0.0147868,
            "tbsp": 0.0147868,
            "teaspoon": 0.00492892,
            "tsp": 0.00492892,
        }

        self.ANGLE_CHART: dict[str, float] = {
            "degree": 1,
            "deg": 1,
            "radian": 57.2958,
            "rad": 57.2958,
            "gradian": 0.9,
            "gon": 0.9,
        }

        self.ENERGY_CHART: dict[str, float] = {
            "joule": 1,
            "j": 1,
            "kilojoule": 1000,
            "kj": 1000,
            "calorie": 4.184,
            "cal": 4.184,
            "kilocalorie": 4184,
            "kcal": 4184,
            "watt-hour": 3600,
            "wh": 3600,
            "kilowatt-hour": 3.6e6,
            "kwh": 3.6e6,
        }

        self.SPEED_CHART: dict[str, float] = {
            "mps": 1,
            "kmph": 0.277778,
            "mph": 0.44704,
            "fps": 0.3048,
            "knot": 0.514444,
        }

        self.PRESSURE_CHART: dict[str, float] = {
            "pascal": 1,
            "Pa": 1,
            "bar": 100000,
            "atm": 101325,
            "torr": 133.322,
            "mmHg": 133.322,
            "psi": 6894.76,
        }

        self.FORCE_CHART: dict[str, float] = {
            "newton": 1,
            "N": 1,
            "kilonewton": 1000,
            "kN": 1000,
            "pound-force": 4.44822,
            "lbf": 4.44822,
            "dyne": 1e-5,
        }

        self.POWER_CHART: dict[str, float] = {
            "watt": 1,
            "W": 1,
            "kilowatt": 1000,
            "kW": 1000,
            "horsepower": 745.7,
            "hp": 745.7,
            "megawatt": 1e6,
            "MW": 1e6,
        }

        self.VOLTAGE_CHART: dict[str, float] = {
            "volt": 1,
            "V": 1,
            "millivolt": 1e-3,
            "mV": 1e-3,
            "kilovolt": 1000,
            "kV": 1000,
            "megavolt": 1e6,
            "MV": 1e6,
        }

        self.CURRENT_CHART: dict[str, float] = {
            "ampere": 1,
            "A": 1,
            "milliampere": 1e-3,
            "mA": 1e-3,
            "microampere": 1e-6,
            "μA": 1e-6,
        }

        self.RESISTANCE_CHART: dict[str, float] = {
            "ohm": 1,
            "Ω": 1,
            "kilohm": 1000,
            "kΩ": 1000,
            "megohm": 1e6,
            "MΩ": 1e6,
        }

        self.CAPACITANCE_CHART: dict[str, float] = {
            "farad": 1,
            "F": 1,
            "millifarad": 1e-3,
            "mF": 1e-3,
            "microfarad": 1e-6,
            "μF": 1e-6,
            "nanofarad": 1e-9,
            "nF": 1e-9,
        }

        self.INDUCTANCE_CHART: dict[str, float] = {
            "henry": 1,
            "H": 1,
            "millihenry": 1e-3,
            "mH": 1e-3,
            "microhenry": 1e-6,
            "μH": 1e-6,
            "nanohenry": 1e-9,
            "nH": 1e-9,
        }

        self.FREQUENCY_CHART: dict[str, float] = {
            "hertz": 1,
            "Hz": 1,
            "kilohertz": 1e3,
            "kHz": 1e3,
            "megahertz": 1e6,
            "MHz": 1e6,
            "gigahertz": 1e9,
            "GHz": 1e9,
        }

        self.LUMINANCE_CHART: dict[str, float] = {
            "candela": 1,
            "cd": 1,
            "lumen": 1,
            "lm": 1,
            "lux": 1,
            "lx": 1,
        }

        self.AREA_CHART: dict[str, float] = {
            "square-meter": 1,
            "m2": 1,
            "square-kilometer": 1e6,
            "km2": 1e6,
            "hectare": 1e4,
            "ha": 1e4,
            "are": 1e2,
            "a": 1e2,
            "square-centimeter": 1e-4,
            "cm2": 1e-4,
            "square-millimeter": 1e-6,
            "mm2": 1e-6,
        }

        self.CURRENCY_SYMBOLS: dict[str, str] = {
            "$": "USD",
            "€": "EUR",
            "£": "GBP",
            "¥": "JPY",
            "₹": "INR",
            "C$": "CAD",
            "A$": "AUD",
            "₣": "CHF",
            "元": "CNY",
        }

        # We no longer use currency_converter here.
