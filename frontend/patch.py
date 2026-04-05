import re
path = r'c:/Users/Karth/Documents/agent projects/coingecko/frontend/index.html'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

new_abi = '''const USDC_ABI = [
  { "inputs": [ { "internalType": "address", "name": "spender", "type": "address" }, { "internalType": "uint256", "name": "amount", "type": "uint256" } ], "name": "approve", "outputs": [ { "internalType": "bool", "name": "", "type": "bool" } ], "stateMutability": "nonpayable", "type": "function" },
  { "inputs": [ { "internalType": "address", "name": "owner", "type": "address" }, { "internalType": "address", "name": "spender", "type": "address" } ], "name": "allowance", "outputs": [ { "internalType": "uint256", "name": "", "type": "uint256" } ], "stateMutability": "view", "type": "function" },
  { "inputs": [ { "internalType": "address", "name": "account", "type": "address" } ], "name": "balanceOf", "outputs": [ { "internalType": "uint256", "name": "", "type": "uint256" } ], "stateMutability": "view", "type": "function" },
  { "inputs": [], "name": "decimals", "outputs": [ { "internalType": "uint8", "name": "", "type": "uint8" } ], "stateMutability": "view", "type": "function" },
  { "inputs": [ { "internalType": "address", "name": "to", "type": "address" }, { "internalType": "uint256", "name": "amount", "type": "uint256" } ], "name": "mint", "outputs": [], "stateMutability": "nonpayable", "type": "function" }
];'''

text = re.sub(r'const USDC_ABI = \[.*?\];', new_abi, text, flags=re.DOTALL)

text = text.replace('function Header({ wallet, onConnect, onDisconnect }) {', 'function Header({ wallet, onConnect, onDisconnect, onMint }) {')

old_btn = """              <button onClick={onDisconnect} style={{
                padding: '6px 12px', borderRadius: 8,
                background: 'transparent', border: '1px solid var(--border)',
                color: 'var(--txt3)', cursor: 'pointer', fontSize: 12,
              }}>Disconnect</button>"""
new_btn = """              <button onClick={onMint} style={{
                padding: '6px 12px', borderRadius: 8,
                background: 'var(--gold-bg)', border: '1px solid rgba(245,158,11,.3)',
                color: 'var(--gold)', cursor: 'pointer', fontSize: 12, fontWeight: 600
              }}>Faucet</button>
              <button onClick={onDisconnect} style={{
                padding: '6px 12px', borderRadius: 8,
                background: 'transparent', border: '1px solid var(--border)',
                color: 'var(--txt3)', cursor: 'pointer', fontSize: 12,
              }}>Disconnect</button>"""

text = text.replace(old_btn, new_btn)

app_conn = "      function disconnectWallet() {"
mint_logic = '''
      async function mintUsdc() {
        if (!wallet || !signer) return;
        try {
            push('Minting 10,000 Dummy USDC...', 'info');
            const u = usc(signer);
            const d = await u.decimals();
            const tx = await u.mint(wallet, ethers.parseUnits('10000', d));
            await tx.wait();
            push('10,000 USDC Faucet Minted! 🎉', 'ok');
            setRefreshAt(Date.now());
        } catch(e) {
            push('Faucet failed: ' + (e.reason || e.message), 'err');
        }
      }

      function disconnectWallet() {'''
text = text.replace(app_conn, mint_logic)

text = text.replace('<Header wallet={wallet} onConnect={connectWallet} onDisconnect={disconnectWallet} />', '<Header wallet={wallet} onConnect={connectWallet} onDisconnect={disconnectWallet} onMint={mintUsdc} />')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print("done")
