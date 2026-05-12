import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_log = logging.getLogger('ScreenShift')

LOG_FILENAME = 'screenshift.log'


def setup(log_dir: Path) -> None:
    """Attach a rotating file handler to the root ScreenShift logger.
    Safe to call multiple times — subsequent calls are no-ops."""
    if _log.handlers:
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(
            log_dir / LOG_FILENAME,
            maxBytes=512_000,
            backupCount=2,
            encoding='utf-8',
        )
        h.setFormatter(logging.Formatter(
            '%(asctime)s  %(levelname)-7s  %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        _log.setLevel(logging.INFO)
        _log.addHandler(h)
    except Exception:
        pass  # never crash the app over a logging failure


def get() -> logging.Logger:
    return _log
