import threading
import bittensor as bt
import redis
from time import sleep

import storage
from storage.validator.database import *
from storage.validator.bonding import *
from storage.shared.utils import get_redis_password

import endpoint
from .sqlite import query

redis_db = None

def startup():
    global redis_db
    redis_db = redis.StrictRedis(password=get_redis_password())

def create_tables():
    query('''
CREATE TABLE IF NOT EXISTS NetworkStatsTable (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_storage BIGINT NOT NULL,
    network_capacity BIGINT NOT NULL,
    total_successful_requests INT NOT NULL,
    redis_index_size_mb FLOAT NOT NULL,
    global_current_attempts INT NOT NULL,
    global_current_successes INT NOT NULL,
    global_current_success_rate FLOAT NOT NULL
)
''')
    
    query('''
CREATE TABLE IF NOT EXISTS TierStatsTable (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tier VARCHAR(50) NOT NULL,
    counts INT NOT NULL,
    capacity BIGINT NOT NULL,
    current_storage BIGINT NOT NULL,
    percent_usage FLOAT NOT NULL,
    current_attempts INT NOT NULL,
    current_successes INT NOT NULL,
    global_success_rate FLOAT NOT NULL,
    total_global_successes INT NOT NULL
)
''')
    
    query('''
CREATE TABLE IF NOT EXISTS HotkeysTable (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hotkey VARCHAR(255) NOT NULL,
    tier VARCHAR(50) NOT NULL,
    current_storage BIGINT NOT NULL,
    capacity BIGINT NOT NULL,
    percent_usage FLOAT NOT NULL,
    num_hashes INT NOT NULL,
    total_successes INT NOT NULL,
    store_successes INT NOT NULL,
    store_attempts INT NOT NULL,
    challenge_successes INT NOT NULL,
    challenge_attempts INT NOT NULL,
    retrieve_successes INT NOT NULL,
    retrieve_attempts INT NOT NULL
)
''')

def collect_and_insert_data():
    global redis_db

    stats = get_miner_statistics(redis_db)
    hotkeys = list(stats)
    caps = cache_hotkeys_capacity(hotkeys, redis_db)

    for hotkey, stat in stats.items():
        cur, cap = caps[hotkey]
        n_hashes = len(get_hashes_for_hotkey(hotkey, redis_db))
        row = [hotkey, stat['tier'], cur, cap, cur / cap, n_hashes, stat['total_successes'], stat['store_successes'], stat['store_attempts'], stat['challenge_successes'], stat['challenge_attempts'], stat['retrieve_successes'], stat['retrieve_attempts']]
        sql_insert_command = """
        INSERT INTO HotkeysTable (
            HOTKEY, TIER, CURRENT_STORAGE, CAPACITY, PERCENT_USAGE, NUM_HASHES, TOTAL_SUCCESSES, STORE_SUCCESSES, STORE_ATTEMPTS, CHALLENGE_SUCCESSES, CHALLENGE_ATTEMPTS, RETRIEVE_SUCCESSES, RETRIEVE_ATTEMPTS
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        query(sql_insert_command, row)

    tstats = tier_statistics(redis_db)

    istats = {}
    for category, tier_dict in tstats.items():
        for tier, value in tier_dict.items():
            if tier not in istats:
                istats[tier] = {}
            istats[tier][category] = value

    by_tier = compute_by_tier_stats(redis_db)

    for tier, stat in istats.items():
        print(tier, stat)
        row = [tier] + list(stat.values())
        if tier in by_tier:
            tr = by_tier[tier]
            row += [tr['total_current_attempts'], tr['total_current_successes'], tr['success_rate'], tr['total_global_successes']]
        else:
            row += [0, 0, 0, 0]
        print(row)

    # Write the actual row to the table
    sql_insert_command = """
    INSERT INTO TierStatsTable (
        TIER, COUNTS, CAPACITY, CURRENT_STORAGE, PERCENT_USAGE, CURRENT_ATTEMPTS, CURRENT_SUCCESSES, GLOBAL_SUCCESS_RATE, TOTAL_GLOBAL_SUCCESSES
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    query(sql_insert_command, row)

    net_cap = get_network_capacity(redis_db)
    idx_size = get_redis_db_size(redis_db)
    tot_suc = total_successful_requests(redis_db)

    hotkeys = active_hotkeys(redis_db)
    caps = cache_hotkeys_capacity(hotkeys, redis_db)
    cur_storage = sum(list(zip(*list(caps.values())))[0])

    store_attempts = sa = 0
    store_successes = ss = 0
    challenge_attempts = ca = 0
    challenge_successes = cs = 0
    retrieve_attempts = ra = 0
    retrieve_successes = rs = 0

    for _, d in (get_miner_statistics(redis_db)).items():
        tier = d['tier']
        sa += int(d['store_attempts'])
        ss += int(d['store_successes'])
        ca += int(d['challenge_attempts'])
        cs += int(d['challenge_successes'])
        ra += int(d['retrieve_attempts'])
        rs += int(d['retrieve_successes'])

    cta = sum([sa, ca, ra])
    cts = sum([ss, cs, rs])
    print(cts, cta)
    print(cts / cta, "%")
    global_attempts = cta
    global_successees = cts

    row = [cur_storage, net_cap, tot_suc, idx_size, global_attempts, global_successees, global_successees / global_attempts]
    print(row)
    # Write SQL to populate table with this row
    # TODO: FIX THIS!
    sql_insert_command = """
    INSERT INTO NetworkStatsTable (
        CURRENT_STORAGE, NETWORK_CAPACITY, TOTAL_SUCCESSFUL_REQUESTS, REDIS_INDEX_SIZE_MB, GLOBAL_CURRENT_ATTEMPTS, GLOBAL_CURRENT_SUCCESSES, GLOBAL_CURRENT_SUCCESS_RATE
    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
    """

    query(sql_insert_command, row)

def run():
    startup()
    create_tables()

    while True:
        collect_and_insert_data()

        sleep(3600) # Run loop every hour

def run_indexer_thread():
    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    endpoint.run_in_thread()