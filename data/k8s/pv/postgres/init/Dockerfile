FROM postgres:16

# Opcional: fija locale/timezone si quieres consistencia
ENV TZ=Europe/Amsterdam

# Copia tu esquema para el entrypoint
COPY 001_schema.sql /docker-entrypoint-initdb.d/001_schema.sql

