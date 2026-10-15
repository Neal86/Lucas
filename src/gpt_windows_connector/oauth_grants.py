"""Durable OAuth revocation generations, independent of browser login sessions.

Generation zero preserves existing signed access tokens until the connection is
disconnected. Retain tombstones after reconnect so old tokens never revive.
All writes participate in the caller's transaction.
"""
from __future__ import annotations

import sqlite3


def initialize(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS oauth_revocations (
        client_id TEXT NOT NULL, user_id TEXT NOT NULL,
        generation INTEGER NOT NULL,
        PRIMARY KEY(client_id, user_id)
    )""")


def connection_generation(db: sqlite3.Connection, user_id: str, client_id: str) -> int:
    row = db.execute("""SELECT COALESCE(r.generation, 0)
        FROM oauth_client_users c
        LEFT JOIN oauth_revocations r ON r.client_id=c.client_id AND r.user_id=c.user_id
        WHERE c.client_id=? AND c.user_id=?""", (client_id, user_id)).fetchone()
    if row is None:
        raise PermissionError("OAuth connection has been disconnected")
    return int(row[0])


def revoke_connection(db: sqlite3.Connection, user_id: str, client_id: str) -> None:
    db.execute("""INSERT INTO oauth_revocations(client_id,user_id,generation)
        VALUES(?,?,1) ON CONFLICT(client_id,user_id)
        DO UPDATE SET generation=generation+1""", (client_id, user_id))


def verify_generation(db: sqlite3.Connection, user_id: str, client_id: str, generation: object) -> None:
    if type(generation) is not int or generation != connection_generation(db, user_id, client_id):
        raise PermissionError("OAuth access token has been revoked")
