import urllib.request
import urllib.error
import json
import base64
import time
import sys
from datetime import datetime
from typing import Optional

# 설정
RPC_URL = "https://fullnode.mainnet.sui.io:443"
TRANSACTIONS_STORE_URL = "https://transactions.sui.io/mainnet"
REQUEST_TIMEOUT = 10  # 초
LOOP_DELAY = 2  # 각 반복 사이 대기 시간 (초)

class Colors:
    """터미널 색상"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def log(message: str, level: str = "INFO"):
    """색상이 있는 로그 출력"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    colors = {
        "INFO": Colors.CYAN,
        "SUCCESS": Colors.GREEN,
        "WARNING": Colors.YELLOW,
        "ERROR": Colors.RED,
        "CRITICAL": f"{Colors.RED}{Colors.BOLD}"
    }
    color = colors.get(level, Colors.END)
    print(f"{color}[{timestamp}] [{level}] {message}{Colors.END}")

def encode_digest_to_base64url(digest_hex: str) -> str:
    """트랜잭션 digest를 base64-url 인코딩"""
    digest_bytes = bytes.fromhex(digest_hex)
    encoded = base64.urlsafe_b64encode(digest_bytes).decode().rstrip('=')
    return encoded

def get_latest_transactions(limit: int = 5) -> Optional[list]:
    """최신 트랜잭션 digest 목록 조회 - 실패 시 즉시 종료"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "suix_queryTransactionBlocks",
        "params": [
            {
                "filter": None,
                "options": {
                    "showInput": False,
                    "showEffects": False,
                    "