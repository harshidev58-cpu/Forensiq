#!/usr/bin/env python3
"""
Database setup script for ForensiX Upload & Fingerprint module.
Creates SQLite database with evidence_records and custody_entries tables.
"""

import sqlite3
import os
from pathlib import Path

def create_database():
    """Create SQLite database and tables for the Upload & Fingerprint module."""
    
    # Database path
    db_path = Path("forensix.db")
    
    # Create database connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create evidence_records table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS evidence_records (
                id TEXT PRIMARY KEY,                      -- UUID4 (every upload unique, no dedup)
                original_filename TEXT NOT NULL,          -- Max 255 chars
                file_size INTEGER NOT NULL,               -- Bytes
                mime_type TEXT NOT NULL,                  -- Max 100 chars (extension-based)
                file_extension TEXT NOT NULL,             -- Max 10 chars
                sha256_hash TEXT NOT NULL,                -- 64-char hex string
                uploader_id TEXT NOT NULL,                -- Max 100 chars
                collection_method TEXT NOT NULL,          -- Max 1000 chars
                upload_timestamp TEXT NOT NULL,           -- ISO 8601 UTC
                creation_timestamp TEXT,                  -- ISO 8601 UTC, nullable
                modification_timestamp TEXT,              -- ISO 8601 UTC, nullable
                extracted_metadata TEXT,                  -- JSON, max 1 MB, nullable
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create custody_entries table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custody_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,                -- FK to evidence_records.id
                action_type TEXT NOT NULL,                -- UPLOAD, ACCESS, VERIFY
                timestamp TEXT NOT NULL,                  -- ISO 8601 UTC with ms
                notes TEXT,                               -- Optional context
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (evidence_id) REFERENCES evidence_records(id) ON DELETE CASCADE
            )
        ''')
        
        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sha256 ON evidence_records(sha256_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_uploader ON evidence_records(uploader_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_upload_timestamp ON evidence_records(upload_timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_evidence_id ON custody_entries(evidence_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_action_type ON custody_entries(action_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON custody_entries(timestamp)')
        
        # Commit changes
        conn.commit()
        print(f"✓ Database created successfully at {db_path.absolute()}")
        print("✓ Tables created: evidence_records, custody_entries")
        print("✓ Indexes created for performance")
        
    except sqlite3.Error as e:
        print(f"✗ Database setup failed: {e}")
        conn.rollback()
        raise
        
    finally:
        conn.close()

def verify_database():
    """Verify database schema and tables."""
    conn = sqlite3.connect("forensix.db")
    cursor = conn.cursor()
    
    try:
        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        table_names = [table[0] for table in tables]
        
        print(f"✓ Tables found: {table_names}")
        
        # Check evidence_records schema
        cursor.execute("PRAGMA table_info(evidence_records)")
        evidence_columns = cursor.fetchall()
        print(f"✓ evidence_records columns: {len(evidence_columns)}")
        
        # Check custody_entries schema
        cursor.execute("PRAGMA table_info(custody_entries)")
        custody_columns = cursor.fetchall()
        print(f"✓ custody_entries columns: {len(custody_columns)}")
        
        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = cursor.fetchall()
        index_names = [idx[0] for idx in indexes if not idx[0].startswith('sqlite_')]
        print(f"✓ Custom indexes: {index_names}")
        
    finally:
        conn.close()

def migrate_add_authentication_results_table():
    """
    Migration: Add authentication_results table for Authentication Engine module.
    
    This creates the authentication_results table with:
    - id: UUID primary key
    - evidence_id: Foreign key to evidence_records.id (NOT NULL, unique)
    - confidence_score: Integer 0-100
    - verdict: String enum (AUTHENTIC, SUSPICIOUS, TAMPERED)
    - signals_detected: JSON text field
    - explanation: Text field (max 5000 chars)
    - analyzed_at: ISO 8601 UTC timestamp
    - analyzer_version: Version string (max 50 chars)
    - created_at: Timestamp (auto-generated)
    - updated_at: Timestamp (auto-generated)
    
    Indexes created on: evidence_id, verdict, analyzed_at, confidence_score
    
    Validates: Requirements 1.1, 1.2
    """
    db_path = Path("forensix.db")
    
    if not db_path.exists():
        print(f"✗ Database not found at {db_path}. Run create_database() first.")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='authentication_results'")
        if cursor.fetchone():
            print("ℹ authentication_results table already exists. Skipping migration.")
            return True
        
        # Create authentication_results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS authentication_results (
                id TEXT PRIMARY KEY,                      -- UUID
                evidence_id TEXT NOT NULL UNIQUE,         -- FK to evidence_records.id
                confidence_score INTEGER NOT NULL,        -- 0-100
                verdict TEXT NOT NULL,                    -- "AUTHENTIC", "SUSPICIOUS", "TAMPERED"
                signals_detected TEXT NOT NULL,           -- JSON array of signals
                explanation TEXT NOT NULL,                -- Max 5000 chars
                analyzed_at TEXT NOT NULL,                -- ISO 8601 UTC
                analyzer_version TEXT NOT NULL,           -- e.g., "1.0.0"
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (evidence_id) REFERENCES evidence_records(id) ON DELETE CASCADE
            )
        ''')
        
        # Create indexes for query performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_authentication_evidence_id ON authentication_results(evidence_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_authentication_verdict ON authentication_results(verdict)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_authentication_analyzed_at ON authentication_results(analyzed_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_authentication_confidence_score ON authentication_results(confidence_score)')
        
        # Commit changes
        conn.commit()
        print("✓ Migration completed: authentication_results table created")
        print("✓ Indexes created: evidence_id, verdict, analyzed_at, confidence_score")
        print("✓ Foreign key constraint created: evidence_id -> evidence_records.id")
        
        return True
        
    except sqlite3.Error as e:
        print(f"✗ Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    print("Setting up ForensiX SQLite database...")
    create_database()
    verify_database()
    print("\nRunning migrations...")
    migrate_add_authentication_results_table()
    print("Database setup complete!")