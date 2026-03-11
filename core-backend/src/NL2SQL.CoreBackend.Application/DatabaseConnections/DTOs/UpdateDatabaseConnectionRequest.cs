namespace NL2SQL.CoreBackend.Application.DatabaseConnections.DTOs;

public record UpdateDatabaseConnectionRequest(
    string? DisplayName,
    string? ConnectionString,
    string? Provider,
    bool? IsActive
);
