import axios from 'axios';
import * as dotenv from 'dotenv';

// .env 파일 로드
dotenv.config();

// RPC 파라미터 상수 설정 (환경변수로 변경 가능)
const COMMITMENT = process.env.COMMITMENT || 'finalized';
const ENCODING = process.env.ENCODING || 'jsonParsed';
const TRANSACTION_DETAILS = process.env.TRANSACTION_DETAILS || 'full';
const MAX_SUPPORTED_TRANSACTION_VERSION = parseInt(process.env.MAX_SUPPORTED_TRANSACTION_VERSION || '0');
const REWARDS = process.env.REWARDS === 'true' ? true : false;

// 통계 수집용 인터페이스
interface SchedulerStats {
  totalGetBlockCalls: number;
  totalLatency: number;
  startBlock: number;
  endBlock: number;
  startTime: number;
  endTime: number;
  errors: number;
}

// 딜레이 함수
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 지정된 시간(분) 전 블록 계산 (솔라나는 약 400ms마다 블록 생성)
function getBlockFromMinutesAgo(currentSlot: number, minutes: number): number {
  // 솔라나는 약 400ms마다 블록이므로 1초에 2.5블록
  const seconds = minutes * 60;
  const blocksToGoBack = Math.floor(seconds / 0.4);
  return Math.max(0, currentSlot - blocksToGoBack);
}

// axios로 getSlot RPC 호출
async function getLatestSlot(rpcEndpoint: string): Promise<number> {
  const response = await axios.post(rpcEndpoint, {
    jsonrpc: '2.0',
    id: 1,
    method: 'getSlot',
    params: [{ commitment: COMMITMENT }]
  });
  return response.data.result;
}

// axios로 getBlock RPC 호출 (요청된 파라미터 사용)
async function getBlockWithAxios(rpcEndpoint: string, slot: number): Promise<void> {
  await axios.post(rpcEndpoint, {
    jsonrpc: '2.0',
    id: 1,
    method: 'getBlock',
    params: [
      slot,
      {
        commitment: COMMITMENT,
        encoding: ENCODING,
        transactionDetails: TRANSACTION_DETAILS,
        maxSupportedTransactionVersion: MAX_SUPPORTED_TRANSACTION_VERSION,
        rewards: REWARDS
      }
    ]
  });
}

// 벌크로 블록 정보 가져오기 (axios 버전)
async function getBlocksBulk(
  rpcEndpoint: string,
  slots: number[],
  stats: SchedulerStats
): Promise<void> {
  const promises = slots.map(async (slot) => {
    const startTime = Date.now();
    try {
      await getBlockWithAxios(rpcEndpoint, slot);
      const endTime = Date.now();
      stats.totalLatency += (endTime - startTime);
      stats.totalGetBlockCalls++;
    } catch (error) {
      const endTime = Date.now();
      stats.totalLatency += (endTime - startTime);
      stats.totalGetBlockCalls++;
      stats.errors++;
      console.warn(`블록 ${slot} 조회 실패:`, error);
    }
  });

  await Promise.all(promises);
}

// 메인 스케줄러 함수
async function runSolanaScheduler(): Promise<void> {
  console.log('🚀 솔라나 입금 스케줄러 테스트 시작 (axios 버전)');
  
  // RPC 엔드포인트 설정 (환경변수로 변경 가능)
  const baseRpcEndpoint = process.env.SOLANA_RPC_ENDPOINT || 'https://api.mainnet-beta.solana.com';
  
  // JSON-RPC 경로 설정 (환경변수로 변경 가능)
  const JSONRPC_PATH = process.env.JSONRPC_PATH || 'jsonrpc-http';
  
  // 쿼리 파라미터 설정 (환경변수로 변경 가능)
  const RAW_UPSTREAM = process.env.RAW_UPSTREAM || 'shared_solana_mainnet_agave_full_http';
  const ACCOUNT_ID = process.env.ACCOUNT_ID || '10';
  const PROJECT_ID = process.env.PROJECT_ID || '100';
  const CU = process.env.CU || '1';
  
  // 벌크 사이즈 설정 (환경변수로 변경 가능)
  const BULK_SIZE = parseInt(process.env.BULK_SIZE || '10');
  
  // 추적 시작 시간 설정 (환경변수로 변경 가능)
  const MINUTES_AGO = parseInt(process.env.MINUTES_AGO || '30');
  
  // 쿼리 파라미터를 포함한 완전한 RPC 엔드포인트 구성
  const rpcEndpoint = `${baseRpcEndpoint}/${JSONRPC_PATH}?raw_upstream=${RAW_UPSTREAM}&account_id=${ACCOUNT_ID}&project_id=${PROJECT_ID}&cu=${CU}`;
  
  console.log(`📡 기본 RPC 엔드포인트: ${baseRpcEndpoint}`);
  console.log(`🛣️  JSON-RPC 경로: ${JSONRPC_PATH}`);
  console.log(`🔧 쿼리 파라미터:`);
  console.log(`   - raw_upstream: ${RAW_UPSTREAM}`);
  console.log(`   - account_id: ${ACCOUNT_ID}`);
  console.log(`   - project_id: ${PROJECT_ID}`);
  console.log(`   - cu: ${CU}`);
  console.log(`📦 벌크 사이즈: ${BULK_SIZE}개`);
  console.log(`⏰ 추적 시작 시간: ${MINUTES_AGO}분 전부터`);
  console.log(`🔧 RPC 파라미터:`);
  console.log(`   - commitment: ${COMMITMENT}`);
  console.log(`   - encoding: ${ENCODING}`);
  console.log(`   - transactionDetails: ${TRANSACTION_DETAILS}`);
  console.log(`   - maxSupportedTransactionVersion: ${MAX_SUPPORTED_TRANSACTION_VERSION}`);
  console.log(`   - rewards: ${REWARDS}`);
  console.log(`📡 최종 RPC 엔드포인트: ${rpcEndpoint}`);

  const stats: SchedulerStats = {
    totalGetBlockCalls: 0,
    totalLatency: 0,
    startBlock: 0,
    endBlock: 0,
    startTime: Date.now(),
    endTime: 0,
    errors: 0
  };

  try {
    // 1. 최신 블록 번호 조회 (getSlot RPC)
    console.log('📊 최신 블록 번호 조회 중...');
    const latestSlot = await getLatestSlot(rpcEndpoint);
    console.log(`✅ 최신 블록: ${latestSlot}`);

    // 지정된 시간(분) 전 블록부터 시작
    const startSlot = getBlockFromMinutesAgo(latestSlot, MINUTES_AGO);
    stats.startBlock = startSlot;
    stats.endBlock = latestSlot;
    
    console.log(`🕰️  ${MINUTES_AGO}분 전 블록부터 시작: ${startSlot}`);
    console.log(`📈 따라갈 블록 수: ${latestSlot - startSlot + 1}개`);

    let currentSlot = startSlot;

    // 2. 내가 따라온 블록이 최신 블록번호까지 도달했다면 종료
    while (currentSlot <= latestSlot) {
      // 3. 아직 못따라갔다면 getBlock RPC로 블록 정보 가져오기 (벌크로)
      const endSlot = Math.min(currentSlot + BULK_SIZE - 1, latestSlot);
      const slotsToFetch = [];

      for (let slot = currentSlot; slot <= endSlot; slot++) {
        slotsToFetch.push(slot);
      }

      console.log(`🔄 블록 ${currentSlot} ~ ${endSlot} 조회 중... (${slotsToFetch.length}개)`);
      
      const bulkStartTime = Date.now();
      await getBlocksBulk(rpcEndpoint, slotsToFetch, stats);
      const bulkEndTime = Date.now();
      const bulkDuration = bulkEndTime - bulkStartTime;
      
      console.log(`✅ 블록 ${currentSlot} ~ ${endSlot} 조회 완료 - 소요시간: ${bulkDuration}ms (평균: ${(bulkDuration / slotsToFetch.length).toFixed(1)}ms/블록)`);

      currentSlot = endSlot + 1;

      // await sleep(50);
    }

    stats.endTime = Date.now();

    // 결과 출력
    console.log('\n📊 === 솔라나 스케줄러 테스트 결과 (axios 버전) ===');
    console.log(`⏱️  총 소요시간: ${((stats.endTime - stats.startTime) / 1000).toFixed(2)}초`);
    console.log(`🔢 총 getBlock 호출 횟수: ${stats.totalGetBlockCalls}회`);
    console.log(`📦 테스트 블록 범위: ${stats.startBlock} ~ ${stats.endBlock} (${stats.endBlock - stats.startBlock + 1}개 블록)`);
    console.log(`⚡ 평균 getBlock RPC 레이턴시: ${(stats.totalLatency / stats.totalGetBlockCalls).toFixed(2)}ms`);
    console.log(`❌ 에러 발생 횟수: ${stats.errors}회`);
    console.log(`✅ 성공률: ${(((stats.totalGetBlockCalls - stats.errors) / stats.totalGetBlockCalls) * 100).toFixed(2)}%`);

  } catch (error) {
    console.error('💥 스케줄러 실행 중 오류 발생:', error);
    process.exit(1);
  }
}

// 스크립트 실행
if (require.main === module) {
  runSolanaScheduler().catch(error => {
    console.error('💥 치명적 오류:', error);
    process.exit(1);
  });
}

export { runSolanaScheduler };
