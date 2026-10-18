import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["LOGGER_DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["LOGGER_DATA_DIR"] = _tmp
