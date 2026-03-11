using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace NL2SQL.CoreBackend.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class InitialCreate : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "schema_cache",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    db_id = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    database_name = table.Column<string>(type: "character varying(255)", maxLength: 255, nullable: false),
                    schema_json = table.Column<string>(type: "jsonb", nullable: false),
                    expires_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    updated_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_schema_cache", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "users",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    email = table.Column<string>(type: "character varying(255)", maxLength: 255, nullable: false),
                    password_hash = table.Column<string>(type: "text", nullable: false),
                    full_name = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                    role = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    is_active = table.Column<bool>(type: "boolean", nullable: false),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    updated_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_users", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "database_connections",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    user_id = table.Column<Guid>(type: "uuid", nullable: false),
                    db_id = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    display_name = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                    connection_string = table.Column<string>(type: "text", nullable: false),
                    provider = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    is_active = table.Column<bool>(type: "boolean", nullable: false),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    updated_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_database_connections", x => x.id);
                    table.ForeignKey(
                        name: "fk_database_connections_users_user_id",
                        column: x => x.user_id,
                        principalTable: "users",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "query_history",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    user_id = table.Column<Guid>(type: "uuid", nullable: false),
                    db_id = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    natural_language_query = table.Column<string>(type: "text", nullable: false),
                    generated_sql = table.Column<string>(type: "text", nullable: true),
                    explanation = table.Column<string>(type: "text", nullable: true),
                    execution_status = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    execution_time_ms = table.Column<int>(type: "integer", nullable: true),
                    error_message = table.Column<string>(type: "text", nullable: true),
                    result_data_json = table.Column<string>(type: "jsonb", nullable: true),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    updated_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_query_history", x => x.id);
                    table.ForeignKey(
                        name: "fk_query_history_users_user_id",
                        column: x => x.user_id,
                        principalTable: "users",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "ix_database_connections_db_id",
                table: "database_connections",
                column: "db_id");

            migrationBuilder.CreateIndex(
                name: "ix_database_connections_user_id",
                table: "database_connections",
                column: "user_id");

            migrationBuilder.CreateIndex(
                name: "ix_query_history_created_at",
                table: "query_history",
                column: "created_at",
                descending: new bool[0]);

            migrationBuilder.CreateIndex(
                name: "ix_query_history_user_id",
                table: "query_history",
                column: "user_id");

            migrationBuilder.CreateIndex(
                name: "ix_schema_cache_db_id",
                table: "schema_cache",
                column: "db_id");

            migrationBuilder.CreateIndex(
                name: "ix_schema_cache_expires_at",
                table: "schema_cache",
                column: "expires_at");

            migrationBuilder.CreateIndex(
                name: "ix_users_email",
                table: "users",
                column: "email",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "database_connections");

            migrationBuilder.DropTable(
                name: "query_history");

            migrationBuilder.DropTable(
                name: "schema_cache");

            migrationBuilder.DropTable(
                name: "users");
        }
    }
}
