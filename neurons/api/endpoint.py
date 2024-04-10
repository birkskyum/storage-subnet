import pandas as pd
import datetime
import time
import threading
import sqlite3

from fastapi import APIRouter
from typing import List, Dict
from pydantic import BaseModel
from fastapi import FastAPI
from redis import asyncio as aioredis

from storage.validator.database import *
from .sqlite import query

redis, app, router = None, None, None

def get_redis():
    global redis
    if not redis:
        redis = aioredis.Redis(db=1)
    return redis

class MinerStatItem(BaseModel):
    DATE: str
    DATETIME: str
    HOTKEY: str
    TIER: str
    CURRENT_STORAGE: int
    CAPACITY: int
    PERCENT_USAGE: float
    NUM_HASHES: int
    TOTAL_SUCCESSES: int
    STORE_SUCCESSES: int
    STORE_ATTEMPTS: int
    CHALLENGE_SUCCESSES: int
    CHALLENGE_ATTEMPTS: int
    RETRIEVE_SUCCESSES: int
    RETRIEVE_ATTEMPTS: int

MINER_QUERY = """
SELECT (
    timestamp,
    hotkey,
    tier,
    current_storage,
    capacity,
    percent_usage,
    num_hashes,
    total_successes,
    store_successes,
    store_attempts,
    challenge_successes,
    challenge_attempts,
    retrieve_successes,
    retrieve_attempts
) FROM HotkeysTable WHERE timestamp BETWEEN datetime(?, 'unixepoch') AND datetime(?, 'unixepoch') LIMIT ?
"""

@app.get("/miner_statistics", response_model=List[MinerStatItem])
async def get_miner_statistics_endpoint(start_time: int = 0, end_time: int = 0, limit: int = 50):
    miner_data = query(MINER_QUERY, [start_time, end_time, limit])

    stats = await get_miner_statistics(database)
    hotkeys = list(stats)
    caps = await cache_hotkeys_capacity(hotkeys, database)
    data_rows = []

    for hotkey, stat in stats.items():
        cur, cap = caps[hotkey]
        n_hashes = len(await get_hashes_for_hotkey(hotkey, database))
        row = MinerStatItem(
            DATE=str(datetime.date.today()),
            DATETIME=str(datetime.datetime.utcfromtimestamp(int(time.time())))[:-3],
            HOTKEY=hotkey,
            TIER=stat['tier'],
            CURRENT_STORAGE=cur,
            CAPACITY=cap,
            PERCENT_USAGE=cur / cap if cap else 0,
            NUM_HASHES=n_hashes,
            TOTAL_SUCCESSES=stat.get('total_successes',0),
            STORE_SUCCESSES=stat.get('store_successes',0),
            STORE_ATTEMPTS=stat.get('store_attempts',0),
            CHALLENGE_SUCCESSES=stat.get('challenge_successes',0),
            CHALLENGE_ATTEMPTS=stat.get('challenge_attempts',0),
            RETRIEVE_SUCCESSES=stat.get('retrieve_successes',0),
            RETRIEVE_ATTEMPTS=stat.get('retrieve_attempts',0),
        )
        data_rows.append(row.dict())

    return data_rows


class TierStatItem(BaseModel):
    DATE: str
    DATETIME: str
    TIER: str
    COUNTS: int
    CAPACITY: int
    CURRENT_STORAGE: int
    PERCENT_USAGE: float
    CURRENT_ATTEMPTS: int
    CURRENT_SUCCESSES: int
    GLOBAL_SUCCESS_RATE: float
    TOTAL_GLOBAL_SUCCESSES: int


@app.get("/tiers_data", response_model=List[TierStatItem])
async def get_tiers_data_endpoint():
    tstats = await tier_statistics(database)
    
    istats = {}
    for category, tier_dict in tstats.items():
        for tier, value in tier_dict.items():
            if tier not in istats:
                istats[tier] = {}
            istats[tier][category] = value

    by_tier = await compute_by_tier_stats(database)

    data_rows = []
    for tier, stat in istats.items():
        row = TierStatItem(
            DATE=str(datetime.date.today()),
            DATETIME=str(datetime.datetime.utcfromtimestamp(int(time.time())))[:-3],
            TIER=tier,
            COUNTS=stat.get('counts', 0),
            CAPACITY=stat.get('capacity', 0),
            CURRENT_STORAGE=stat.get('current_storage', 0),
            PERCENT_USAGE=stat.get('percent_usage', 0.0),
            CURRENT_ATTEMPTS=by_tier[tier]['total_current_attempts'] if tier in by_tier else 0,
            CURRENT_SUCCESSES=by_tier[tier]['total_current_successes'] if tier in by_tier else 0,
            GLOBAL_SUCCESS_RATE=by_tier[tier]['success_rate'] if tier in by_tier else 0.0,
            TOTAL_GLOBAL_SUCCESSES=by_tier[tier]['total_global_successes'] if tier in by_tier else 0,
        )
        data_rows.append(row.dict())

    return data_rows



class NetworkDataItem(BaseModel):
    DATE: str
    DATETIME: str
    CURRENT_STORAGE: int
    NETWORK_CAPACITY: int
    TOTAL_SUCCESSFUL_REQUESTS: int
    REDIS_INDEX_SIZE_BYTES: int
    GLOBAL_CURRENT_ATTEMPTS: int
    GLOBAL_CURRENT_SUCCESSES: int
    GLOBAL_CURRENT_SUCCESS_RATE: float

@app.get("/network_data", response_model=NetworkDataItem)
async def get_network_data_endpoint():
    net_cap = await get_network_capacity(database)
    idx_size = await get_redis_db_size(database)
    tot_suc = await total_successful_requests(database)

    hotkeys = await active_hotkeys(database)
    caps = await cache_hotkeys_capacity(hotkeys, database)
    cur_storage = sum(c[0] for c in caps.values())

    global_stats = {
        'store_attempts': 0,
        'store_successes': 0,
        'challenge_attempts': 0,
        'challenge_successes': 0,
        'retrieve_attempts': 0,
        'retrieve_successes': 0,
    }

    for _, d in (await get_miner_statistics(database)).items():
        for key in global_stats.keys():
            global_stats[key] += int(d[key])

    global_attempts = global_stats['store_attempts'] + global_stats['challenge_attempts'] + global_stats['retrieve_attempts']
    global_successes = global_stats['store_successes'] + global_stats['challenge_successes'] + global_stats['retrieve_successes']

    data_row = NetworkDataItem(
        DATE=str(datetime.date.today()),
        DATETIME=str(datetime.datetime.utcfromtimestamp(int(time.time())))[:-3],
        CURRENT_STORAGE=cur_storage,
        NETWORK_CAPACITY=net_cap,
        TOTAL_SUCCESSFUL_REQUESTS=tot_suc,
        REDIS_INDEX_SIZE_BYTES=idx_size,
        GLOBAL_CURRENT_ATTEMPTS=global_attempts,
        GLOBAL_CURRENT_SUCCESSES=global_successes,
        GLOBAL_CURRENT_SUCCESS_RATE=(global_successes / global_attempts) if global_attempts else 0
    )

    return data_row

def startup():
    global database, app, router
    database = get_database()
    app = FastAPI()
    router = APIRouter()

def run_in_thread():
    thread = threading.Thread(target=startup, daemon=True)
    thread.start()