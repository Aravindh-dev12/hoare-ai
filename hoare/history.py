from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


class HistoryStore:
    def __init__(self, sqlite_path: str | None = None):
        self.sqlite_path = sqlite_path or os.getenv('HOARE_SQLITE_PATH', '/tmp/hoare_ai.db')
        self.bigquery_table = os.getenv('HOARE_BIGQUERY_TABLE', '').strip()
        self._bq_ready = False
        self._init_sqlite()

    def _connect(self):
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self):
        with self._connect() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    language TEXT,
                    code_hash TEXT,
                    quality_score REAL,
                    risk_level TEXT,
                    summary TEXT,
                    payload_json TEXT NOT NULL
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_reviews_user_created ON reviews(user_id, created_at DESC)')

    def _ensure_bigquery(self, client):
        if self._bq_ready or not self.bigquery_table:
            return
        from google.cloud import bigquery

        parts = self.bigquery_table.split('.')
        if len(parts) != 3:
            raise ValueError('HOARE_BIGQUERY_TABLE must be project.dataset.table')
        project, dataset_name, _ = parts
        dataset_id = f'{project}.{dataset_name}'
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1')
        client.create_dataset(dataset, exists_ok=True)
        schema = [
            bigquery.SchemaField('review_id', 'STRING', mode='REQUIRED'),
            bigquery.SchemaField('user_id', 'STRING', mode='REQUIRED'),
            bigquery.SchemaField('created_at', 'TIMESTAMP', mode='REQUIRED'),
            bigquery.SchemaField('language', 'STRING'),
            bigquery.SchemaField('code_hash', 'STRING'),
            bigquery.SchemaField('quality_score', 'FLOAT'),
            bigquery.SchemaField('risk_level', 'STRING'),
            bigquery.SchemaField('summary', 'STRING'),
            bigquery.SchemaField('payload_json', 'JSON'),
        ]
        client.create_table(bigquery.Table(self.bigquery_table, schema=schema), exists_ok=True)
        self._bq_ready = True

    def save(self, payload: dict[str, Any]):
        row = (
            payload['review_id'], payload['user_id'], payload['created_at'], payload.get('language', ''),
            payload.get('code_hash', ''), payload.get('quality_score', 0), payload.get('risk_level', ''),
            payload.get('summary', ''), json.dumps(payload, ensure_ascii=False),
        )
        with self._connect() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO reviews
                (review_id,user_id,created_at,language,code_hash,quality_score,risk_level,summary,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?)
            ''', row)
        if self.bigquery_table:
            self._save_bigquery(payload)

    def _save_bigquery(self, payload: dict[str, Any]):
        try:
            from google.cloud import bigquery
            client = bigquery.Client()
            self._ensure_bigquery(client)
            bq_row = {
                'review_id': payload['review_id'],
                'user_id': payload['user_id'],
                'created_at': payload['created_at'],
                'language': payload.get('language', ''),
                'code_hash': payload.get('code_hash', ''),
                'quality_score': payload.get('quality_score', 0),
                'risk_level': payload.get('risk_level', ''),
                'summary': payload.get('summary', ''),
                'payload_json': payload,
            }
            errors = client.insert_rows_json(self.bigquery_table, [bq_row])
            if errors:
                print('BigQuery insert errors:', errors)
        except Exception as exc:
            print('BigQuery write skipped:', exc)

    def _recent_bigquery(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        from google.cloud import bigquery
        client = bigquery.Client()
        self._ensure_bigquery(client)
        safe_limit = max(1, min(int(limit), 100))
        query = f'''
            SELECT review_id, created_at, language, quality_score, risk_level, summary,
                   TO_JSON_STRING(payload_json) AS payload_json
            FROM `{self.bigquery_table}`
            WHERE user_id = @user_id
            ORDER BY created_at DESC
            LIMIT {safe_limit}
        '''
        config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter('user_id', 'STRING', user_id)]
        )
        rows = client.query(query, job_config=config).result()
        result = []
        for row in rows:
            item = dict(row.items())
            created = item.get('created_at')
            if hasattr(created, 'isoformat'):
                item['created_at'] = created.isoformat()
            result.append(item)
        return result

    def recent(self, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        if self.bigquery_table:
            try:
                return self._recent_bigquery(user_id, limit)
            except Exception as exc:
                print('BigQuery read fallback:', exc)
        with self._connect() as conn:
            rows = conn.execute('''
                SELECT review_id,created_at,language,quality_score,risk_level,summary,payload_json
                FROM reviews WHERE user_id=? ORDER BY created_at DESC LIMIT ?
            ''', (user_id, max(1, min(int(limit), 100)))).fetchall()
        return [dict(r) for r in rows]

    def recent_patterns(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.recent(user_id, limit)
        patterns: dict[tuple[str, str], int] = {}
        for row in rows:
            raw = row.get('payload_json')
            try:
                payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                continue
            for finding in payload.get('findings', []):
                key = (finding.get('category', 'unknown'), finding.get('title', 'Issue'))
                patterns[key] = patterns.get(key, 0) + 1
        return [
            {'category': k[0], 'issue': k[1], 'count': count}
            for k, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:8]
        ]
