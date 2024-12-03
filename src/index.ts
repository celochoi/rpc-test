import {ethers as e, FetchRequest} from "ethers";
import safeJsonStringify from "safe-json-stringify"

const sleep = (ms: number) => {
  return new Promise(resolve => {
    setTimeout(resolve, ms)
  })
}

const RPC_TIMEOUT_MS = 10000

// Must set finishBlockNumber or targetRunningTimeMs
type TestConfig = {
  startTimeMs: number;
  startBlockNumber?: number;
  finishBlockNumber?: number;
  targetRunningTimeMs?: number;
  rpcUrl: string;
  batchSize: number;
};

type TestResult = {
  idx: number;
  calls: number;
  failCalls: number;
  retryCalls: number;
  finishTimeMs: number;
  startBlockNumber: number;
  finishBlockNumber: number;
  totalCallMs: number;
  rpcUrl: string;
};

type Failure = {
  reason: string,
  timestamp: number,
};

async function processBlock(idx: number, cfg: TestConfig, provider: e.JsonRpcProvider, blockNumber: number): Promise<Failure[]> {
  const now = Date.now()
  console.log(`${now} - Scheduler ${idx} start to process block: ${blockNumber}`)
  let fails: Failure[] = []

  // Get txs from block
  const block = await provider.getBlock(blockNumber)
  if (!block) {
    throw Error(`Can't find ${blockNumber} block`)
  }
  const txs = block.transactions

  // Get transaction receipts
  const promises = []
  for (let i = 0; i < txs.length; i++) {
    // if (i == 0) {
    //   promises.push(provider.send('debug_traceTransaction', [txs[i], {"tracer": "callTracer"}]).catch((err: any) => {
    //     console.log(`debug error (scheduler ${idx}) (${txs[ii]}): ${err.toString()} (${Date.now()}) (err: ${safeJsonStringify(err)})`)
    //     throw err
    //   }))
    // }
    const ii = i
    const requestTime = Date.now()
    promises.push(provider.getTransactionReceipt(txs[i]).catch((err: any) => {
      console.log(`error (scheduler ${idx}) (${txs[ii]}): ${err.toString()} (req_at:${requestTime}, res_at:${Date.now()}) (err: ${safeJsonStringify(err)})`)
      throw err
    }))
  }

  const receipts = await Promise.allSettled(promises)
  for (let i = 0; i < receipts.length; i++) {
    if (receipts[i].status == 'rejected') {
      const rejectReason = (receipts[i] as any).reason.toString() as string
      fails.push({reason: rejectReason, timestamp: Date.now()});
    }
  }

  // if (fails.length > 0) {
  //   throw Error(`Scheduler ${idx} failed to process ${blockNumber} block (fails: ${fails.length})`)
  // }

  const finishTime = Date.now()
  console.log(`${finishTime} - Scheduler ${idx} processed block: ${blockNumber}, processedTimeSec: ${(finishTime- now) / 1000}, fails: ${fails.length}`)
  return fails
}

async function startScheduler(idx: number, cfg: TestConfig): Promise<TestResult> {
  const fetch = new e.FetchRequest(cfg.rpcUrl)
  fetch.timeout = RPC_TIMEOUT_MS

  let totalReqs = 0
  let totalCalls = 0
  let totalCallMs = 0
  let failCalls = 0
  let timeoutCalls = 0
  let retryCalls = 0

  fetch.preflightFunc = async (req) => {
    req.setHeader("startTimeMs", Date.now())
    // req.setHeader("host", "polygon-mainnet.nodit.io")
    totalReqs++
    return req
  }

  fetch.processFunc = async (req, resp) => {
    const startTimeMs = Number(req.getHeader("startTimeMs"))
    const callTimeMs = Date.now() - startTimeMs
    totalCalls++
    totalCallMs += callTimeMs
    return resp
  }

  fetch.retryFunc = async (req, res, attempt) => {
    return false
    if (res.statusCode == 429) {
      if (attempt <= 3) {
        console.log(`Scheduler (${idx}): try retry (attempt: ${attempt})`)
        retryCalls++
        return true
      }
    }
    return false
  }

  // const provider = new e.JsonRpcProvider(fetch, undefined, { batchMaxSize: 1, cacheTimeout: 1 })
  const provider = new e.JsonRpcProvider(fetch, undefined, {polling: true, batchMaxSize: 1, cacheTimeout: 0})
  const startBlockNumber = cfg.startBlockNumber ?? await provider.getBlockNumber()
  const finishBlockNumber = cfg.finishBlockNumber
  let currBlockNumber = startBlockNumber

  while (true) {

    if (finishBlockNumber != undefined && currBlockNumber > finishBlockNumber) {
      console.log(`Reached to finish block number! stop test`)
      break;
    }

    const loopStartTime = Date.now()
    if (cfg.targetRunningTimeMs != undefined && (loopStartTime - cfg.startTimeMs) >= cfg.targetRunningTimeMs) {
      console.log(`Reached to target running time! stop test`)
      // if targetRunningTimeMs is set, check running time
      break
    }

    let prevLatestBlockNumber = 0

    try {
      // Check new block
      const latestBlockNumber = await provider.getBlockNumber()
      if (prevLatestBlockNumber != 0 && prevLatestBlockNumber > latestBlockNumber) {
        console.log(`chain rollback! prevLatestBlockNumber: ${prevLatestBlockNumber}, latestBlockNumber: ${latestBlockNumber}`)
        process.exit(1)
      }
      prevLatestBlockNumber = latestBlockNumber

      if (currBlockNumber >= latestBlockNumber) {
        // console.log(`Reached to latest block! (latestBlockNumber: ${latestBlockNumber})`)
        await sleep(200)
        continue
      }

      const batchSize = Math.min(cfg.batchSize, latestBlockNumber - currBlockNumber)
      const promises: Promise<Failure[]>[] = []
      for (let batchIdx = 0; batchIdx < batchSize; batchIdx++) {
        promises.push(processBlock(idx, cfg, provider, currBlockNumber + batchIdx + 1))
      }

      const results = await Promise.all(promises)
      let isFailed = false
      for (let batchIdx = 0; batchIdx < batchSize; batchIdx++) {
        for (let i = 0; i < results[batchIdx].length; i++) {
          console.log(`scheduler ${idx} failed to process block ${currBlockNumber}. reason: ${results[batchIdx][i].reason}, timestamp: ${results[batchIdx][i].timestamp}`)
          failCalls++
          if (results[batchIdx][i].reason.includes("timeout")) {
            timeoutCalls++
          }
          isFailed = true
        }
      }

      if (isFailed) {
        // console.log(`Retry batch. currBlockNumber: ${currBlockNumber}, batch_size: ${batchSize}, totalReqs: ${totalReqs}, totalCalls: ${totalCalls}, totalFails: ${failCalls}, timeoutCalls: ${timeoutCalls}, loopTime: ${(Date.now() - loopStartTime) / 1000}, rps: ${totalCalls / ((Date.now() - cfg.startTimeMs) / 1000)}`)
        // continue
        console.log(`Failed but skip. currBlockNumber: ${currBlockNumber}, batch_size: ${batchSize}, totalReqs: ${totalReqs}, totalCalls: ${totalCalls}, totalFails: ${failCalls}, timeoutCalls: ${timeoutCalls}, loopTime: ${(Date.now() - loopStartTime) / 1000}, rps: ${totalCalls / ((Date.now() - cfg.startTimeMs) / 1000)}`)
      }

      console.log(`Batch Finished. currBlockNumber: ${currBlockNumber}, batch_size: ${batchSize}, totalReqs: ${totalReqs}, totalCalls: ${totalCalls}, totalFails: ${failCalls}, timeoutCalls: ${timeoutCalls}, loopTime: ${(Date.now() - loopStartTime) / 1000}, rps: ${totalCalls / ((Date.now() - cfg.startTimeMs) / 1000)}`)
      currBlockNumber += batchSize
    } catch (err: any) {
      console.log(`scheduler ${idx} catch err (${currBlockNumber}): ${err.toString()}`)
    }
  }
  return {
    idx,
    calls: totalCalls,
    failCalls,
    retryCalls,
    finishTimeMs: Date.now(),
    startBlockNumber,
    finishBlockNumber: currBlockNumber - 1,
    totalCallMs,
    rpcUrl: cfg.rpcUrl,
  }
}

async function main() {
  process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = String(0)

  const startTimeMs = Date.now()
  const noditPrdKey = ''
  const noditDevKey = ''

  // Config
  const configs: TestConfig[] = [
    {
      startTimeMs,
      targetRunningTimeMs: 30 * 60 * 1000,
      rpcUrl: "https://arbitrum-mainnet.nodit-dev.net/" + noditDevKey, // DEV
      batchSize: 10
    }
  ]

  const promises: Promise<TestResult>[] = []

  for (let i = 0; i < configs.length; i++) {
    promises.push(startScheduler(i, configs[i]))
  }

  const results: TestResult[] = await Promise.all(promises)

  for (let i = 0; i < results.length; i++) {
    const elapsedTimeSecs = (results[i].finishTimeMs - startTimeMs) / 1000
    console.log(`Scheduler: ${results[i].idx}`)
    console.log(`RPC URL: ${results[i].rpcUrl}`)
    console.log(`Start block: ${results[i].startBlockNumber}`)
    console.log(`Finish block: ${results[i].finishBlockNumber}`)
    console.log(`Total calls: ${results[i].calls}`)
    console.log(`Fail calls: ${results[i].failCalls}`)
    console.log(`Retry calls: ${results[i].retryCalls}`)
    console.log(`Test time: ${elapsedTimeSecs} secs`)
    console.log(`Avg call time: ${results[i].totalCallMs / results[i].calls} ms (${results[i].totalCallMs / results[i].calls / 1000} sec)`)
    console.log(`Total call time: ${results[i].totalCallMs} ms`)
    console.log(`RPS: ${results[i].calls / elapsedTimeSecs}`)
    console.log('\n')
  }
}

main()
