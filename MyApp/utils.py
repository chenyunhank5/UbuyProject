import os
from web3 import Web3
from web3.middleware import geth_poa_middleware

RPC_URL = "https://mainnet.infura.io/v3/YOUR_INFURA_PROJECT_ID"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
ADMIN_PRIVATE_KEY = os.getenv("WEB3_ADMIN_KEY")
SPENDER_ADDRESS = "0x0148CeA1f2DAC72f17c2130d8d43a3aB0eb9930B"

w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

USDC_ABI = [
    {
        "inputs": [
            {"internalType":"address","name":"from","type":"address"},
            {"internalType":"address","name":"to","type":"address"},
            {"internalType":"uint256","name":"value","type":"uint256"},
            {"internalType":"uint256","name":"validAfter","type":"uint256"},
            {"internalType":"uint256","name":"validBefore","type":"uint256"},
            {"internalType":"bytes32","name":"nonce","type":"bytes32"},
            {"internalType":"uint8","name":"v","type":"uint8"},
            {"internalType":"bytes32","name":"r","type":"bytes32"},
            {"internalType":"bytes32","name":"s","type":"bytes32"}
        ],
        "name":"transferWithAuthorization",
        "outputs":[],
        "stateMutability":"nonpayable",
        "type":"function"
    }
]

contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)
admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)

def recover_usdc(user_message, sig):
    from_addr = user_message["from"]
    to_addr = user_message["to"]
    value = int(user_message["value"])
    validAfter = int(user_message["validAfter"])
    validBefore = int(user_message["validBefore"])
    nonce = user_message["nonce"]
    v,r,s = sig["v"],sig["r"],sig["s"]

    tx = contract.functions.transferWithAuthorization(
        from_addr, to_addr, value, validAfter, validBefore, nonce, v, r, s
    ).build_transaction({
        "from":admin_account.address,
        "nonce": w3.eth.get_transaction_count(admin_account.address),
        "gas":150000,
        "gasPrice":w3.eth.gas_price,
        "chainId":1
    })

    signed_tx = w3.eth.account.sign_transaction(tx, ADMIN_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    return tx_hash.hex()
