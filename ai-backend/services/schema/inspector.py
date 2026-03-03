from sqlalchemy import create_engine, inspect
from typing import Dict, Any

class SchemaInspector:
    def __init__(self, db_url: str):
        """
        SQLAlchemy kullanarak hedef veritabanına (Postgres, MySQL vb.) bağlanır.
        """
        self.engine = create_engine(db_url)
        self.inspector = inspect(self.engine)

    def extract_hierarchy(self) -> Dict[str, Any]:
        """
        Tabloları, kolonları ve aralarındaki Foreign Key ilişkilerini çıkarır.
        """
        full_schema = {}
        tables = self.inspector.get_table_names()
        
        for table in tables:
            # Gereksiz sistem tablolarını filtrele
            if table.startswith(('pg_', 'information_schema', 'sys')):
                continue
                
            # Kolonları al
            columns = self.inspector.get_columns(table)
            # İlişkileri (Foreign Keys) al -> Bu kısım JOIN'ler için senin en kritik görevin!
            fks = self.inspector.get_foreign_keys(table)
            
            full_schema[table] = {
                "columns": [{"name": c['name'], "type": str(c['type'])} for c in columns],
                "relationships": [{"to_table": f['referred_table'], "on": f['referred_columns']} for f in fks]
            }
        return full_schema