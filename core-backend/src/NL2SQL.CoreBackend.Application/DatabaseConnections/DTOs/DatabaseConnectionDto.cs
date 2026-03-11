namespace NL2SQL.CoreBackend.Application.DatabaseConnections.DTOs;

public record DatabaseConnectionDto(
    Guid Id,
    string DbId,
    string DisplayName,
    string Provider,
    bool IsActive,
    DateTime CreatedAt
);
