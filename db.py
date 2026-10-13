import json

import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool

from config import DB_CONFIG

POOL = MySQLConnectionPool(
    pool_name="fintech_pool",
    pool_size=5,
    **DB_CONFIG,
)


def get_connection():
    return POOL.get_connection()


def fetch_all(query, params=None):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        result = cursor.fetchall()
        return result
    finally:
        cursor.close()
        conn.close()


def fetch_one(query, params=None):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        result = cursor.fetchone()
        return result
    finally:
        cursor.close()
        conn.close()


def execute(query, params=None, commit=True):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        if commit:
            conn.commit()
        return cursor.lastrowid or cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def record_txn_event(txn_id, stage, detail=None, table_prefix=""):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO {table_prefix}txn_events (txn_id, stage, detail) VALUES (%s, %s, %s)",
            (txn_id, stage, json.dumps(detail or {})),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()
