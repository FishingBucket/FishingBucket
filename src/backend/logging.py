import datetime
import logging
import traceback
from pathlib import Path
from typing import Callable, Any

from ..context import config, context


def get_log_file(postfix: str = "") -> Path:
    return config().log_directory / f"{context().startup_time.strftime(config().log_time_format)}{postfix}.log"

def start_log(name: str, postfix: str = "") -> tuple[Callable[..., None], Callable[[BaseException], None]]:
    logger = logging.getLogger(name + postfix)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(get_log_file(postfix), encoding="utf-8")
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)

    def info(*data: Any):
        msg = f"{datetime.datetime.now() - context().startup_time} [{name}{postfix}] " + ' '.join(str(d) for d in data)
        print(msg)
        logger.info(msg)

    def err(e: BaseException):
        msg = f"{datetime.datetime.now() - context().startup_time} [{name}{postfix}] " + "".join(traceback.format_exception(type(e), e, e.__traceback__))
        print(msg)
        logger.error(msg)

    return info, err
