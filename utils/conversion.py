import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple

import requests


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
            response = requests.get(url, timeout=self._request_timeout)

            if response.status_code == 200:
                rates_data = response.json()
                current_time = time.time()

                with self._cache_lock:
                    self._cache[from_code] = {
                        "rates": rates_data,
                        "timestamp": current_time,
                    }

        except Exception as e:
            print(f"Background currency fetch failed for {from_code}: {e}")
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

        # We no longer use currency_converter here.


class Conversion:
    def __init__(self):
        self.units = Units()
        self.currency_cache = _currency_cache

    def convert(self, value: float, from_type: str, to_type: str):
        """
        Generalized conversion function that works with all categories,
        including currency via floatrates.com.
        """
        # Collection of all non-currency charts
        charts = {
            "WEIGHT_CHART": self.units.WEIGHT_CHART,
            "LENGTH_CHART": self.units.LENGTH_CHART,
            "TEMPERATURE_CHART": self.units.TEMPERATURE_CHART,
            "TIME_CHART": self.units.TIME_CHART,
            "LIQUID_VOLUME_CHART": self.units.LIQUID_VOLUME_CHART,
            "STORAGE_TYPE_CHART": self.units.STORAGE_TYPE_CHART,
            "ANGLE_CHART": self.units.ANGLE_CHART,
            "ENERGY_CHART": self.units.ENERGY_CHART,
            "SPEED_CHART": self.units.SPEED_CHART,
            "PRESSURE_CHART": self.units.PRESSURE_CHART,
            "FORCE_CHART": self.units.FORCE_CHART,
            "POWER_CHART": self.units.POWER_CHART,
            "VOLTAGE_CHART": self.units.VOLTAGE_CHART,
            "CURRENT_CHART": self.units.CURRENT_CHART,
            "RESISTANCE_CHART": self.units.RESISTANCE_CHART,
            "CAPACITANCE_CHART": self.units.CAPACITANCE_CHART,
            "INDUCTANCE_CHART": self.units.INDUCTANCE_CHART,
            "FREQUENCY_CHART": self.units.FREQUENCY_CHART,
            "LUMINANCE_CHART": self.units.LUMINANCE_CHART,
            "AREA_CHART": self.units.AREA_CHART,
        }

        # 1) Check if it's in any of the charts (non-currency)
        for chart_name, chart in charts.items():
            if from_type in chart and to_type in chart:
                # Temperatures use lambdas
                if chart_name == "TEMPERATURE_CHART":
                    if from_type == to_type:
                        return value
                    to_kelvin = chart[from_type][0]
                    from_kelvin = chart[to_type][1]
                    return from_kelvin(to_kelvin(value))

                # Handle WEIGHT_CHART separately (tuple values)
                if chart_name == "WEIGHT_CHART":
                    if from_type == to_type:
                        return value
                    to_kg = chart[from_type][0]
                    from_kg = chart[to_type][1]
                    return value * to_kg * from_kg

                # Any other numeric chart
                if from_type == to_type:
                    return value
                return value * (chart[from_type] / chart[to_type])

        # 2) If both are currency codes (e.g. “USD”, “ARS”)
        #    we assume they are uppercase and have 3 letters.
        if (
            len(from_type) == 3
            and len(to_type) == 3
            and from_type.isalpha()
            and to_type.isalpha()
        ):
            result = self._convert_currency_fast(value, from_type, to_type)
            if result is not None:
                return result
            # Fallback to slow method if fast method fails
            return self._convert_currency_via_floatrates(value, from_type, to_type)

        # 3) If it doesn't fall into any case, error.
        raise ValueError(f"Unsupported conversion: {from_type} to {to_type}")

    def _convert_currency_fast(
        self, value: float, from_code: str, to_code: str
    ) -> Optional[float]:
        """
        Fast currency conversion using cached exchange rates.
        Returns None if rate is not available in cache.
        """
        rate_info = self.currency_cache.get_rate(from_code, to_code)
        if rate_info is not None:
            rate, _ = rate_info  # cache_age not needed here
            return value * rate
        return None

    def _convert_currency_via_floatrates(
        self, value: float, from_code: str, to_code: str
    ) -> float:
        """
        Converts using the JSON from floatrates.com:
        - Makes GET to https://www.floatrates.com/daily/{from_lower}.json
        - Takes the rate from the to_lower key and multiplies.
        """
        from_lower = from_code.lower()
        to_lower = to_code.lower()

        if from_lower == to_lower:
            return value

        url = f"https://www.floatrates.com/daily/{from_lower}.json"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            raise ValueError(f"Error getting data from floatrates for {from_code}")

        data = resp.json()
        if to_lower not in data:
            raise ValueError(
                f"Target currency '{to_code}' not found in floatrates response for '{
                    from_code
                }'"
            )

        rate = data[to_lower]["rate"]
        return value * rate

    def parse_input_and_convert(self, input: str):
        parts = input.split()
        addition = "s" if parts[-1].endswith("s") else ""

        if "and" in parts:  # value unit1 and value2 unit2 _ to target_unit
            parts.remove("and")
            if len(parts) != 6:
                raise ValueError(
                    "Invalid format. Expected: 'value from_type and value2 from_type2 _ to_type'"
                )

            value1, from_type1, value2, from_type2, _, to_type = parts
            value1, value2 = float(value1), float(value2)
            from_type1 = self.clean_type(from_type1)
            from_type2 = self.clean_type(from_type2)
            to_type = self.clean_type(to_type)

            if from_type1 == from_type2:
                return (
                    self.convert(value1 + value2, from_type1, to_type),
                    to_type + addition,
                )
            else:
                res = 0
                res += self.convert(value1, from_type1, to_type)
                res += self.convert(value2, from_type2, to_type)
                return res, to_type + addition
        else:
            if len(parts) != 4:
                raise ValueError(
                    "Invalid format. Expected: 'value from_type _ to_type'"
                )
            value, from_type, _, to_type = parts
            value = float(value)
            from_type = self.clean_type(from_type)
            to_type = self.clean_type(to_type)
            return self.convert(value, from_type, to_type), to_type + addition

    def clean_type(self, type: str) -> str:
        """
        If it's currency (3 letters), convert to uppercase.
        If it ends in 's' (and is not 'celsius'), remove the 's' for
        other units."""
        if len(type) == 3 and type.isalpha():
            return type.upper()
        if type.endswith("s") and type.lower() != "celsius":
            # For tables that have singular/plural
            singular = type[:-1].lower()
            # If it exists in STORAGE_TYPE_CHART, we use it;
            # if not, we return singular in lowercase for other charts.
            if singular in self.units.STORAGE_TYPE_CHART:
                return singular
            return singular.lower()
        return type

    def cleanup(self):
        """Cleanup resources."""
        self.currency_cache.cleanup()

    def get_currency_cache_info(
        self, from_code: str, to_code: str
    ) -> Optional[Tuple[bool, float]]:
        """
        Get currency cache information for UI display.
        Returns (is_fresh, cache_age_seconds) or None if not cached.
        """
        rate_info = self.currency_cache.get_rate(from_code, to_code)
        if rate_info is not None:
            _, cache_age = rate_info  # rate not needed here
            is_fresh = cache_age < 300  # Consider fresh if less than 5 minutes old
            return is_fresh, cache_age
        return None


# Quick usage example:
if __name__ == "__main__":
    conv = Conversion()
    # Convert 10 USD to ARS:
    result, suffix = conv.parse_input_and_convert("10 USD _ ARS")
    print(f"{result:.2f} {suffix}")  # Ex: "10 USD _ ARS" -> "38754.23 ARS"
