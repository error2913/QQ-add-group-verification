import json
import os
import logging

logger = logging.getLogger(__name__)

# 获取当前模块所在目录
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "LEVEL_THRESHOLD": 5,
    "WS_URL": "ws://127.0.0.1:8080",
    "VERIFY_TIMEOUT": 60,
    "MASTER_LIST": [1234567]
}

class Config:
    _instance = None
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._config = DEFAULT_CONFIG.copy()
            cls._instance._init_config()
        return cls._instance
    
    def _init_config(self):
        """初始化配置文件"""
        if not os.path.exists(CONFIG_PATH):
            self._save_config()
        else:
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._config.update(json.load(f))
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"配置文件加载失败，使用默认配置: {str(e)}")
                self._config = DEFAULT_CONFIG.copy()
                self._save_config()
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
        except IOError as e:
            logger.error(f"配置文件保存失败: {str(e)}")
    
    @property
    def level_threshold(self) -> int:
        return self._config["LEVEL_THRESHOLD"]
    
    @property
    def ws_url(self) -> str:
        return self._config["WS_URL"]
    
    @property
    def verify_timeout(self) -> int:
        return self._config["VERIFY_TIMEOUT"]
    
    @property
    def master_list(self) -> list:
        return self._config["MASTER_LIST"]

config = Config()