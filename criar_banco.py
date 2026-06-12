import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def criar_sigua_db():
    try:
        # Tenta conectar no Postgres padrão para criar o novo banco
        # Testamos as duas portas possíveis (5433 e 5432)
        for porta in [5433, 5432]:
            try:
                print(f"Tentando conectar na porta {porta}...")
                con = psycopg2.connect(
                    dbname="postgres",
                    user="postgres",
                    password="emyc27311",  # Sua senha
                    host="localhost",
                    port=porta,
                )
                con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                cur = con.cursor()

                # Cria o banco de dados
                cur.execute("CREATE DATABASE sigua_db")
                print(f"✅ Sucesso! Banco 'sigua_db' criado na porta {porta}.")
                cur.close()
                con.close()
                return porta
            except Exception as e:
                if "already exists" in str(e):
                    print(f"ℹ️ O banco 'sigua_db' já existe na porta {porta}.")
                    return porta
                print(f"❌ Erro na porta {porta}: {e}")

    except Exception as e:
        print(f"🔥 Erro crítico: {e}")


if __name__ == "__main__":
    porta_ativa = criar_sigua_db()
    if porta_ativa:
        print(f"\n🚀 AGORA AJUSTE SEU .ENV: DB_PORT={porta_ativa}")
