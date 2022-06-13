import logging
import logging.handlers
from enum import Enum
from typing import Union

from cerberus import Validator
from coloredlogs import ColoredFormatter

from getwvclone import config
from getwvclone.pssh_utils import parse_pssh


class APIAction(Enum):
    DISABLE_USER = "disable"
    DISABLE_USER_BULK = "disable_bulk"
    ENABLE_USER = "enable"
    KEY_COUNT = "keycount"
    USER_COUNT = "usercount"
    SEARCH = "search"


def construct_logger():
    logging.root.setLevel(config.ROOT_LOG_LEVEL)

    # ensure parent folders exist
    config.WVK_LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.WZ_LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # setup handlers
    # create a colored formatter for the console
    console_formatter = ColoredFormatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)

    # create a regular non-colored formatter for the log file
    file_formatter = logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)

    # create a handler for console logging
    stream = logging.StreamHandler()
    stream.setLevel(config.CONSOLE_LOG_LEVEL)
    stream.setFormatter(console_formatter)

    # configure werkzeug logger
    wzlogger = logging.getLogger("werkzeug")
    wzlogger.setLevel(logging.DEBUG)
    file_handler = logging.handlers.RotatingFileHandler(config.WZ_LOG_FILE_PATH, maxBytes=(1024 * 1024) * 5, backupCount=5)

    # create a regular non-colored formatter for the log file
    file_formatter = logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    wzlogger.addHandler(file_handler)
    wzlogger.addHandler(stream)

    # create a handler for file logging, 5 mb max size, with 5 backup files
    file_handler = logging.handlers.RotatingFileHandler(config.WVK_LOG_FILE_PATH, maxBytes=(1024 * 1024) * 5, backupCount=5)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(config.FILE_LOG_LEVEL)

    # construct the logger
    logger = logging.getLogger("getwvkeys")
    logger.addHandler(stream)
    logger.addHandler(file_handler)
    return logger


class CacheBase(object):
    def __init__(self, added_at: int, added_by: Union[str, None], license_url: Union[str, None]):
        self.added_at = added_at
        self.added_by = added_by
        self.license_url = license_url

    @staticmethod
    def from_dict(d: dict):
        (added_at, added_by, license_url) = (d["added_at"], d.get("added_by"), d.get("license_url"))
        return CacheBase(added_at, added_by, license_url)


class CachedKey(CacheBase):
    """
    Represents cached key information that contains a single key
    """

    def __init__(self, kid: str, added_at: int, added_by: Union[str, None], license_url: Union[str, None], key: str):
        super().__init__(added_at, added_by, license_url)
        self.kid = kid
        self.key = key

    @staticmethod
    def from_dict(d: dict):
        (kid, added_at, license_url, key) = (d["kid"], d["added_at"], d.get("license_url", None), d["key"])
        return CachedKey(kid, added_at, license_url, key)

    def to_json(self):
        return {"kid": self.kid, "added_at": self.added_at, "license_url": self.license_url, "key": self.key}


def extract_kid_from_pssh(pssh: str):
    logger = logging.getLogger("getwvkeys")
    try:
        parsed_pssh = parse_pssh(pssh)
        if len(parsed_pssh.key_ids) == 0:
            if len(parsed_pssh.data.key_ids) == 0:
                raise Exception("No key id found in pssh")
            elif len(parsed_pssh.data.key_ids) > 1:
                logger.warning("Multiple key ids found in pssh! {}".format(pssh))
                return parsed_pssh.data.key_ids
            else:
                return parsed_pssh.data.key_ids[0]
    except Exception as e:
        raise e


class Validators:
    def __init__(self) -> None:
        self.vinetrimmer_schema = {
            "method": {"required": True, "type": "string", "allowed": ["GetKeysX", "GetKeys", "GetChallenge"]},
            "params": {"required": False, "type": "dict"},
            "token": {"required": True, "type": "string"},
        }
        self.key_exchange_schema = {
            "cdmkeyresponse": {"required": True, "type": ["string", "binary"]},
            "encryptionkeyid": {"required": True, "type": ["string", "binary"]},
            "hmackeyid": {"required": True, "type": ["string", "binary"]},
            "session_id": {"required": True, "type": "string"},
        }
        self.keys_schema = {"cdmkeyresponse": {"required": True, "type": ["string", "binary"]}, "session_id": {"required": True, "type": "string"}}
        self.challenge_schema = {
            "init": {"required": True, "type": "string"},
            "cert": {"required": True, "type": "string"},
            "raw": {"required": True, "type": "boolean"},
            "licensetype": {"required": True, "type": "string", "allowed": ["OFFLINE", "STREAMING"]},
            "device": {"required": True, "type": "string"},
        }
        self.vinetrimmer_validator = Validator(self.vinetrimmer_schema)
        self.key_exchange_validator = Validator(self.key_exchange_schema)
        self.keys_validator = Validator(self.keys_schema)
        self.challenge_validator = Validator(self.challenge_schema)
