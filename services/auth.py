import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyotp
from PIL import Image
from pyzbar.pyzbar import decode

import config.data as data


def get_otp_file_path():
    """Returns the path to the OTP file inside the cache directory."""
    cache_dir = Path(data.CACHE_DIR) / "otp"
    # Create the directory if it doesn't exist
    cache_dir.mkdir(parents=True, exist_ok=True)

    file_path = cache_dir / "otp_codes.json"

    # Create the file if it doesn't exist
    if not file_path.exists():
        with open(file_path, "w") as f:
            json.dump([], f)
        print(f"File {file_path} created successfully!")

    return file_path


def capture_selected_area(filename="/tmp/screenshot.png"):
    """
    Uses slurp to let the user select an area of the screen,
    then captures that area using grim.
    """
    try:
        # slurp returns coordinates in format: x,y widthxheight (e.g. 100,200 300x400)
        result = subprocess.run(["slurp"], check=True, capture_output=True, text=True)
        geometry = result.stdout.strip()
        if not geometry:
            print("No area selected with slurp.")
            return None
    except subprocess.CalledProcessError as e:
        print("Error selecting area with slurp:", e)
        return None

    try:
        # grim uses -g to capture a specific region
        subprocess.run(["grim", "-g", geometry, filename], check=True)
    except subprocess.CalledProcessError as e:
        print("Error capturing screenshot with grim:", e)
        return None

    return filename


def read_and_save_to_json():
    # Get the full path to the JSON file
    json_file = get_otp_file_path()

    screenshot = capture_selected_area()
    if screenshot is None:
        print("Failed to capture the selected area.")
        return False

    # Short delay to ensure the file is written
    time.sleep(1)

    # Open the captured image
    try:
        img = Image.open(screenshot)
    except Exception as e:
        print("Error opening the image:", e)
        return False

    # Decode QR Code(s) from the image
    decoded_objects = decode(img)
    if not decoded_objects:
        print("No QR Code detected in the selected area.")
        return False

    results = []

    for obj in decoded_objects:
        data = obj.data.decode("utf-8")
        print("QR Code detected:", data)

        result_entry = {"timestamp": datetime.now().isoformat(), "qr_data": data}

        if data.startswith("otpauth://"):
            parsed = urlparse(data)
            query = parse_qs(parsed.query)

            # Extract the secret properly
            secret = query.get("secret", [None])[0]
            issuer_from_query = query.get("issuer", [None])[0]

            # Extract the label (path), which may contain issuer and account
            label = parsed.path.lstrip("/") if parsed.path else ""
            account_name = label
            issuer_from_path = None

            if ":" in label:
                parts = label.split(":", 1)
                issuer_from_path = parts[0]
                account_name = parts[1]

            # Prefer issuer from path if available, otherwise use from query
            issuer = issuer_from_path or issuer_from_query

            # Extract the period (default is 30 seconds)
            period = int(query.get("period", ["30"])[0])

            # Create TOTP object with the correct interval
            totp = pyotp.TOTP(secret, interval=period)
            current_otp = totp.now()
            print(f"Generated OTP: {current_otp} (valid for {period} seconds)")

            result_entry.update(
                {
                    "type": "otp",
                    "secret": secret,
                    "issuer": issuer,
                    "account_name": account_name,
                }
            )
        else:
            result_entry["type"] = "unknown"
            print("Unrecognized format. Expected a URI like otpauth://")
            return False

        results.append(result_entry)

    # Load existing data if the file exists
    existing_data = []
    if os.path.exists(json_file):
        try:
            with open(json_file, "r") as f:
                existing_data = json.load(f)
        except json.JSONDecodeError:
            print(f"Error reading the file {json_file}. Creating a new one.")

    # Append new results
    existing_data.extend(results)

    # Save to JSON file
    with open(json_file, "w") as f:
        json.dump(existing_data, f, indent=4)

    print(f"OTP data saved to {json_file}")
    return True


def CodeOTP(uri):
    parsed = urlparse(uri)
    query = parse_qs(parsed.query)
    secret = query.get("secret", [None])[0]

    if secret is None:
        return None
    else:
        totp = pyotp.TOTP(secret)
        return totp.now()


# TOTP/OTP utility functions
def generate_totp(secret: str) -> str:
    """Generate TOTP code from secret."""
    try:
        return pyotp.TOTP(secret).now()
    except Exception as e:
        print(f"Error generating TOTP: {e}")
        return None


def get_time_remaining() -> int:
    """Get seconds remaining until next token refresh."""
    return 30 - (int(time.time()) % 30)


def get_time_remaining_with_blink() -> str:
    """Get time remaining with blinking effect."""
    time_remaining = get_time_remaining()
    current_second = int(time.time())
    should_blink = current_second % 2 == 0

    if should_blink:
        return f"<span alpha='30%'>{time_remaining}s</span>"
    else:
        return f"{time_remaining}s"


def validate_base32_secret(secret: str) -> dict:
    """Validate and clean Base32 secret."""
    import base64
    import re

    try:
        # Clean up the secret - remove spaces, dashes, and convert to uppercase
        clean_secret = secret.replace(" ", "").replace("-", "").replace("_", "").upper()

        # Remove any non-base32 characters
        clean_secret = re.sub(r"[^A-Z2-7]", "", clean_secret)

        # Add padding if needed (Base32 requires padding to multiple of 8)
        while len(clean_secret) % 8 != 0:
            clean_secret += "="

        # Validate Base32 format
        try:
            base64.b32decode(clean_secret)
        except Exception as e:
            return {"success": False, "error": f"Invalid Base32 secret: {str(e)}"}

        # Test if the secret can generate a valid TOTP
        try:
            test_totp = pyotp.TOTP(clean_secret)
            test_code = test_totp.now()
            if not test_code or len(test_code) != 6:
                raise ValueError("Generated invalid TOTP code")
        except Exception as e:
            return {"success": False, "error": f"Cannot generate TOTP: {str(e)}"}

        return {"success": True, "secret": clean_secret}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


def parse_otpauth_uri(uri: str, account_name: str = "") -> dict:
    """Parse otpauth URI and extract account information."""
    try:
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
    except Exception as e:
        return {"success": False, "error": f"Error parsing otpauth URI: {str(e)}"}


def scan_qr_and_add_account(account_name: str, secrets_file_path: str) -> dict:
    """Scan QR code and add OTP account to secrets file."""
    try:
        # Capture QR code from screen
        screenshot_path = capture_selected_area()
        if not screenshot_path:
            return {"success": False, "error": "QR scan cancelled or failed"}

        # Decode QR code
        try:
            img = Image.open(screenshot_path)
            decoded_objects = decode(img)

            if not decoded_objects:
                return {
                    "success": False,
                    "error": "No QR code detected in selected area",
                }

            # Process the first QR code found
            qr_data = decoded_objects[0].data.decode("utf-8")
            print(f"QR Code detected: {qr_data}")

            if qr_data.startswith("otpauth://"):
                # Parse otpauth URI
                result = parse_otpauth_uri(qr_data, account_name)
                if not result["success"]:
                    return result

                # Load existing secrets
                secrets = {}
                if os.path.exists(secrets_file_path):
                    try:
                        with open(secrets_file_path, "r", encoding="utf-8") as f:
                            secrets = json.load(f)
                    except Exception as e:
                        print(f"Error loading secrets: {e}")

                # Add new account
                secrets[result["account_name"]] = {
                    "secret": result["secret"],
                    "issuer": result["issuer"],
                    "algorithm": result["algorithm"],
                    "digits": result["digits"],
                    "period": result["period"],
                }

                # Save secrets
                try:
                    os.makedirs(os.path.dirname(secrets_file_path), exist_ok=True)
                    with open(secrets_file_path, "w", encoding="utf-8") as f:
                        json.dump(secrets, f, indent=2)
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Error saving secrets: {str(e)}",
                    }

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
            else:
                return {"success": False, "error": "QR code is not an otpauth URI"}

        except Exception as e:
            return {"success": False, "error": f"Error processing QR code: {str(e)}"}

    except Exception as e:
        return {"success": False, "error": f"Error during QR scan: {str(e)}"}
