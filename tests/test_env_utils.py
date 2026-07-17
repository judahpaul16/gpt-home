def test_get_env_reads_environ_when_no_dotenv(load_source, monkeypatch, tmp_path):
    env_utils = load_source("env_utils_iso", "tools/env_utils.py")
    monkeypatch.setattr(env_utils, "ENV_FILE_PATH", tmp_path / "absent.env")
    monkeypatch.setenv("MY_KEY", "from_environ")
    assert env_utils.get_env("MY_KEY") == "from_environ"


def test_get_env_returns_default_when_missing(load_source, monkeypatch, tmp_path):
    env_utils = load_source("env_utils_iso", "tools/env_utils.py")
    monkeypatch.setattr(env_utils, "ENV_FILE_PATH", tmp_path / "absent.env")
    monkeypatch.delenv("MISSING", raising=False)
    assert env_utils.get_env("MISSING", "fallback") == "fallback"


def test_get_env_prefers_dotenv_over_environ(load_source, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MY_KEY=from_file\n")
    env_utils = load_source("env_utils_iso", "tools/env_utils.py")
    monkeypatch.setattr(env_utils, "ENV_FILE_PATH", env_file)
    monkeypatch.setenv("MY_KEY", "from_environ")
    assert env_utils.get_env("MY_KEY") == "from_file"


def test_get_env_all_mixes_sources(load_source, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("A=one\n")
    env_utils = load_source("env_utils_iso", "tools/env_utils.py")
    monkeypatch.setattr(env_utils, "ENV_FILE_PATH", env_file)
    monkeypatch.setenv("B", "two")
    monkeypatch.delenv("C", raising=False)
    assert env_utils.get_env_all("A", "B", "C") == {"A": "one", "B": "two", "C": None}
