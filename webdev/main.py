import os
import sys
import json
import base64
import bittensor as bt
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from storage.validator.encryption import encrypt_data, decrypt_data_with_private_key
from storage.api import StoreUserAPI, RetrieveUserAPI, get_query_api_axons, store, retrieve
from webdev.database import startup, get_database, get_user, create_user, get_server_wallet, get_metagraph
from webdev.database import Token, TokenData, User, UserInDB, store_file_metadata, get_user_metadata
from webdev.database import file_exists, get_cid_by_filename, get_cid_metadata, get_user_stats, get_hotkeys_by_cid


os.environ['ACCESS_TOKEN_EXPIRE_MINUTES']='15'
os.environ['ALGORITHM']='HS256'
# Load the env configuration
load_dotenv()

# Init the redis db
startup()
redis_db = get_database()

# Get metagraph for this session
# TODO: get this in a periodic update loop
metagraph = get_metagraph()

# Initialize FastAPI app
app = FastAPI()

# Initialize Password Context for hashing and verifying
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Wallet to use for querying the network (we whitelist ourselves)
server_wallet = get_server_wallet()

# Singleton storage handler
store_handler = StoreUserAPI(server_wallet)

# Singleton retriever handler
retrieve_handler = RetrieveUserAPI(server_wallet)

# OAuth2 and JWT Token Management
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class UserInfo(BaseModel):
    username: str
    password: str

# Managmeent of Passwords
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def generate_seed():
    return pwd_context.hash(os.urandom(32))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    print('Creating access...')
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv("SECRET_KEY"), algorithm=os.getenv("ALGORITHM"))
    return encoded_jwt

# User Authentication Functions
async def get_current_user(token: str = Depends(oauth2_scheme)):
    print('Getting current user...')
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        user = get_user(username)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

# User Registration Endpoint
@app.post("/register/")
async def register_user(user_info: UserInfo):
    username=user_info.username
    password=user_info.password
    if get_user(username) is not None:
        raise HTTPException(status_code=400, detail="Username already registered")

    # Generate wallet. Use `username` for coldkey and `default` hotkey
    user_wallet = bt.wallet(name=username)
    user_wallet.create(coldkey_use_password=False, hotkey_use_password=False)

    print(user_wallet)

    # Hash the password and generate a seed for the user
    hashed_password = get_password_hash(password)
    seed = generate_seed()
    name = user_wallet.name
    hotkey = user_wallet.hotkey.ss58_address
    mnemonic = user_wallet.coldkey.mnemonic

    if mnemonic is None:
        raise HTTPException(status_code=500, detail="Mnemonic not generated")

    user = UserInDB(
        username = username, 
        hashed_password = hashed_password, 
        seed = seed, 
        wallet_name = name, 
        wallet_hotkey = hotkey,
        wallet_mnemonic = mnemonic
    )
    create_user(user)
    return {"message": f"User {username} registered successfully"}

# User Login and Token Generation Endpoint
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user(form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    access_token_expires = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")))
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# Protected User Data Endpoint
@app.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# File Upload Endpoint
@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):

    # Access wallet_name and wallet_hotkey from current_user
    wallet_name = current_user.wallet_name
    wallet_hotkey = current_user.wallet_hotkey
    user_wallet = bt.wallet(name = wallet_name, hotkey = wallet_hotkey)

    # Fetch the axons of the available API nodes, or specify UIDs directly
    axons = await get_query_api_axons(wallet=server_wallet, metagraph=metagraph)

    # Check for existence before reuploading
    splt = file.filename.split(os.path.extsep)
    filename_no_ext = splt[0]

    # If exists, don't attempt to overwrite on the network.
    if file_exists(current_user.username, filename=filename_no_ext):
        cid = get_cid_by_filename(filename_no_ext, current_user.username)
        hotkeys = get_hotkeys_by_cid(cid, current_user.username)
        return cid, hotkeys

    raw_data = await file.read()

    # Encrypt the data with the user_wallet, and send with the server_wallet
    if False:
        encrypted_data, encryption_payload = encrypt_data(raw_data, user_wallet)
    else:
        # Don't encrypt for testing right now
        encrypted_data, encryption_payload = raw_data, {}

    cid, hotkeys = await store_handler(
        axons=axons,
        data=encrypted_data,
        encrypt=False, # We already encrypted the data (and don't want to double encrypt it)
        ttl=60 * 60 * 24 * 180, # 6 months
        encoding="utf-8",
        timeout=60,
    )
    if not len(hotkeys):
        raise HTTPException(status_code=500, detail="No hotkeys returned from store_handler. Data not stored.")

    # Store the encrpyiton payload in the user db for later retrieval
    ext = splt[-1] if len(splt) > 1 else ""
    store_file_metadata(
        username=current_user.username,
        filename=filename_no_ext,
        cid=cid,
        hotkeys=hotkeys,
        payload=encryption_payload,
        ext=ext,
        size=sys.getsizeof(encrypted_data),
    )

    return cid, hotkeys

# Multiple files upload endpoint
@app.post("/uploadfiles/")
async def create_upload_files(files: List[UploadFile] = File(...), current_user: User = Depends(get_current_user)):

    # Access wallet_name and wallet_hotkey from current_user
    wallet_name = current_user.wallet_name
    wallet_hotkey = current_user.wallet_hotkey
    user_wallet = bt.wallet(name = wallet_name, hotkey = wallet_hotkey)

    # Fetch the axons of the available API nodes, or specify UIDs directly
    axons = await get_query_api_axons(wallet=server_wallet, metagraph=metagraph)

    # TODO: This should be non-blocking. Either in separate threads or asyncio tasks we await.
    for file in files:
        # TODO: Make this a separate function that can use asyncio.to_thread() or asyncio.create_task()
        # Check for existence before reuploading
        splt = file.filename.split(os.path.extsep)
        filename_no_ext = splt[0]

        if file_exists(current_user.username, filename=filename_no_ext):
            cid = get_cid_by_filename(filename_no_ext, current_user.username)
            hotkeys = get_hotkeys_by_cid(cid, current_user.username)
            continue
            # raise HTTPException(status_code=400, detail="File already exists")

        raw_data = await file.read()

        # Encrypt the data with the user_wallet, and send with the server_wallet
        if False:
            encrypted_data, encryption_payload = encrypt_data(raw_data, user_wallet)
        else:
            # Don't encrypt for testing right now
            encrypted_data, encryption_payload = raw_data, {}

        cid, hotkeys = await store_handler(
            axons=axons,
            data=encrypted_data,
            encrypt=False, # We already encrypted the data (and don't want to double encrypt it)
            ttl=60 * 60 * 24 * 180, # 6 months
            encoding="utf-8",
            timeout=60,
        )
        if not len(hotkeys):
            raise HTTPException(status_code=500, detail="No hotkeys returned from store_handler. Data not stored.")

        # Store the encrpyiton payload in the user db for later retrieval
        ext = splt[-1] if len(splt) > 1 else ""
        store_file_metadata(
            username=current_user.username,
            filename=filename_no_ext,
            cid=cid,
            hotkeys=hotkeys,
            payload=encryption_payload,
            ext=ext,
            size=sys.getsizeof(encrypted_data),
        )

    return cid, hotkeys

# File Retrieval Endpoint
@app.get("/retrieve/{filename}")
async def retrieve_user_data(filename: str, current_user: User = Depends(get_current_user)):

    splt = filename.split(os.path.extsep)
    filename_no_ext = splt[0]

    if not file_exists(current_user.username, filename=filename_no_ext):
        raise HTTPException(
            status_code=404, detail=f"File {filename} does not exist. Please check the filename."
        )

    # Access wallet_name and wallet_hotkey from current_user
    wallet_name = current_user.wallet_name
    wallet_hotkey = current_user.wallet_hotkey
    user_wallet = bt.wallet(name = wallet_name, hotkey = wallet_hotkey)

    cid = get_cid_by_filename(filename_no_ext, current_user.username)
    metadata = get_cid_metadata(cid, current_user.username)
    hotkeys = metadata.get("hotkeys")

    metagraph = get_metagraph()
    uids = None
    if hotkeys is not None:
        uids = [metagraph.hotkeys.index(hotkey) for hotkey in hotkeys]

    # Fetch the axons of the available API nodes, or specify UIDs directly
    axons = await get_query_api_axons(wallet=server_wallet, metagraph=metagraph, uids=uids)

    # TODO: do user decryption if necessary
    encryption_payload = metadata.get("encryption_payload", {})

    success = False
    try:
        decrypted_data = await retrieve_handler(
            axons=axons,
            cid=cid,
            timeout=60
        )
        bt.logging.info(f"Response: {decrypted_data}")
        if decrypted_data != b"":
            success = True

        if success:
            # Save the data to a temporary file on the server
            temp_file_path = "/tmp/" + filename
            with open(temp_file_path, "wb") as f:
                f.write(decrypted_data)

            # Return a FileResponse to send the file for download
            return FileResponse(temp_file_path, filename=filename)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Perhaps this doesn't need username if we can parse it from the `User` object?
@app.get("/user_data")
async def get_user_data(current_user: User = Depends(get_current_user)):
    return {
        "file_metadata": get_user_metadata(current_user.username),
        "stats": get_user_stats(current_user.username),
    }

@app.get("/hotkeys/{cid}")
async def get_hotkeys(cid: str, current_user: User = Depends(get_current_user)):
    return get_hotkeys_by_cid(cid, current_user.username)