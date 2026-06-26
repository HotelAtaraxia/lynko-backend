import psycopg2
from psycopg2.extras import RealDictCursor

def obtener_conexion():
    try:
        return psycopg2.connect(
            host="localhost",
            database="lynko",         
            user="postgres",          
            password="1234",        
            port="5432"
        )
    except Exception as e:
        print(f"❌ Error crítico al conectar con PostgreSQL: {e}")
        return None