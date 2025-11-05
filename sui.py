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
                    "showEvents": False
                }
            },
            None,
            limit,
            True  # descending order (최신부터)
        ]
    }
    
    try:
        log(f"RPC 요청 중...")
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            RPC_URL,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        if 'result' not in result or 'data' not in result['result']:
            log(f"예상치 못한 RPC 응답 구조", "ERROR")
            log(f"응답: {result}", "ERROR")
            return None
        
        transactions = result['result']['data']
        digests = [tx['digest'] for tx in transactions]
        log(f"트랜잭션 {len(digests)}개 조회 완료", "SUCCESS")
        return digests
        
    except urllib.error.URLError as e:
        if hasattr(e, 'reason'):
            if 'timed out' in str(e.reason):
                log(f"RPC 타임아웃 발생!", "ERROR")
            else:
                log(f"RPC 연결 실패: {e.reason}", "ERROR")
        else:
            log(f"RPC 요청 실패: {e}", "ERROR")
        return None
    except Exception as e:
        log(f"예상치 못한 에러: {type(e).__name__}: {e}", "ERROR")
        return None

def test_transactions_store(digest: str, encoded: str, test_num: int, total: int) -> bool:
    """
    transactions.sui.io에서 트랜잭션 데이터 조회 테스트
    
    Returns:
        True: 성공 또는 404 (정상)
        False: 타임아웃 또는 에러 (비정상) - 즉시 종료
    """
    data_types = [
        ("tx", "Transaction"),
        ("fx", "Effects"),
        ("tx2c", "Tx→Checkpoint"),
    ]
    
    log(f"\n{'='*80}")
    log(f"테스트 [{test_num}/{total}] - Digest: {digest[:16]}...", "INFO")
    log(f"Encoded: {encoded[:32]}...")
    
    for type_code, type_name in data_types:
        url = f"{TRANSACTIONS_STORE_URL}/{encoded}/{type_code}"
        log(f"\n  [{type_name}] 요청 중...")
        log(f"  URL: {url}")
        
        start_time = time.time()
        
        try:
            req = urllib.request.Request(url, method='GET')
            
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                elapsed = time.time() - start_time
                status_code = response.status
                content = response.read()
                
                if status_code == 200:
                    size = len(content)
                    log(f"  ✓ 성공! ({status_code}) - {elapsed:.2f}초 - {size:,} bytes", "SUCCESS")
                else:
                    log(f"  ? 예상치 못한 상태 코드 ({status_code}) - {elapsed:.2f}초", "WARNING")
                
                # 응답 시간 경고
                if elapsed > 5:
                    log(f"  ⚠ 느린 응답 감지: {elapsed:.2f}초", "WARNING")
                    
        except urllib.error.HTTPError as e:
            elapsed = time.time() - start_time
            status_code = e.code
            
            if status_code == 404:
                log(f"  ○ 데이터 없음 ({status_code}) - {elapsed:.2f}초 (정상)", "INFO")
            elif status_code == 403:
                log(f"  ✗ 접근 거부! ({status_code}) - {elapsed:.2f}초", "ERROR")
                log(f"  응답: {e.read().decode('utf-8', errors='ignore')[:500]}", "ERROR")
                return False
            elif 500 <= status_code < 600:
                log(f"  ✗ 서버 에러! ({status_code}) - {elapsed:.2f}초", "ERROR")
                log(f"  응답: {e.read().decode('utf-8', errors='ignore')[:500]}", "ERROR")
                return False
            else:
                log(f"  ? HTTP 에러 ({status_code}) - {elapsed:.2f}초", "WARNING")
                
        except urllib.error.URLError as e:
            elapsed = time.time() - start_time
            
            if hasattr(e, 'reason'):
                if 'timed out' in str(e.reason).lower() or 'timeout' in str(e.reason).lower():
                    log(f"\n  ✗✗✗ 타임아웃 발생! ✗✗✗", "CRITICAL")
                    log(f"  설정 타임아웃: {REQUEST_TIMEOUT}초", "CRITICAL")
                    log(f"  실제 경과 시간: {elapsed:.2f}초", "CRITICAL")
                    log(f"  URL: {url}", "CRITICAL")
                    log(f"  Digest: {digest}", "CRITICAL")
                    log(f"  Encoded Digest: {encoded}", "CRITICAL")
                    log(f"  Data Type: {type_name} ({type_code})", "CRITICAL")
                    log(f"\n  {'*'*60}", "CRITICAL")
                    log(f"  *** 30초 Hang 문제 재현 가능성 높음! ***", "CRITICAL")
                    log(f"  {'*'*60}\n", "CRITICAL")
                    return False
                else:
                    log(f"  ✗ 연결 실패! - {elapsed:.2f}초", "ERROR")
                    log(f"  에러: {e.reason}", "ERROR")
                    log(f"  URL: {url}", "ERROR")
                    return False
            else:
                log(f"  ✗ URL 에러! - {elapsed:.2f}초", "ERROR")
                log(f"  에러: {e}", "ERROR")
                return False
                
        except Exception as e:
            elapsed = time.time() - start_time
            log(f"  ✗ 예상치 못한 에러! - {elapsed:.2f}초", "ERROR")
            log(f"  에러 타입: {type(e).__name__}", "ERROR")
            log(f"  에러 내용: {e}", "ERROR")
            log(f"  URL: {url}", "ERROR")
            import traceback
            log(f"  스택 트레이스:\n{traceback.format_exc()}", "ERROR")
            return False
    
    return True

def main():
    """메인 실행 함수"""
    log(f"\n{'='*80}", "INFO")
    log("Sui Transactions Store 연속 테스트 시작", "INFO")
    log("표준 라이브러리만 사용 (urllib)", "INFO")
    log(f"{'='*80}\n", "INFO")
    
    log(f"설정:", "INFO")
    log(f"  - RPC URL: {RPC_URL}")
    log(f"  - Transactions Store: {TRANSACTIONS_STORE_URL}")
    log(f"  - Request Timeout: {REQUEST_TIMEOUT}초")
    log(f"  - Loop Delay: {LOOP_DELAY}초")
    log(f"  - Retry: 없음 (실패 시 즉시 종료)\n")
    
    iteration = 0
    success_count = 0
    
    try:
        while True:
            iteration += 1
            log(f"\n{'#'*80}", "INFO")
            log(f"반복 #{iteration} 시작", "INFO")
            log(f"{'#'*80}", "INFO")
            
            # 최신 트랜잭션 조회
            digests = get_latest_transactions(limit=3)
            if not digests:
                log(f"\n{'!'*80}", "CRITICAL")
                log(f"트랜잭션 조회 실패! 테스트 중단", "CRITICAL")
                log(f"{'!'*80}\n", "CRITICAL")
                log(f"최종 통계:", "INFO")
                log(f"  - 총 반복: {iteration}")
                log(f"  - 성공한 트랜잭션 테스트: {success_count}")
                return 1
            
            # 각 트랜잭션에 대해 transactions.sui.io 테스트
            for idx, digest in enumerate(digests, 1):
                encoded = encode_digest_to_base64url(digest)
                
                success = test_transactions_store(digest, encoded, idx, len(digests))
                
                if not success:
                    log(f"\n{'!'*80}", "CRITICAL")
                    log(f"에러 발생! 테스트 즉시 중단", "CRITICAL")
                    log(f"{'!'*80}\n", "CRITICAL")
                    log(f"최종 통계:", "INFO")
                    log(f"  - 총 반복: {iteration}")
                    log(f"  - 성공한 트랜잭션 테스트: {success_count}")
                    log(f"  - 실패한 트랜잭션: {digest[:16]}...")
                    return 1
                
                success_count += 1
                
                # 다음 트랜잭션 테스트 전 잠시 대기
                if idx < len(digests):
                    time.sleep(0.5)
            
            log(f"\n반복 #{iteration} 완료 - 모든 트랜잭션 정상", "SUCCESS")
            log(f"현재 통계 - 성공: {success_count}", "INFO")
            
            # 다음 반복 전 대기
            log(f"\n{LOOP_DELAY}초 대기...\n", "INFO")
            time.sleep(LOOP_DELAY)
            
    except KeyboardInterrupt:
        log(f"\n\n사용자 중단 (Ctrl+C)", "WARNING")
        log(f"\n최종 통계:", "INFO")
        log(f"  - 총 반복: {iteration}")
        log(f"  - 성공한 트랜잭션 테스트: {success_count}")
        return 0

if __name__ == "__main__":
    sys.exit(main())