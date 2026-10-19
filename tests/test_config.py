"""Config loading: example file, validation, CLI-selected markets.

Run:  python3 -m pytest tests/  (or  python3 tests/test_config.py)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from entropy_arb.config import ConfigError, load_config  # noqa: E402

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLE = os.path.join(ROOT, "config.example.yaml")
NO_ENV = os.path.join(tempfile.gettempdir(), "entropy-arb-no-such.env")
# Every config written by write_tmp() lands here, and relative CSV paths
# resolve against this dir (never the cwd the tests run from).
TMP = tempfile.gettempdir()


def write_tmp(text: str) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    f.write(text)
    f.close()
    return f.name


def anchored(*parts: str) -> str:
    """Expected path: *parts* under the temp dir the configs are written to."""
    return os.path.join(TMP, *parts)


MINIMAL = """
thresholds:
  midline_bps: 5.0
  upper_bps: 4.0
  lower_bps: 3.0
"""


def load(yaml_text: str, symbol="SNDK", hedge="lighter-rh"):
    return load_config(write_tmp(yaml_text), NO_ENV,
                       symbol=symbol, hedge_venue=hedge)


def test_example_config_loads():
    cfg = load_config(EXAMPLE, NO_ENV,
                      symbol="SNDK", hedge_venue="lighter-rh")
    assert cfg.symbol == "SNDK"
    assert cfg.entropy.kind == "hl" and cfg.entropy.hl_dex == "io"
    assert cfg.hedge_venue == "lighter-rh"
    assert cfg.hedge.kind == "lighter"
    assert cfg.hedge.lighter_profile.chain_id == 466324
    assert cfg.entropy.symbol == "SNDK" and cfg.hedge.symbol == "SNDK"
    assert (cfg.recorder_enabled
            and cfg.recorder_csv == os.path.join(
                ROOT, "logs", "minutes-lighter-rh-SNDK.csv"))
    assert cfg.trades_csv == os.path.join(ROOT, "logs", "trades-SNDK.csv")
    assert cfg.dashboard and cfg.log_file


def test_minimal_defaults():
    cfg = load(MINIMAL, hedge="lighter")
    assert cfg.midline_bps == 5.0 and cfg.upper_bps == 4.0 and cfg.lower_bps == 3.0
    assert cfg.hedge.label == "LIGHTER"
    assert cfg.hedge.lighter_profile.chain_id == 304
    assert cfg.take_fraction == 0.5          # defaults kick in
    assert cfg.recorder_enabled is True
    assert cfg.recorder_csv == anchored("logs", "minutes-lighter-SNDK.csv")


def test_recorder_selects_distinct_csv_for_each_hedge():
    paths = """
recorder:
  csv_by_hedge:
    lighter: data/mainnet.csv
    lighter-rh: data/robinhood.csv
    tradexyz: data/tradexyz.csv
"""
    for hedge, name in (("lighter", "mainnet"),
                        ("lighter-rh", "robinhood"),
                        ("tradexyz", "tradexyz")):
        # relative to the CONFIG's dir, not the cwd the test runs from
        assert load(MINIMAL + paths, hedge=hedge).recorder_csv == anchored(
            "data", f"{name}-SNDK.csv")


def test_legacy_single_recorder_csv_remains_supported():
    cfg = load(MINIMAL + "\nrecorder:\n  csv: logs/legacy.csv\n")
    assert cfg.recorder_csv == anchored("logs", "legacy-SNDK.csv")


def test_csv_paths_are_distinct_for_each_symbol():
    sndk = load(MINIMAL, symbol="SNDK", hedge="lighter")
    hype = load(MINIMAL, symbol="HYPE", hedge="lighter")
    assert sndk.recorder_csv == anchored("logs", "minutes-lighter-SNDK.csv")
    assert hype.recorder_csv == anchored("logs", "minutes-lighter-HYPE.csv")
    assert sndk.trades_csv == anchored("logs", "trades-SNDK.csv")
    assert hype.trades_csv == anchored("logs", "trades-HYPE.csv")


def test_custom_csv_paths_are_scoped_by_symbol():
    cfg = load(MINIMAL + "\nlogging:\n  trades_csv: data/fills.csv\n",
               symbol="HYPE")
    assert cfg.trades_csv == anchored("data", "fills-HYPE.csv")


def test_relative_paths_ignore_the_process_cwd():
    # A config in dir X must write to X/logs even when started from elsewhere:
    # a forgotten `cd` once scattered CSVs across the filesystem.
    cfg_dir = tempfile.mkdtemp()
    path = os.path.join(cfg_dir, "c.yaml")
    with open(path, "w") as fh:
        fh.write(MINIMAL)
    elsewhere = tempfile.mkdtemp()
    was = os.getcwd()
    os.chdir(elsewhere)
    try:
        cfg = load_config(path, NO_ENV, symbol="SNDK", hedge_venue="lighter")
    finally:
        os.chdir(was)
    assert cfg.recorder_csv == os.path.join(
        cfg_dir, "logs", "minutes-lighter-SNDK.csv")
    assert cfg.trades_csv == os.path.join(cfg_dir, "logs", "trades-SNDK.csv")


def test_data_paths_expand_vars_and_home():
    os.environ["ENTROPY_ARB_TEST_LOGS"] = "/var/tmp/entropy-arb-test"
    try:
        cfg = load(MINIMAL +
                   "\nlogging:\n  trades_csv: $ENTROPY_ARB_TEST_LOGS/t.csv\n",
                   symbol="SNDK", hedge="lighter")
        assert cfg.trades_csv == "/var/tmp/entropy-arb-test/t-SNDK.csv"
    finally:
        del os.environ["ENTROPY_ARB_TEST_LOGS"]


def test_recorder_csv_paths_must_be_complete_and_distinct():
    expect_error(MINIMAL + """
recorder:
  csv_by_hedge:
    lighter: data/mainnet.csv
""", "recorder.csv_by_hedge must define a path for 'lighter-rh'")
    expect_error(MINIMAL + """
recorder:
  csv_by_hedge:
    lighter: data/shared.csv
    lighter-rh: data/shared.csv
    tradexyz: data/tradexyz.csv
""", "paths must be distinct")


def test_tradexyz_hedge():
    cfg = load(MINIMAL, hedge="tradexyz")
    assert cfg.hedge.kind == "hl" and cfg.hedge.hl_dex == "xyz"
    assert cfg.hedge.label == "XYZ"


def expect_error(yaml_text: str, needle: str, **kw):
    try:
        load(yaml_text, **kw)
    except ConfigError as e:
        assert needle in str(e), f"{needle!r} not in {e}"
        return
    raise AssertionError(f"expected ConfigError containing {needle!r}")


def test_unknown_key_rejected():
    expect_error(MINIMAL + "\nthresholdz:\n  x: 1\n",
                 "unknown config key 'thresholdz'")
    expect_error(MINIMAL + "\nsizing:\n  take_fractionn: 0.5\n",
                 "sizing.take_fractionn")


def test_markets_no_longer_config_keys():
    # symbol / hedge_venue moved to --symbol / --hedge: leftovers in the
    # YAML must fail loudly, not silently override the flags
    expect_error("symbol: SNDK\n" + MINIMAL, "unknown config key 'symbol'")
    expect_error("hedge_venue: tradexyz\n" + MINIMAL,
                 "unknown config key 'hedge_venue'")


def test_bad_cli_markets():
    expect_error(MINIMAL, "--hedge", hedge="binance")
    expect_error(MINIMAL, "--symbol", symbol="")


def test_missing_thresholds():
    expect_error("recorder:\n  enabled: true\n", "thresholds.")


def test_nonpositive_band():
    expect_error("thresholds:\n"
                 "  midline_bps: 5\n  upper_bps: 0\n  lower_bps: 3\n",
                 "must be > 0")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name:40s} OK")
