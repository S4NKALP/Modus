import contextlib
import tempfile
import webbrowser
from urllib.parse import quote

from fabric.core.service import Service
from fabric.utils import logger, os

from utils.functions import run_command

DEFAULT_UPLOADER = "https://litterbox.catbox.moe/resources/internals/api.php"


class GoogleLens(Service):
    """Service to capture region and search with Google Lens."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get_initial():
        if GoogleLens._instance is None:
            GoogleLens._instance = GoogleLens()
        return GoogleLens._instance

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def capture_region(self, dest_path):
        from utils.functions import find_binary

        # Check for dependencies
        if not find_binary("grim"):
            raise RuntimeError("grim not found - please install it")

        if not find_binary("slurp"):
            raise RuntimeError("slurp not found - please install it")

        try:
            # Select region
            result = run_command(["slurp"], timeout=60)
            if result.returncode != 0:
                if result.returncode == 1:
                    raise RuntimeError("Selection cancelled")
                raise RuntimeError(f"Failed to select region: {result.stderr}")

            geom = (
                result.stdout.strip()
                if isinstance(result.stdout, str)
                else result.stdout.decode("utf-8").strip()
            )

            if not geom:
                raise RuntimeError("No region selected")

            # Capture selected region
            capture_result = run_command(["grim", "-g", geom, dest_path], timeout=60)
            if capture_result.returncode != 0:
                raise RuntimeError(f"Failed to capture region: {capture_result.stderr}")

        except Exception as e:
            raise RuntimeError(f"Failed to capture region: {e}") from e

    def upload_file(self, uploader_url, file_path):
        cmd = [
            "curl",
            "-sS",
            "--max-time",
            "15",
            "-F",
            "reqtype=fileupload",
            "-F",
            "time=1h",
            "-F",
            f"fileToUpload=@{file_path}",
            uploader_url,
        ]
        result = run_command(cmd, timeout=20)
        if result.returncode != 0:
            raise RuntimeError(f"Upload failed: {result.stderr}")

        url_resp = (
            result.stdout.strip()
            if isinstance(result.stdout, str)
            else result.stdout.decode("utf-8").strip()
        )

        # catbox.moe returns the URL directly
        if (
            not url_resp
            or not isinstance(url_resp, str)
            or not url_resp.startswith("http")
        ):
            raise RuntimeError(f"Invalid response from uploader: {url_resp}")

        return url_resp

    def search(self):
        tmp = tempfile.NamedTemporaryFile(
            prefix="google_lens_", suffix=".png", delete=False
        )
        tmp_path = tmp.name
        tmp.close()

        try:
            # Capture region
            logger.info("Select a region...")
            self.capture_region(tmp_path)

            # Upload
            logger.info("Uploading...")
            uploaded_url = self.upload_file(DEFAULT_UPLOADER, tmp_path)
            logger.info(f"Uploaded: {uploaded_url}")

            # Open in Lens
            lens_url = f"https://lens.google.com/uploadbyurl?url={quote(uploaded_url, safe='')}"
            logger.info("Opening Google Lens...")
            webbrowser.open(lens_url)

        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            # Cleanup
            if os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
