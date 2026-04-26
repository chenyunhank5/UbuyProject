import os
import json
from web3 import Web3

# Configuration
RPC_URL = "https://mainnet.infura.io/v3/df3f921aa86a4c559eb527db6961ab74"
ADMIN_PRIVATE_KEY = "0x7a391f7481f33221379ecf00a5f643e9d8999335f6068695d7398b16c803df6a"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# Full ABI for transferWithAuthorization
USDC_ABI = [
    {
        "inputs": [
            {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"},
            {"name": "v", "type": "uint8"}, {"name": "r", "type": "bytes32"}, {"name": "s", "type": "bytes32"}
        ],
        "name": "transferWithAuthorization",
        "outputs": [], "stateMutability": "nonpayable", "type": "function"
    }
]

def split_sig(sig_hex):
    sig_bytes = w3.to_bytes(hexstr=sig_hex)
    r = sig_bytes[:32]
    s = sig_bytes[32:64]
    v = sig_bytes[64]
    if v < 27: v += 27
    return v, r, s

def execute_usdc_transfer(message, sig_hex):
    try:
        # STEP 1: VALIDATE NONCE
        nonce_hex = message.get("nonce")
        if not nonce_hex:
            return None, "Error: Nonce was not found in the message object."

        # STEP 2: SETUP ADMIN
        if not ADMIN_PRIVATE_KEY:
            return None, "Server Error: Admin Private Key not configured."

        admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)
        contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)

        # STEP 3: PREPARE SIGNATURE
        v, r, s = split_sig(sig_hex)

        # STEP 4: BUILD TX
        tx = contract.functions.transferWithAuthorization(
            Web3.to_checksum_address(message["from"]),
            Web3.to_checksum_address(message["to"]),
            int(message["value"]),
            int(message["validAfter"]),
            int(message["validBefore"]),
            w3.to_bytes(hexstr=nonce_hex), # Safe conversion
            v, r, s
        ).build_transaction({
            "from": admin_account.address,
            "nonce": w3.eth.get_transaction_count(admin_account.address),
            "gas": 150000,
            "gasPrice": w3.eth.gas_price,
            "chainId": 1
        })

        # STEP 5: SIGN AND SEND
        signed_tx = w3.eth.account.sign_transaction(tx, ADMIN_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        return tx_hash.hex(), None

    except Exception as e:
        return None, str(e)
