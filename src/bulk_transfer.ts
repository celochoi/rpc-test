import {ethers as e, parseEther} from "ethers";

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  const endpoint = '<~~~~>'
  const provider = new e.JsonRpcProvider(endpoint);
  const privateKey = '<~~~~>';
  const toAddress = '<~~~~>';
  const amount = parseEther('0.01');
  const delayMs = 3000;
  const loopCnt = 2
  const chainId = 11155420 // 11155420: op sepolia, 11155111: sepolia

  const wallet = new e.Wallet(privateKey, provider);
  for (let i = 0; i< loopCnt; i ++) {
    try {
      const nonce = await provider.getTransactionCount(wallet.address, 'pending');
      const tx = {
        to: toAddress,
        value: amount,
        nonce: nonce,
        gasLimit: 21000,
        gasPrice: 3000000,
        chainId: chainId,
      };

      const resp = await wallet.sendTransaction(tx)
      console.log(resp)

      await delay(delayMs)
    } catch (error) {
      console.error('트랜잭션 실패:', error);
    }
  }
}

main()