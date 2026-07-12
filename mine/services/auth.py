import base64
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyotp
from fabric.utils import GdkPixbuf, logger, os, re, time
from pyzbar.pyzbar import decode

import config.data as data
from utils.functions import run_command


def get_otp_file_path():
    cache_dir = Path(data.CACHE_DIR) / "otp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_path = cache_dir / "otp_codes.json"

    if not file_path.exists():
        with open(file_path, "w") as f:
            json.dump([], f)

    return file_path


def capture_selected_area(filename="/tmp/screenshot.png"):
    result = run_command(["slurp"], timeout=10)
    geometry = result.stdout.strip() if isinstance(result.stdout, str) else ""
    if not geometry or result.returncode != 0:
        return None

    if run_command(["grim", "-g", geometry, filename], timeout=10).returncode != 0:
        return None
    return filename


def read_and_save_to_json():
    json_file = get_otp_file_path()
    screenshot = capture_selected_area()
    if screenshot is None:
        logger.error("Failed to capture the selected area.")
        return False

    time.sleep(1)
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(screenshot)
        pixels = pixbuf.get_pixels()
        channels = pixbuf.get_n_channels()
        gray_pixels = pixels[::channels]
        decoded_objects = decode((gray_pixels, pixbuf.get_width(), pixbuf.get_height()))
    finally:
        del pixbuf
    if not decoded_objects:
        return False

    results = []

    for obj in decoded_objects:
        data = obj.data.decode("utf-8")
        result_entry = {"timestamp": datetime.now().isoformat(), "qr_data": data}

        if not data.startswith("otpauth://"):
            result_entry["type"] = "unknown"
            return False

        parsed = urlparse(data)
        query = parse_qs(parsed.query)
        secret = query.get("secret", [None])[0]
        issuer_from_query = query.get("issuer", [None])[0]

        label = parsed.path.lstrip("/") if parsed.path else ""
        account_name = label
        issuer_from_path = None

        if ":" in label:
            parts = label.split(":", 1)
            issuer_from_path = parts[0]
            account_name = parts[1]

        issuer = issuer_from_path or issuer_from_query
        period = int(query.get("period", ["30"])[0])

        totp = pyotp.TOTP(secret, interval=period)
        current_otp = totp.now()
        logger.success(f"Generated OTP: {current_otp} (valid for {period} seconds)")

        result_entry.update(
            {
                "type": "otp",
                "secret": secret,
                "issuer": issuer,
                "account_name": account_name,
            }
        )
        results.append(result_entry)

    existing_data = []
    if os.path.exists(json_file):
        with open(json_file) as f:
            existing_data = json.load(f)

    existing_data.extend(results)

    with open(json_file, "w") as f:
        json.dump(existing_data, f, indent=4)
    return True


def CodeOTP(uri):
    parsed = urlparse(uri)
    query = parse_qs(parsed.query)
    secret = query.get("secret", [None])[0]

    if secret is None:
        return None
    totp = pyotp.TOTP(secret)
    return totp.now()


def generate_totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def get_time_remaining() -> int:
    return 30 - (int(time.time()) % 30)


def get_time_remaining_with_blink() -> str:
    time_remaining = get_time_remaining()
    current_second = int(time.time())
    should_blink = current_second % 2 == 0

    return (
        f"<span alpha='30%'>{time_remaining}s</span>"
        if should_blink
        else f"{time_remaining}s"
    )


def validate_base32_secret(secret: str) -> dict:
    clean_secret = secret.replace(" ", "").replace("-", "").replace("_", "").upper()
    clean_secret = re.sub(r"[^A-Z2-7]", "", clean_secret)

    while len(clean_secret) % 8 != 0:
        clean_secret += "="

    try:
        base64.b32decode(clean_secret)
    except Exception as e:
        return {"success": False, "error": f"Invalid Base32 secret: {str(e)}"}

    try:
        test_totp = pyotp.TOTP(clean_secret)
        test_code = test_totp.now()
        if not test_code or len(test_code) != 6:
            raise ValueError("Generated invalid TOTP code")
    except Exception as e:
        return {"success": False, "error": f"Cannot generate TOTP: {str(e)}"}

    return {"success": True, "secret": clean_secret}


def parse_otpauth_uri(uri: str, account_name: str = "") -> dict:
    parsed = urlparse(uri)
    if parsed.scheme != "otpauth" or parsed.netloc != "totp":
        return {
            "success": False,
            "error": "Only otpauth://totp/ URIs are supported",
        }

    if not account_name:
        account_path = parsed.path.lstrip("/")
        if ":" in account_path:
            issuer, extracted_name = account_path.split(":", 1)
            account_name = extracted_name
        else:
            account_name = account_path

    params = parse_qs(parsed.query)
    secret = params.get("secret", [""])[0]
    issuer = params.get("issuer", [""])[0]
    algorithm = params.get("algorithm", ["SHA1"])[0]
    digits = int(params.get("digits", ["6"])[0])
    period = int(params.get("period", ["30"])[0])

    if not secret:
        return {"success": False, "error": "No secret found in URI"}

    return {
        "success": True,
        "account_name": account_name,
        "secret": secret,
        "issuer": issuer,
        "algorithm": algorithm,
        "digits": digits,
        "period": period,
    }


def scan_qr_and_add_account(account_name: str, secrets_file_path: str) -> dict:
    screenshot_path = capture_selected_area()
    if not screenshot_path:
        return {"success": False, "error": "QR scan cancelled or failed"}

    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(screenshot_path)
        pixels = pixbuf.get_pixels()
        channels = pixbuf.get_n_channels()
        gray_pixels = pixels[::channels]
        decoded_objects = decode((gray_pixels, pixbuf.get_width(), pixbuf.get_height()))
    finally:
        del pixbuf

    if not decoded_objects:
        return {
            "success": False,
            "error": "No QR code detected in selected area",
        }

    qr_data = decoded_objects[0].data.decode("utf-8")

    if not qr_data.startswith("otpauth://"):
        return {"success": False, "error": "QR code is not an otpauth URI"}

    result = parse_otpauth_uri(qr_data, account_name)
    if not result["success"]:
        return result

    secrets = {}
    if os.path.exists(secrets_file_path):
        with open(secrets_file_path, encoding="utf-8") as f:
            secrets = json.load(f)

    secrets[result["account_name"]] = {
        "secret": result["secret"],
        "issuer": result["issuer"],
        "algorithm": result["algorithm"],
        "digits": result["digits"],
        "period": result["period"],
    }

    os.makedirs(os.path.dirname(secrets_file_path), exist_ok=True)
    with open(secrets_file_path, "w", encoding="utf-8") as f:
        json.dump(secrets, f, indent=2)

    display_name = (
        f"{result['issuer']} - {result['account_name']}"
        if result["issuer"]
        else result["account_name"]
    )
    return {
        "success": True,
        "account_name": result["account_name"],
        "display_name": display_name,
        "message": f"Successfully added OTP account: {display_name}",
    }
