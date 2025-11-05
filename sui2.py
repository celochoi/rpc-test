#!/usr/bin/env python3
import json
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 설정
RPC_URLS = [
    "http://192.168.34.90:9000",
    "http://192.168.34.85:9000",
    "http://192.168.34.94:9000",
    "http://192.168.34.122:9000",
    "http://192.168.66.35:9000",
    "http://192.168.66.36:9000"
]
REQUEST_TIMEOUT = 30
LOOP_DELAY = 0.1

def rpc_call(url, method, params, timeout=REQUEST_TIMEOUT):
    """RPC 호출"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))

def get_checkpoint_txs(url):
    """노드에서 최신 체크포인트의 모든 트랜잭션 가져오기"""
    try:
        # 최신 체크포인트 번호
        result = rpc_call(url, "sui_getLatestCheckpointSequenceNumber", [])
        if 'result' not in result:
            return {'url': url, 'success': False, 'error': f'No result'}

        checkpoint = result['result']

        # 체크포인트 상세 정보 (트랜잭션 다이제스트 포함)
        cp_result = rpc_call(url, "sui_getCheckpoint", [str(checkpoint)])

        if 'result' not in cp_result or 'transactions' not in cp_result['result']:
            return {'url': url, 'success': False, 'error': 'No transactions in checkpoint'}

        digests = cp_result['result']['transactions']

        if not digests:
            return {'url': url, 'success': False, 'error': 'Empty digests'}

        return {
            'url': url,
            'checkpoint': checkpoint,
            'digests': digests,
            'count': len(digests),
            'success': True
        }
    except Exception as e:
        return {
            'url': url,
            'success': False,
            'error': str(e)
        }

def multi_get_tx_on_node(url, digests):
    """특정 노드에서 sui_multiGetTransactionBlocks 호출"""
    start = time.time()
    try:
        result = rpc_call(url, "sui_multiGetTransactionBlocks", [
            digests,
            {
                "showInput": True,
                "showRawInput": False,
                "showEffects": True,
                "showEvents": False,
                "showObjectChanges": False,
                "showBalanceChanges": True
            }
        ])
        elapsed = time.time() - start

        if 'result' not in result:
            return {
                'url': url,
                'elapsed': elapsed,
                'success': False,
                'error': f'No result in response'
            }

        return {
            'url': url,
            'elapsed': elapsed,
            'success': True,
            'status': 'OK',
            'count': len(result['result'])
        }
    except urllib.error.URLError as e:
        elapsed = time.time() - start
        if hasattr(e, 'reason') and 'timed out' in str(e.reason):
            return {
                'url': url,
                'elapsed': elapsed,
                'success': False,
                'error': 'TIMEOUT'
            }
        return {
            'url': url,
            'elapsed': elapsed,
            'success': False,
            'error': str(e)
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            'url': url,
            'elapsed': elapsed,
            'success': False,
            'error': str(e)
        }

def main():
    print(f"🚀 Sui MultiGetTransactionBlocks 테스트 시작")
    print(f"📡 노드 수: {len(RPC_URLS)}")
    print(f"📦 최신 체크포인트의 모든 트랜잭션 조회")
    print(f"⏱️  타임아웃: {REQUEST_TIMEOUT}초")
    print(f"🔄 루프 딜레이: {LOOP_DELAY}초\n")

    iteration = 0

    while True:
        iteration += 1
        print(f"\n{'='*80}")
        print(f"🔄 Iteration #{iteration} - {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        # 1단계: 모든 노드에서 최신 체크포인트의 모든 트랜잭션 가져오기 (병렬)
        print(f"\n📥 1단계: 최신 체크포인트의 모든 트랜잭션 조회 중...")
        with ThreadPoolExecutor(max_workers=len(RPC_URLS)) as executor:
            futures = {executor.submit(get_checkpoint_txs, url): url for url in RPC_URLS}
            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result['success']:
                    print(f"  ✅ {result['url']}: checkpoint={result['checkpoint']}, txs={result['count']}개")
                else:
                    print(f"  ❌ {result['url']}: {result['error']}")

        # 가장 최신 체크포인트의 트랜잭션들 찾기
        successful_results = [r for r in results if r['success']]
        if not successful_results:
            print("❌ 모든 노드에서 최신 트랜잭션 조회 실패!")
            time.sleep(LOOP_DELAY)
            continue

        latest = max(successful_results, key=lambda x: x['checkpoint'])
        digests = latest['digests']

        print(f"\n🎯 최신 체크포인트: {latest['checkpoint']}, 트랜잭션 수: {len(digests)}개")
        print(f"   첫 다이제스트: {digests[0][:32]}...")
        if len(digests) > 1:
            print(f"   마지막 다이제스트: {digests[-1][:32]}...")

        # 2단계: 모든 노드에 sui_multiGetTransactionBlocks 호출 (병렬)
        print(f"\n📤 2단계: 모든 노드에 sui_multiGetTransactionBlocks 호출 중...")
        with ThreadPoolExecutor(max_workers=len(RPC_URLS)) as executor:
            futures = {executor.submit(multi_get_tx_on_node, url, digests): url for url in RPC_URLS}

            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    print(f"  ✅ {result['url']}: {result['status']} ({result['elapsed']:.2f}초, {result['count']}개)")
                else:
                    print(f"  ❌ {result['url']}: {result['error']} ({result['elapsed']:.2f}초)")
                    if result['error'] == 'TIMEOUT':
                        print(f"\n🚨 타임아웃 발생! 노드: {result['url']}")
                        print(f"⏱️  경과 시간: {result['elapsed']:.2f}초")
                        print(f"📦 조회 시도한 트랜잭션 수: {len(digests)}개")
                        return

        time.sleep(LOOP_DELAY)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  사용자가 중단했습니다.")
    except Exception as e:
        print(f"\n\n💥 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()