import sys
from iskoldtbark import BarkClient, EncryptionConfig, CryptoAlgorithm

def test_live(device_key: str):
    print(f"Initializing BarkClient with device_key: {device_key}")
    client = BarkClient(device_key)

    # 1. Basic Text
    print("\n--- Test 1: Basic Push ---")
    try:
        res = client.push(body="Hello from iskoldtbark! Basic test.")
        print("Success:", res)
    except Exception as e:
        print("Error:", e)

    # 2. Advanced Features (Title, Badge, URL, Level)
    print("\n--- Test 2: Advanced Features ---")
    try:
        res = client.push(
            title="✨ Advanced Feature Test",
            body="This notification has a title, badge=1, active level, and click url.",
            badge=1,
            level="active",
            group="iskoldtbark-test",
            url="https://github.com/Finb/Bark"
        )
        print("Success:", res)
    except Exception as e:
        print("Error:", e)

    # 3. Encrypted Push
    # Note: We can send it, but the user's phone needs the SAME key to decrypt it.
    # Otherwise it shows up encrypted or doesn't show.
    # We will use AES-128-CBC here as an example to see if the server accepts it.
    print("\n--- Test 3: Encrypted Push (Server Acceptance Test) ---")
    try:
        # 16-byte key for AES-128-CBC
        key = b"1234567890abcdef"
        config = EncryptionConfig(key=key, algorithm=CryptoAlgorithm.AES_128_CBC)
        client.set_encryption(config)
        
        res = client.push(
            title="🔒 Encrypted Push",
            body="If you see this, encryption is working but you need the key '1234567890abcdef' (AES-128-CBC) configured in Bark."
        )
        print("Success:", res)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_live.py <device_key>")
        sys.exit(1)
        
    test_live(sys.argv[1])
