import bcrypt
# Replace with your correctly stored bcrypt hash from the database
stored_hashed_password = b"$2b$12$XzG1jPYmDqfBrUV8A9ebAeLqMD10AWu2SzR6Q2K7Gn2yz8cO9e6nq"  

input_password = "password123"  # User-provided password
print (input_password.encode())
if bcrypt.checkpw(input_password.encode(), stored_hashed_password):
    print("✅ Password matches!")
else:
    print("❌ Incorrect password.")