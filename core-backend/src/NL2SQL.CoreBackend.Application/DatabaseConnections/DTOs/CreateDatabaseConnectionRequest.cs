namespace NL2SQL.CoreBackend.Application.DatabaseConnections.DTOs;

public record CreateDatabaseConnectionRequest(
    string DbId,
    string DisplayName,
    string ConnectionString,
    string Provider
);
