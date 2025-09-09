import {ethers as e, parseEther} from "ethers";

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  const endpoint = ''
  // const endpoint = 'http://61.111.3.57:18016'
  const provider = new e.JsonRpcProvider(endpoint);
  const privateKey = '';
  const toAddress = '';
  const amount = parseEther('0.0001');
  const delayMs = 200;
  const loopCnt = 10;
  const chainId = 11155111 // 11155420: op sepolia, 11155111: sepolia

  const wallet = new e.Wallet(privateKey, provider);
  for (let i = 0; i< loopCnt; i ++) {
    try {
      const nonce = await provider.getTransactionCount(wallet.address, 'pending');
      const txObject = {
        to: toAddress,
        value: amount,
        nonce: nonce,
        gasLimit: 21000,
        gasPrice: 3000000,
        chainId: chainId,
      };

      const resp = await wallet.sendTransaction(txObject)
      console.log("Transaction sent:", resp)

      await delay(200)

      // Immediately try to get the transaction by hash and check if nonce increased
      try {
        // Call both functions simultaneously
        const [tx, newNonce] = await Promise.all([
          provider.getTransaction(resp.hash),
          provider.getTransactionCount(wallet.address, 'pending')
        ]);

        // Check if transaction is found
        if (tx) {
          console.log("Transaction immediately found:", tx);
        } else {
          console.log("Transaction not immediately found in the blockchain");
        }

        // Check if nonce increased
        console.log("Original nonce:", nonce);
        console.log("New nonce:", newNonce);
        if (newNonce > nonce) {
          console.log("Nonce increased after transaction");
        } else {
          console.log("Nonce did not increase after transaction");
        }
      } catch (error) {
        console.error("Error retrieving transaction or nonce:", error);
      }

      await delay(delayMs)
    } catch (error) {
      console.error('트랜잭션 실패:', error);
    }
  }
}

main()
