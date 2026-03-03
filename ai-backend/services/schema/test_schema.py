import sys
import os
from services.db_inspector import DBInspector 
from services.vector_store import save_schema_chunks

DB_URL = "postgresql://nl2sql_user:CHANGE_ME_strong_password_here@nl2sql-postgres:5432/nl2sql"

def run_test():
    print("Epic 1: Profesyonel Şema Analizi Başlatılıyor...")
    try:
        inspector = DBInspector(DB_URL)
        schema_tables = inspector.get_schema()
        
        print(f"✅ {len(schema_tables)} tablo başarıyla analiz edildi.")

        print("Veriler ChromaDB hafızasına aktarılıyor...")
        num_saved = save_schema_chunks(db_id="test_db_001", tables=schema_tables)
        
        print(f"\n EPIC 1 BAŞARIYLA TAMAMLANDI: {num_saved} tablo hafızaya alındı!")

    except Exception as e:
        print(f"❌ HATA: {e}")
    finally:
        if 'inspector' in locals():
            inspector.dispose()

if __name__ == "__main__":
    run_test()