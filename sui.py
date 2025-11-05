import urllib.request
import urllib.error
import json
import base64
import time
import sys
from datetime import datetime
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# 내부 Sui 노드들
RPC_URLS = [
    "http://192.168.34.90:9000",
    "http://192.168.34.85:9000",
    "http://192.168.34.94:9000",
    "http://192.168.34.122:9000",
    "http://192.168.66.35:9000",
    "http://192.168.66.36:9000",
]

TRANSACTIONS_STORE_URL = "https://transactions.sui.io/mainnet"
REQUEST_TIMEOUT = 30
LOOP_DELAY = 0.1

class Colors:
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

def base58_decode(s: str) -> bytes:
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    decoded = 0
    multi = 1
    for char in reversed(s):
        if char not in alphabet:
            raise ValueError(f"Invalid Base58 character: {char}")
        decoded += multi * alphabet.index(char)
        multi *= 58

    hex_str = hex(decoded)[2:]
    if len(hex_str) % 2:
        hex_str = '0' + hex_str
    return bytes.fromhex(hex_str)

def encode_digest_to_base64url(digest_base58: str) -> str:
    try:
        digest_bytes = base58_decode(digest_base58)
        encoded = base64.urlsafe_b64encode(digest_bytes).decode().rstrip('=')
        return encoded
    except Exception as e:
        log(f"Digest 인코딩 실패: {e}", "ERROR")
        log(f"Original digest: {digest_base58}", "ERROR")
        raise

def encode_checkpoint_to_base64url(checkpoint_num) -> str:
    try:
        import struct
        if isinstance(checkpoint_num, str):
            checkpoint_num = int(checkpoint_num)
        checkpoint_bytes = struct.pack('<Q', checkpoint_num)
        encoded = base64.urlsafe_b64encode(checkpoint_bytes).decode().rstrip('=')
        return encoded
    except Exception as e:
        log(f"Checkpoint 인코딩 실패: {checkpoint_num} ({type(checkpoint_num)})", "ERROR")
        raise

def get_latest_transaction_from_node(rpc_url: str) -> Optional[dict]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "suix_queryTransactionBlocks",
        "params": [
            {
                "filter": None,
                "options": {
                    "showInput": True,
                    "showEffects": True,
                    "showEvents": True
                }
            },
            None,
            1,
            True
        ]
    }

    try:
        start_time = time.time()
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            rpc_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode('utf-8'))

        elapsed = time.time() - start_time

        if 'result' not in result or 'data' not in result['result']:
            return None

        transactions = result['result']['data']
        if transactions:
            tx = transactions[0]
            checkpoint = tx.get('checkpoint', 0)
            if isinstance(checkpoint, str):
                checkpoint = int(checkpoint) if checkpoint else 0
            return {
                'transaction': tx,
                'checkpoint': checkpoint,
                'rpc_url': rpc_url,
                'elapsed': elapsed
            }
        return None

    except Exception as e:
        return None

def get_latest_transaction_from_all_nodes() -> Optional[dict]:
    log(f"\n{len(RPC_URLS)}개 노드에서 동시에 최신 트랜잭션 조회 중...")
    start_time = time.time()

    results = []

    with ThreadPoolExecutor(max_workers=len(RPC_URLS)) as executor:
        future_to_url = {executor.submit(get_latest_transaction_from_node, url): url for url in RPC_URLS}

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result:
                    log(f"  ✓ {url}", "SUCCESS")
                    log(f"    Checkpoint: {result['checkpoint']}, Digest: {result['transaction']['digest'][:16]}..., 응답시간: {result['elapsed']:.2f}초")
                    results.append(result)
                else:
                    log(f"  ✗ {url} - 실패", "WARNING")
            except Exception as e:
                log(f"  ✗ {url} - 에러: {e}", "WARNING")

    total_elapsed = time.time() - start_time
    log(f"  총 소요 시간: {total_elapsed:.2f}초 (병렬 처리)", "INFO")

    if not results:
        log("모든 노드 조회 실패!", "ERROR")
        return None

    latest = max(results, key=lambda x: x['checkpoint'])

    log(f"\n가장 최신 트랜잭션 선택:", "INFO")
    log(f"  노드: {latest['rpc_url']}", "INFO")
    log(f"  Checkpoint: {latest['checkpoint']}", "INFO")
    log(f"  Digest: {latest['transaction']['digest']}", "INFO")

    return latest['transaction']

def fetch_single_url(url: str, type_code: str, type_name: str) -> dict:
    start_time = time.time()

    try:
        req = urllib.request.Request(url, method='GET')

        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            elapsed = time.time() - start_time
            status_code = response.status
            content = response.read()

            return {
                'success': True,
                'type_code': type_code,
                'type_name': type_name,
                'url': url,
                'status_code': status_code,
                'content': content,
                'elapsed': elapsed
            }

    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        return {
            'success': False,
            'type_code': type_code,
            'type_name': type_name,
            'url': url,
            'status_code': e.code,
            'error': 'HTTPError',
            'elapsed': elapsed
        }

    except urllib.error.URLError as e:
        elapsed = time.time() - start_time
        error_type = 'Timeout' if 'timed out' in str(e.reason).lower() or 'timeout' in str(e.reason).lower() else 'URLError'
        return {
            'success': False,
            'type_code': type_code,
            'type_name': type_name,
            'url': url,
            'error': error_type,
            'reason': str(e.reason),
            'elapsed': elapsed
        }

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            'success': False,
            'type_code': type_code,
            'type_name': type_name,
            'url': url,
            'error': type(e).__name__,
            'reason': str(e),
            'elapsed': elapsed
        }

def test_transactions_store(tx_data: dict, test_num: int, total: int) -> bool:
    digest = tx_data['digest']
    checkpoint = tx_data.get('checkpoint')

    log(f"\n{'='*80}")
    log(f"테스트 [{test_num}/{total}]", "INFO")
    log(f"  Digest: {digest}", "INFO")
    log(f"  Checkpoint: {checkpoint} (type: {type(checkpoint).__name__})", "INFO")

    encoded_digest = encode_digest_to_base64url(digest)

    data_types = [
        ("tx", "Transaction", encoded_digest),
        ("fx", "Effects", encoded_digest),
        ("tx2c", "Tx→Checkpoint", encoded_digest),
        ("evtx", "Events", encoded_digest),
    ]

    if checkpoint is not None and checkpoint != "":
        try:
            encoded_checkpoint = encode_checkpoint_to_base64url(checkpoint)
            data_types.extend([
                ("cs", "Checkpoint Summary", encoded_checkpoint),
                ("cc", "Checkpoint Contents", encoded_checkpoint),
            ])
        except Exception as e:
            log(f"  Checkpoint 인코딩 실패, cs/cc 스킵: {e}", "WARNING")
    else:
        log(f"  Checkpoint 정보 없음, cs/cc 스킵", "INFO")

    log(f"\ntransactions.sui.io에 병렬로 {len(data_types)}개 요청 시작...", "INFO")
    start_time = time.time()

    urls_to_fetch = []
    for type_code, type_name, encoded in data_types:
        url = f"{TRANSACTIONS_STORE_URL}/{encoded}/{type_code}"
        urls_to_fetch.append((url, type_code, type_name))

    results = []
    with ThreadPoolExecutor(max_workers=len(urls_to_fetch)) as executor:
        future_to_data = {
            executor.submit(fetch_single_url, url, type_code, type_name): (url, type_code, type_name)
            for url, type_code, type_name in urls_to_fetch
        }

        for future in as_completed(future_to_data):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                log(f"  ✗ 예외 발생: {e}", "ERROR")

    total_elapsed = time.time() - start_time
    log(f"모든 요청 완료 - 총 소요 시간: {total_elapsed:.2f}초 (병렬)", "INFO")

    for result in results:
        type_name = result['type_name']
        url = result['url']
        elapsed = result['elapsed']

        log(f"\n  [{type_name}]")
        log(f"  URL: {url}")

        if result['success']:
            size = len(result['content'])
            preview = result['content'][:20].hex() if len(result['content']) >= 20 else result['content'].hex()
            log(f"  ✓ 성공! ({result['status_code']}) - {elapsed:.2f}초 - {size:,} bytes", "SUCCESS")
            log(f"  데이터 미리보기 (hex): {preview}", "SUCCESS")

            if elapsed > 5:
                log(f"  ⚠ 느린 응답 감지: {elapsed:.2f}초", "WARNING")

        else:
            if result.get('error') == 'Timeout':
                log(f"\n  ✗✗✗ 타임아웃 발생! ✗✗✗", "CRITICAL")
                log(f"  설정 타임아웃: {REQUEST_TIMEOUT}초", "CRITICAL")
                log(f"  실제 경과 시간: {elapsed:.2f}초", "CRITICAL")
                log(f"  URL: {url}", "CRITICAL")
                log(f"  Digest: {digest}", "CRITICAL")
                log(f"  Data Type: {type_name} ({result['type_code']})", "CRITICAL")
                log(f"\n  {'*'*60}", "CRITICAL")
                log(f"  *** 30초 Hang 문제 재현! ***", "CRITICAL")
                log(f"  {'*'*60}\n", "CRITICAL")
                return False

            elif result.get('error') == 'HTTPError':
                status_code = result['status_code']
                if status_code == 404:
                    log(f"  ○ 데이터 없음 ({status_code}) - {elapsed:.2f}초 (정상)", "INFO")
                elif status_code == 403:
                    log(f"  ✗ 접근 거부! ({status_code}) - {elapsed:.2f}초", "ERROR")
                    return False
                elif 500 <= status_code < 600:
                    log(f"  ✗ 서버 에러! ({status_code}) - {elapsed:.2f}초", "ERROR")
                    return False
                else:
                    log(f"  ? HTTP 에러 ({status_code}) - {elapsed:.2f}초", "WARNING")
            else:
                log(f"  ✗ {result.get('error', 'Unknown')}: {result.get('reason', 'N/A')} - {elapsed:.2f}초", "ERROR")
                return False

    return True

def main():
    log(f"\n{'='*80}", "INFO")
    log("Sui multi_get_transaction_blocks 재현 테스트", "INFO")
    log("내부 노드 조회 & transactions.sui.io 병렬 처리", "INFO")
    log(f"{'='*80}\n", "INFO")

    log(f"설정:", "INFO")
    log(f"  - RPC 노드 수: {len(RPC_URLS)} (병렬 조회)")
    for idx, url in enumerate(RPC_URLS, 1):
        log(f"    {idx}. {url}")
    log(f"  - Transactions Store: {TRANSACTIONS_STORE_URL}")
    log(f"  - Request Timeout: {REQUEST_TIMEOUT}초")
    log(f"  - Loop Delay: {LOOP_DELAY}초\n")

    iteration = 0
    success_count = 0

    try:
        while True:
            iteration += 1
            log(f"\n{'#'*80}", "INFO")
            log(f"반복 #{iteration} 시작", "INFO")
            log(f"{'#'*80}", "INFO")

            tx_data = get_latest_transaction_from_all_nodes()
            if not tx_data:
                log(f"\n트랜잭션 조회 실패! 테스트 중단", "CRITICAL")
                return 1

            success = test_transactions_store(tx_data, 1, 1)

            if not success:
                log(f"\n{'!'*80}", "CRITICAL")
                log(f"에러 발생! 테스트 즉시 중단", "CRITICAL")
                log(f"{'!'*80}\n", "CRITICAL")
                log(f"최종 통계:", "INFO")
                log(f"  - 총 반복: {iteration}")
                log(f"  - 성공한 트랜잭션 테스트: {success_count}")
                return 1

            success_count += 1

            log(f"\n반복 #{iteration} 완료 - 모든 트랜잭션 정상", "SUCCESS")
            log(f"현재 통계 - 성공: {success_count}", "INFO")

            time.sleep(LOOP_DELAY)
            
    except KeyboardInterrupt:
        log(f"\n\n사용자 중단 (Ctrl+C)", "WARNING")
        log(f"\n최종 통계:", "INFO")
        log(f"  - 총 반복: {iteration}")
        log(f"  - 성공한 트랜잭션 테스트: {success_count}")
        return 0

if __name__ == "__main__":
    sys.exit(main())