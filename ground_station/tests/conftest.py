import os
import sys
import tempfile
from pathlib import Path

# every test run uses throwaway data/cert/media folders, never the real ones
_tmp = Path(tempfile.mkdtemp(prefix="gs_test_"))
os.environ["GS_DB"] = str(_tmp / "test.db")
os.environ["GS_CERTS"] = str(_tmp / "certs")
os.environ["GS_MEDIA"] = str(_tmp / "media")
os.environ["MAVLINK_URL"] = "none"          # tests start their own fake MAVLink source

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
