import logging
from sqlalchemy import text
from database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def migrate():
    """Ejecuta migraciones manuales para añadir columnas faltantes en Render."""
    logger.info("Iniciando migración manual de base de datos...")
    
    with engine.begin() as conn:
        # 1. Verificar y añadir 'resultados_publicados' en 'elecciones'
        try:
            conn.execute(text("ALTER TABLE elecciones ADD COLUMN resultados_publicados BOOLEAN DEFAULT FALSE;"))
            logger.info("✅ Columna 'resultados_publicados' añadida exitosamente.")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("ℹ️ La columna 'resultados_publicados' ya existía.")
            else:
                logger.error(f"❌ Error al añadir 'resultados_publicados': {e}")

        # 2. Verificar y añadir 'nombre_jefe' en 'jefes_mesa'
        try:
            conn.execute(text("ALTER TABLE jefes_mesa ADD COLUMN nombre_jefe VARCHAR;"))
            logger.info("✅ Columna 'nombre_jefe' añadida exitosamente.")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("ℹ️ La columna 'nombre_jefe' ya existía.")
            else:
                logger.error(f"❌ Error al añadir 'nombre_jefe': {e}")

    logger.info("Migración completada.")

if __name__ == "__main__":
    migrate()
