import sqlite3
import os
import secrets
from datetime import datetime, timedelta

DB_FILE="whitelist.db"

if not os.path.exists(DB_FILE):
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("CREATE TABLE api_keys (key TEXT PRIMARY KEY, owner TEXT, expires_at TEXT, ratelimit TEXT)")
    conn.commit()
    conn.close()

def list_keys():
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("SELECT rowid,key,owner,expires_at,ratelimit FROM api_keys")
    rows=c.fetchall()
    for i,k,o,e,r in rows:
        note=f" ({o})" if o else ""
        exp=f" expires at {e}" if e else " lifetime"
        print(f"{i}. {k}{note}{exp} [{r}]")
    conn.close()
    return rows

def add_key():
    owner=input("Owner (optional): ").strip()
    lifetime=input("Lifetime? (y for lifetime, or enter 2d/3d/etc): ").strip()
    ratelimit=input("Rate limit? (standard/premium): ").strip().lower() or "standard"
    expires_at=None
    if lifetime.lower()!="y":
        amount=int(lifetime[:-1])
        unit=lifetime[-1]
        delta={"s":timedelta(seconds=amount),"m":timedelta(minutes=amount),"h":timedelta(hours=amount),"d":timedelta(days=amount)}.get(unit,timedelta(days=amount))
        expires_at=(datetime.utcnow()+delta).isoformat()
    new_key=secrets.token_hex(32)
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("INSERT INTO api_keys (key,owner,expires_at,ratelimit) VALUES (?,?,?,?)",(new_key,owner if owner else None,expires_at,ratelimit))
    conn.commit()
    conn.close()
    print(f"Added key: {new_key}")

def edit_key():
    rows=list_keys()
    if not rows:
        print("No keys to edit.")
        return
    index=int(input("Select number to edit: ").strip())
    selected=next((r for r in rows if r[0]==index),None)
    if not selected:
        print("Invalid selection.")
        return
    owner=input(f"New owner (current {selected[2]}): ").strip()
    lifetime=input("Lifetime? (y for lifetime, or enter 2d/3d/etc): ").strip()
    ratelimit=input(f"Rate limit? (current {selected[4]}): ").strip().lower() or selected[4]
    expires_at=None
    if lifetime.lower()!="y":
        amount=int(lifetime[:-1])
        unit=lifetime[-1]
        delta={"s":timedelta(seconds=amount),"m":timedelta(minutes=amount),"h":timedelta(hours=amount),"d":timedelta(days=amount)}.get(unit,timedelta(days=amount))
        expires_at=(datetime.utcnow()+delta).isoformat()
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("UPDATE api_keys SET owner=?,expires_at=?,ratelimit=? WHERE rowid=?",(owner if owner else None,expires_at,ratelimit,selected[0]))
    conn.commit()
    conn.close()
    print("Key updated.")

def remove_key():
    rows=list_keys()
    if not rows:
        print("No keys to remove.")
        return
    index=int(input("Select number to delete: ").strip())
    selected=next((r for r in rows if r[0]==index),None)
    if not selected:
        print("Invalid selection.")
        return
    confirm=input(f"Are you sure you want to delete {selected[1]}? (y/n): ").strip().lower()
    if confirm=="y":
        conn=sqlite3.connect(DB_FILE)
        c=conn.cursor()
        c.execute("DELETE FROM api_keys WHERE rowid=?",(selected[0],))
        conn.commit()
        conn.close()
        print("Deleted.")

def purge_all():
    confirm=input("Are you sure you want to purge all keys? (y/n): ").strip().lower()
    if confirm!="y":
        print("Cancelled.")
        return
    keep_cosmin=input("Keep Cosmin key? (y/n): ").strip().lower()=="y"
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    if keep_cosmin:
        c.execute("DELETE FROM api_keys WHERE owner!='cosmin'")
    else:
        c.execute("DELETE FROM api_keys")
    conn.commit()
    conn.close()
    print("Purged keys.")

def set_all_standard():
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("UPDATE api_keys SET ratelimit='standard'")
    conn.commit()
    conn.close()
    print("All keys set to standard.")

def main():
    print("1. Add key\n2. Edit key\n3. Remove key\n4. Purge all keys\n5. List keys")
    choice=input("Choose: ").strip()
    if choice=="1": add_key()
    elif choice=="2": edit_key()
    elif choice=="3": remove_key()
    elif choice=="4": purge_all()
    elif choice=="5": list_keys()
    else: print("Invalid choice.")

if __name__=="__main__":
    main()
