const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { parse } = require("dotenv");
const mysql = require("mysql2/promise");

const rosterTables = ["facultad", "escuela_profesional", "alumno", "docente", "personal_administrativo"];
const legacyTables = ["disciplinas", "losas", "configuracion_global", "users", "trabajadores"];

async function exportTables(folder, tables) {
  const env = parse(readFileSync(resolve(__dirname, "..", "..", folder, ".env")));
  const connection = await mysql.createConnection({
    host: env.DB_HOST || "localhost",
    port: Number(env.DB_PORT || 3306),
    user: env.DB_USER,
    password: env.DB_PASSWORD,
    database: env.DB_NAME,
    timezone: "local",
    dateStrings: true,
    connectTimeout: 8000,
  });
  try {
    await connection.query("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY");
    const records = {};
    for (const table of tables) {
      const [rows] = await connection.query(`SELECT * FROM \`${table}\``);
      records[table] = rows;
    }
    await connection.rollback();
    return records;
  } finally {
    await connection.end();
  }
}

async function main() {
  const roster = await exportTables("backend_api", rosterTables);
  const legacy = process.argv.includes("--legacy") ? await exportTables("backend", legacyTables) : {};
  process.stdout.write(JSON.stringify({ roster, legacy }));
}

main().catch((error) => {
  console.error("Exportación MySQL fallida", error.code || error.name);
  process.exitCode = 1;
});

