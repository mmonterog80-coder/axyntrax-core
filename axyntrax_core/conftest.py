import os

# Configuración automática del entorno de pruebas unitarias
# Garantiza que los tests siempre cuenten con una clave de prueba sin requerir export manual
os.environ.setdefault("AXYNTRAX_SIGNING_SECRET", "test-only-signing-secret-key-32bytes!!")
