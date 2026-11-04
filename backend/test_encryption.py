from app.core.encryption import encrypt_value, decrypt_value

original = "234567890123"

encrypted = encrypt_value(original)
decrypted = decrypt_value(encrypted)

print("Original:", "XXXX XXXX " + original[-4:])
print("Encrypted:", encrypted[:20] + "...")
print("Decrypted:", "XXXX XXXX " + decrypted[-4:])

assert original == decrypted

print("Encryption test successful!")