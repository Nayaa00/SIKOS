from pathlib import Path
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
URL = os.getenv('DATABASE_URL', 'mysql+pymysql://root@127.0.0.1:3306/sikos?charset=utf8mb4')
options = {'pool_pre_ping': True}
if URL.startswith('sqlite'):
    options['connect_args'] = {'check_same_thread':False}
engine = create_engine(URL, **options)
if URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
